import { Hono } from "hono";
import { getDB } from "../db.js";
import { paginate, defaultPage, defaultLimit } from "../utils/response.js";
import { simulatedDelay } from "../utils/delay.js";
import { id } from "../utils/id.js";
import { pointsForPayment, tierForPoints, tierProgressForPoints } from "../seed/tiers.js";
import type { Installment, Payment, PaymentAppliedTo } from "../schema/index.js";

export const paymentRoutes = new Hono();

// ── Tipos de respuesta del validate ─────────────────────────────────
type ValidateResult =
  | { result: "PAYMENT_CREATED_AND_VALIDATED"; payment: unknown; installment: unknown; pointsEarned: number }
  | { result: "PAYMENT_ALREADY_VALIDATED"; payment: unknown; message: string }
  | { result: "PAYMENT_NOT_FOUND"; message: string };

// ── Desenlaces determinados por el prefijo de la referencia ─────────
/**
 * `POST /payments/validate` NO consulta ni muta la DB para decidir su
 * resultado: el desenlace es función del prefijo de `externalReference`.
 *
 *   REF_OK…        → PAYMENT_CREATED_AND_VALIDATED
 *   REF_DUP…       → PAYMENT_ALREADY_VALIDATED (sin warning)
 *   REF_WRONG…     → PAYMENT_ALREADY_VALIDATED + warning (habilita reassign)
 *   cualquier otra → PAYMENT_NOT_FOUND (404)
 *
 * Por qué así y no por estado real:
 *  - **Determinista** — el mismo input da el mismo resultado siempre, así los
 *    evals pueden afirmar un desenlace exacto en vez de tolerar azar.
 *  - **Sin efectos secundarios** — no marca cuotas pagadas ni suma puntos, así
 *    que no hay nada que resetear entre corridas de eval.
 *  - **Elegible** — para probar una rama concreta basta cambiar la referencia.
 *
 * El seed emite referencias con estos prefijos (`REF_OK…` en pagos pendientes,
 * `REF_WRONG…` en el escenario de orden equivocada), así que una referencia
 * descubierta navegando la data produce el desenlace que le corresponde.
 *
 * Los datos de cuota/orden de la respuesta sí se leen de la DB (solo lectura)
 * para que el payload sea coherente con lo que el agente ve en
 * `GET /orders/:id/installments`.
 */
type Outcome = "created" | "duplicate" | "wrong_installment";

const OUTCOME_BY_PREFIX: ReadonlyArray<readonly [string, Outcome]> = [
  ["REF_WRONG", "wrong_installment"],
  ["REF_DUP", "duplicate"],
  ["REF_OK", "created"],
];

function outcomeFor(externalReference: string): Outcome | null {
  for (const [prefix, outcome] of OUTCOME_BY_PREFIX) {
    if (externalReference.startsWith(prefix)) return outcome;
  }
  return null;
}

/**
 * Prefijo de los ids de pago sintéticos. `validate` no persiste nada, así que
 * el id se deriva de la referencia — estable entre llamadas y reconocible por
 * `reassign`, que necesita seguir el flujo sin que exista una fila en la DB.
 */
const MOCK_PAYMENT_PREFIX = "pmt_mock_";

function mockPaymentId(externalReference: string): string {
  return MOCK_PAYMENT_PREFIX + externalReference.toLowerCase().replace(/[^a-z0-9]/g, "");
}

/** Cuotas del usuario en orden estable (por orden, luego número). Solo lectura. */
function userInstallments(db: ReturnType<typeof getDB>, userId: string): Installment[] {
  return db.installments
    .filter((i) => i.userId === userId)
    .sort((a, b) => a.orderId.localeCompare(b.orderId) || a.number - b.number);
}

function appliedTo(db: ReturnType<typeof getDB>, inst: Installment | null): PaymentAppliedTo {
  if (!inst) {
    return { installmentId: null, orderId: null, orderMerchantName: null, installmentNumber: null };
  }
  return {
    installmentId: inst.id,
    orderId: inst.orderId,
    orderMerchantName: db.orders.get(inst.orderId)?.merchantName ?? null,
    installmentNumber: inst.number,
  };
}

const DAY_MS = 86_400_000;

// ── GET /api/v1/payments ────────────────────────────────────────────
paymentRoutes.get("/payments", async (c) => {
  await simulatedDelay();
  const db = getDB();
  const query = c.req.query();

  let payments = [...db.payments.values()];

  if (query["userId"]) {
    payments = payments.filter((p) => p.userId === query["userId"]);
  }
  if (query["status"]) {
    payments = payments.filter((p) => p.status === query["status"]);
  }

  payments.sort((a, b) => b.createdAt.localeCompare(a.createdAt));

  const page = defaultPage(query);
  const limit = defaultLimit(query);
  return c.json(paginate(payments, page, limit));
});

// ── GET /api/v1/payments/:id ────────────────────────────────────────
paymentRoutes.get("/payments/:id", async (c) => {
  await simulatedDelay();
  const db = getDB();
  const payment = db.payments.get(c.req.param("id"));
  if (!payment) return c.json({ error: "Payment not found" }, 404);
  return c.json(payment);
});

// ── POST /api/v1/payments/validate ──────────────────────────────────
/**
 * Valida un pago por su referencia externa. El desenlace lo decide el prefijo
 * de `externalReference` (ver OUTCOME_BY_PREFIX); este handler no muta la DB.
 *
 * Caso 1 — PAYMENT_CREATED_AND_VALIDATED (`REF_OK…`, 200):
 *   El pago se concilió y se aplicó a la primera cuota impaga del cliente.
 *
 * Caso 2 — PAYMENT_ALREADY_VALIDATED (`REF_DUP…`, 200):
 *   Ya se había validado antes, y sobre la cuota correcta. Sin warning.
 *
 * Caso 3 — PAYMENT_ALREADY_VALIDATED + warning (`REF_WRONG…`, 200):
 *   Ya se había validado, pero sobre una cuota de otra orden. Trae
 *   `correctInstallmentId` para que el agente pueda ofrecer reasignarlo.
 *
 * Caso 4 — PAYMENT_NOT_FOUND (404):
 *   La referencia no corresponde a ningún pago. Es un desenlace de negocio,
 *   no un fallo técnico: cubre el comprobante falso y la referencia mal tipeada.
 */
paymentRoutes.post("/payments/validate", async (c) => {
  await simulatedDelay();
  const db = getDB();

  let body: { externalReference?: string; userId?: string };
  try {
    body = await c.req.json();
  } catch {
    return c.json({ error: "Invalid body" }, 400);
  }

  if (!body.externalReference || !body.userId) {
    return c.json({ error: "externalReference and userId are required" }, 400);
  }

  const externalReference = body.externalReference;
  const userId = body.userId;
  const outcome = outcomeFor(externalReference);

  if (!outcome) {
    const result: ValidateResult = {
      result: "PAYMENT_NOT_FOUND",
      message: `No payment found with reference '${externalReference}' for this user`,
    };
    return c.json(result, 404);
  }

  // Solo lectura — para que el payload sea coherente con la data del cliente.
  const installments = userInstallments(db, userId);
  const intendedInst = installments.find((i) => i.status !== "paid") ?? installments[0] ?? null;

  if (!intendedInst) {
    const result: ValidateResult = {
      result: "PAYMENT_NOT_FOUND",
      message: `No installments found for user '${userId}' — nothing to apply this payment to`,
    };
    return c.json(result, 404);
  }

  const base = {
    id: mockPaymentId(externalReference),
    userId,
    externalReference,
    amount: intendedInst.amountDue,
    currency: "MXN",
    method: "spei",
    createdAt: new Date(Date.now() - 3 * DAY_MS).toISOString(),
  } as const;

  // ── REF_OK… — conciliado y aplicado a la cuota que el cliente pagó ──
  if (outcome === "created") {
    const payment: Payment = {
      ...base,
      status: "validated",
      appliedTo: appliedTo(db, intendedInst),
      validatedAt: new Date().toISOString(),
      correctInstallmentId: null,
    };
    const result: ValidateResult = {
      result: "PAYMENT_CREATED_AND_VALIDATED",
      payment,
      installment: { ...intendedInst, status: "paid" },
      pointsEarned: pointsForPayment(intendedInst.amountDue),
    };
    return c.json(result);
  }

  // ── REF_DUP… — ya estaba validado, y en el lugar correcto ───────────
  if (outcome === "duplicate") {
    const validatedAt = new Date(Date.now() - 2 * DAY_MS).toISOString();
    const payment: Payment = {
      ...base,
      status: "validated",
      appliedTo: appliedTo(db, intendedInst),
      validatedAt,
      correctInstallmentId: null,
    };
    const result: ValidateResult = {
      result: "PAYMENT_ALREADY_VALIDATED",
      payment,
      message: `Payment ${payment.id} was already validated on ${validatedAt}`,
    };
    return c.json(result);
  }

  // ── REF_WRONG… — validado, pero aplicado a una cuota de otra orden ──
  const wrongInst =
    installments.find((i) => i.orderId !== intendedInst.orderId) ??
    installments.find((i) => i.id !== intendedInst.id) ??
    intendedInst;

  const payment: Payment & { warning: string } = {
    ...base,
    status: "validated",
    appliedTo: appliedTo(db, wrongInst),
    validatedAt: new Date(Date.now() - 2 * DAY_MS).toISOString(),
    correctInstallmentId: intendedInst.id,
    warning: "Payment was applied to a different installment than expected",
  };

  const result: ValidateResult = {
    result: "PAYMENT_ALREADY_VALIDATED",
    payment,
    message:
      `Payment ${payment.id} was already validated, but it was applied to installment ` +
      `${wrongInst.number} of order '${payment.appliedTo.orderMerchantName}' — which may not ` +
      `be the order the customer intended to pay.`,
  };
  return c.json(result);
});

// ── POST /api/v1/payments/:id/reassign ──────────────────────────────
/**
 * Reasigna un pago ya validado a otra cuota.
 *
 * 1. Revierte la cuota equivocada: status vuelve a su estado anterior,
 *    se elimina la transacción de pago asociada.
 * 2. Aplica el pago a la cuota correcta: status → paid, nueva transacción,
 *    puntos recalculados.
 * 3. Actualiza credit account y membership.
 */
paymentRoutes.post("/payments/:id/reassign", async (c) => {
  await simulatedDelay();
  const db = getDB();
  const paymentId = c.req.param("id");

  let body: { installmentId?: string };
  try {
    body = await c.req.json();
  } catch {
    return c.json({ error: "Invalid body" }, 400);
  }

  const payment = db.payments.get(paymentId);

  // ── Pago sintético (viene de un validate con REF_WRONG…) ────────────
  // `validate` no persiste nada, así que ese pago no existe en la DB. Se
  // responde canned para que el flujo validate → reassign sea coherente en
  // los dos turnos, que es justo lo que el eval L3 necesita ejercitar.
  if (!payment) {
    if (!paymentId.startsWith(MOCK_PAYMENT_PREFIX)) {
      return c.json({ error: "Payment not found" }, 404);
    }
    if (!body.installmentId) {
      return c.json({ error: "installmentId is required" }, 400);
    }
    const targetInst = db.installments.find((i) => i.id === body.installmentId);
    if (!targetInst) return c.json({ error: "Target installment not found" }, 404);

    return c.json({
      result: "PAYMENT_REASSIGNED",
      payment: {
        id: paymentId,
        userId: targetInst.userId,
        amount: targetInst.amountDue,
        status: "reassigned",
        appliedTo: appliedTo(db, targetInst),
        correctInstallmentId: null,
      },
      installment: { ...targetInst, status: "paid" },
      previousInstallmentId: null,
      pointsEarned: pointsForPayment(targetInst.amountDue),
    });
  }

  if (payment.status !== "validated") {
    return c.json({ error: "Payment must be validated before reassignment" }, 409);
  }

  // Determinar la cuota destino
  const targetInstallmentId = body.installmentId ?? payment.correctInstallmentId ?? null;
  if (!targetInstallmentId) {
    return c.json({ error: "installmentId is required (or payment must have correctInstallmentId set)" }, 400);
  }

  const targetInst = db.installments.find((i) => i.id === targetInstallmentId);
  if (!targetInst) return c.json({ error: "Target installment not found" }, 404);
  if (targetInst.userId !== payment.userId) {
    return c.json({ error: "Installment does not belong to the same user" }, 409);
  }

  const now = new Date().toISOString();

  // 1. Revertir la cuota equivocada (si existe)
  const wrongInstId = payment.appliedTo.installmentId;
  if (wrongInstId && wrongInstId !== targetInst.id) {
    const wrongInst = db.installments.find((i) => i.id === wrongInstId);
    if (wrongInst) {
      // Restaurar estado — si tenía overdue, vuelve a overdue; si no, due
      const dueDate = new Date(wrongInst.dueDate).getTime();
      wrongInst.status = dueDate < Date.now() ? "overdue" : "due";
      wrongInst.paidDate = null;
      wrongInst.paymentMethodId = null;
    }

    // Eliminar la transacción de pago de la cuota equivocada
    db.transactions = db.transactions.filter(
      (t) => t.referenceId !== wrongInstId || t.type !== "payment",
    );
  }

  // 2. Aplicar el pago a la cuota correcta
  targetInst.status = "paid";
  targetInst.paidDate = now;
  targetInst.paymentMethodId = null;

  const targetOrder = db.orders.get(targetInst.orderId);

  // Actualizar el payment
  payment.status = "reassigned";
  payment.appliedTo = {
    installmentId: targetInst.id,
    orderId: targetInst.orderId,
    orderMerchantName: targetOrder?.merchantName ?? null,
    installmentNumber: targetInst.number,
  };
  payment.correctInstallmentId = null; // ya se reasignó

  // Crear nueva transacción
  db.transactions.push({
    id: id("txn"),
    userId: payment.userId,
    type: "payment",
    direction: "credit",
    amount: targetInst.amountDue,
    description: `Payment reassigned - Installment ${targetInst.number}/${targetOrder?.installmentCount ?? "?"} - ${targetOrder?.merchantName ?? "Unknown"} (ref: ${payment.externalReference})`,
    referenceType: "installment",
    referenceId: targetInst.id,
    createdAt: now,
  });

  // Puntos ganados
  const pts = pointsForPayment(targetInst.amountDue);
  db.pointsTransactions.push({
    id: id("pts"),
    userId: payment.userId,
    type: "earned",
    amount: pts,
    source: "order_payment",
    referenceId: targetInst.id,
    description: `Points earned (reassigned) - Installment ${targetInst.number} - ${targetOrder?.merchantName ?? "Unknown"}`,
    createdAt: now,
  });

  // 3. Recalcular credit account y membership
  recalcCredit(db, payment.userId, now);
  recalcMembership(db, payment.userId, now);

  return c.json({
    result: "PAYMENT_REASSIGNED",
    payment,
    installment: targetInst,
    previousInstallmentId: wrongInstId ?? null,
    pointsEarned: pts,
  });
});

// ── Helpers de recálculo ────────────────────────────────────────────

function recalcCredit(db: ReturnType<typeof getDB>, userId: string, now: string): void {
  const credit = [...db.creditAccounts.values()].find((cr) => cr.userId === userId);
  if (!credit) return;
  const allInst = db.installments.filter((i) => i.userId === userId);
  const outstanding = allInst
    .filter((i) => i.status !== "paid")
    .reduce((sum, i) => sum + i.amountDue, 0);
  credit.outstandingBalance = outstanding;
  credit.availableCredit = credit.creditLimit - outstanding;
  credit.utilizationPct = credit.creditLimit > 0
    ? Math.round((outstanding / credit.creditLimit) * 10000) / 100
    : 0;
  credit.updatedAt = now;
}

function recalcMembership(db: ReturnType<typeof getDB>, userId: string, now: string): void {
  const membership = [...db.memberships.values()].find((m) => m.userId === userId);
  if (!membership) return;
  const totalPoints = db.pointsTransactions
    .filter((p) => p.userId === userId)
    .reduce((sum, p) => sum + p.amount, 0);
  membership.pointsBalance = totalPoints;
  membership.tier = tierForPoints(totalPoints);
  membership.tierProgress = tierProgressForPoints(totalPoints);
  membership.updatedAt = now;
}

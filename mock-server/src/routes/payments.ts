import { Hono } from "hono";
import { getDB } from "../db.js";
import { paginate, defaultPage, defaultLimit } from "../utils/response.js";
import { simulatedDelay } from "../utils/delay.js";
import { id } from "../utils/id.js";
import { pointsForPayment, tierForPoints, tierProgressForPoints } from "../seed/tiers.js";
import type { Installment, Payment, PaymentAppliedTo } from "../schema/index.js";

export const paymentRoutes = new Hono();

// ── Body del validate (formato venezolano) ──────────────────────────
interface ValidatePaymentBody {
  correo?: string;
  cedula?: string;
  orden?: string;
  referencia?: string;
  monto?: number;
  moneda?: string;
  fecha?: string;
  telefono?: string;
  originBankName?: string;
}

// ── Desenlaces determinados por el prefijo de la referencia ─────────
/**
 * `POST /payments/validate` NO consulta ni muta la DB para decidir su
 * resultado: el desenlace es función del prefijo de la `referencia`.
 *
 *   10…  → PAYMENT_CREATED_AND_VALIDATED
 *   20…  → PAYMENT_ALREADY_VALIDATED (ya validado, cuota correcta)
 *   30…  → PAYMENT_ALREADY_VALIDATED (aplicado a cuota equivocada → reassign)
 *   otra → PAYMENT_NOT_FOUND (404)
 *
 * Por qué así y no por estado real:
 *  - **Determinista** — el mismo input da el mismo resultado siempre, así los
 *    evals pueden afirmar un desenlace exacto en vez de tolerar azar.
 *  - **Sin efectos secundarios** — no marca cuotas pagadas ni suma puntos, así
 *    que no hay nada que resetear entre corridas de eval.
 *  - **Elegible** — para probar una rama concreta basta cambiar la referencia.
 *
 * El seed emite referencias numéricas con estos prefijos, así que una
 * referencia descubierta navegando la data produce el desenlace que le
 * corresponde.
 */
type Outcome = "created" | "duplicate" | "wrong_installment";

const OUTCOME_BY_PREFIX: ReadonlyArray<readonly [string, Outcome]> = [
  ["30", "wrong_installment"],
  ["20", "duplicate"],
  ["10", "created"],
];

function outcomeFor(referencia: string): Outcome | null {
  for (const [prefix, outcome] of OUTCOME_BY_PREFIX) {
    if (referencia.startsWith(prefix)) return outcome;
  }
  return null;
}

/**
 * Prefijo de los ids de pago sintéticos. `validate` no persiste nada, así que
 * el id se deriva de la referencia — estable entre llamadas y reconocible por
 * `reassign`, que necesita seguir el flujo sin que exista una fila en la DB.
 */
const MOCK_PAYMENT_PREFIX = "pmt_mock_";

function mockPaymentId(referencia: string): string {
  return MOCK_PAYMENT_PREFIX + referencia.toLowerCase().replace(/[^a-z0-9]/g, "");
}

/** Genera un paymentId numérico de 9 dígitos determinista a partir de la referencia. */
function numericPaymentId(referencia: string): string {
  let hash = 0;
  for (let i = 0; i < referencia.length; i++) {
    hash = (hash * 31 + referencia.charCodeAt(i)) & 0x7fffffff;
  }
  return String(100_000_000 + (hash % 900_000_000));
}

/** Verifica si un ID es un paymentId sintético (numérico de 9 dígitos o pmt_mock_). */
function isSyntheticPaymentId(id: string): boolean {
  return id.startsWith(MOCK_PAYMENT_PREFIX) || /^\d{9}$/.test(id);
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
 * Valida un pago por su referencia bancaria. El desenlace lo decide el prefijo
 * de `referencia` (ver OUTCOME_BY_PREFIX); este handler no muta la DB.
 *
 * Acepta el payload venezolano: correo, cédula, orden, referencia, monto,
 * moneda, fecha, teléfono, originBankName.
 *
 * Caso 1 — PAYMENT_CREATED_AND_VALIDATED (`10…`, 200):
 *   El pago se concilió y se creó en el sistema.
 *
 * Caso 2 — PAYMENT_ALREADY_VALIDATED (`20…`, 200):
 *   Ya se había validado antes, sobre la cuota correcta.
 *
 * Caso 3 — PAYMENT_ALREADY_VALIDATED (`30…`, 200):
 *   Ya se había validado, pero sobre una cuota de otra orden. Habilita reassign.
 *
 * Caso 4 — PAYMENT_NOT_FOUND (404):
 *   La referencia no corresponde a ningún pago.
 */
paymentRoutes.post("/payments/validate", async (c) => {
  await simulatedDelay();

  let body: ValidatePaymentBody;
  try {
    body = await c.req.json();
  } catch {
    return c.json({ error: "Invalid body" }, 400);
  }

  if (typeof body.referencia !== "string" || body.referencia.trim() === "") {
    return c.json({ error: "referencia is required and must be a string" }, 400);
  }

  const referencia = body.referencia;
  const outcome = outcomeFor(referencia);

  if (!outcome) {
    return c.json({
      status: "PAYMENT_NOT_FOUND",
      mensaje: "Payment not validated",
    }, 404);
  }

  // ── 10… — pago creado y validado ──────────────────────────────────
  if (outcome === "created") {
    return c.json({
      status: "PAYMENT_CREATED_AND_VALIDATED",
      mensaje: "Payment created and validated",
      paymentId: numericPaymentId(referencia),
    });
  }

  // ── 20… — ya estaba validado, en el lugar correcto ────────────────
  if (outcome === "duplicate") {
    return c.json({
      status: "PAYMENT_ALREADY_VALIDATED",
      mensaje: "Payment already validated",
    });
  }

  // ── 30… — validado, pero aplicado a cuota equivocada ──────────────
  // El paymentId sintético permite continuar el flujo con reassign.
  return c.json({
    status: "PAYMENT_ALREADY_VALIDATED",
    mensaje: "Payment already validated",
    paymentId: numericPaymentId(referencia),
  });
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

  // ── Pago sintético (viene de un validate con prefijo 30…) ──────────
  // `validate` no persiste nada, así que ese pago no existe en la DB. Se
  // responde canned para que el flujo validate → reassign sea coherente en
  // los dos turnos, que es justo lo que el eval L3 necesita ejercitar.
  if (!payment) {
    if (!isSyntheticPaymentId(paymentId)) {
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

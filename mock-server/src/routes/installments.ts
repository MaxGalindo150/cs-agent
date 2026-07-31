import { Hono } from "hono";
import { getDB } from "../db.js";
import { simulatedDelay } from "../utils/delay.js";
import { id } from "../utils/id.js";
import { pointsForPayment } from "../seed/tiers.js";
import type { Installment, Transaction, PointsTransaction } from "../schema/index.js";

export const installmentRoutes = new Hono();

// ── POST /api/v1/installments/:id/pay ───────────────────────────────
/**
 * Marca una cuota como pagada. En cadena:
 * - Cuota → status "paid", paidDate
 * - Transacción de pago
 * - Puntos ganados
 * - Credit account recalculado
 * - Membership recalculada (puntos + tier)
 */
installmentRoutes.post("/installments/:id/pay", async (c) => {
  await simulatedDelay();
  const db = getDB();
  const installmentId = c.req.param("id");

  const inst = db.installments.find((i) => i.id === installmentId);
  if (!inst) return c.json({ error: "Installment not found" }, 404);
  if (inst.status === "paid") return c.json({ error: "Installment already paid" }, 409);

  // Parsear body opcional
  let body: { paymentMethodId?: string } = {};
  try {
    body = await c.req.json();
  } catch {
    // body vacío es válido
  }

  const now = new Date().toISOString();

  // 1. Marcar cuota como pagada
  inst.status = "paid";
  inst.paidDate = now;
  inst.paymentMethodId = body.paymentMethodId ?? inst.paymentMethodId;

  // 2. Crear transacción de pago
  const order = db.orders.get(inst.orderId);
  const txn: Transaction = {
    id: id("txn"),
    userId: inst.userId,
    type: "payment",
    direction: "credit",
    amount: inst.amountDue,
    description: `Payment - Installment ${inst.number}/${order?.installmentCount ?? "?"} - ${order?.merchantName ?? "Unknown"}`,
    referenceType: "installment",
    referenceId: inst.id,
    createdAt: now,
  };
  db.transactions.push(txn);

  // 3. Puntos ganados
  const pts = pointsForPayment(inst.amountDue);
  const pointsTxn: PointsTransaction = {
    id: id("pts"),
    userId: inst.userId,
    type: "earned",
    amount: pts,
    source: "order_payment",
    referenceId: inst.id,
    description: `Points earned - Installment ${inst.number} - ${order?.merchantName ?? "Unknown"}`,
    createdAt: now,
  };
  db.pointsTransactions.push(pointsTxn);

  // 4. Recalcular credit account
  const credit = [...db.creditAccounts.values()].find((cr) => cr.userId === inst.userId);
  if (credit) {
    const allInst = db.installments.filter((i) => i.userId === inst.userId);
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

  // 5. Recalcular membership
  const membership = [...db.memberships.values()].find((m) => m.userId === inst.userId);
  if (membership) {
    const totalPoints = db.pointsTransactions
      .filter((p) => p.userId === inst.userId)
      .reduce((sum, p) => sum + p.amount, 0);
    membership.pointsBalance = totalPoints;
    // Tier update — recalculado dinámicamente
    const { tierForPoints, tierProgressForPoints } = await import("../seed/tiers.js");
    membership.tier = tierForPoints(totalPoints);
    membership.tierProgress = tierProgressForPoints(totalPoints);
    membership.updatedAt = now;
  }

  return c.json({ status: "paid", installment: inst, transaction: txn, pointsEarned: pts });
});

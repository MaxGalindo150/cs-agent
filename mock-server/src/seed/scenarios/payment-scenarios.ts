/**
 * Escenarios de anomalías de PAGOS y CRÉDITO.
 */

import { id } from "../../utils/id.js";
import { isoDaysAgo } from "../generators.js";
import { recalcCreditAccount } from "../generators.js";
import { tierForPoints, tierProgressForPoints } from "../tiers.js";
import type { Database } from "../../db.js";
import type { ScenarioTag } from "../../schema/index.js";
import type { Scenario } from "./types.js";
import { tagUser, usersWithFewestTags, activeOrders, completedOrders } from "./types.js";

// ── double_payment ──────────────────────────────────────────────────
export const doublePayment: Scenario = {
  tag: "double_payment",
  description: "User paid the same installment twice — duplicate payment not refunded",
  apply(db: Database): void {
    for (const userId of usersWithFewestTags(db, ["double_payment"])) {
      const orders = activeOrders(db, userId);
      if (orders.length === 0) continue;

      const order = orders[0]!;
      const installments = db.installments
        .filter((i) => i.orderId === order.id && i.status === "paid")
        .sort((a, b) => b.number - a.number);
      if (installments.length === 0) continue;

      const inst = installments[0]!;
      const pm = [...db.paymentMethods.values()].find((p) => p.userId === userId);
      if (!pm) continue;

      // Crear una segunda transacción de pago idéntica el mismo día
      db.transactions.push({
        id: id("txn"),
        userId,
        type: "payment",
        direction: "credit",
        amount: inst.amountDue,
        description: `Payment - Installment ${inst.number}/${order.installmentCount} - ${order.merchantName} (DUPLICATE)`,
        referenceType: "installment",
        referenceId: inst.id,
        createdAt: inst.paidDate ?? isoDaysAgo(1),
      });

      tagUser(db, userId, "double_payment");
      return;
    }
  },
};

// ── refund_pending ──────────────────────────────────────────────────
export const refundPending: Scenario = {
  tag: "refund_pending",
  description: "User requested a refund for a completed order but it hasn't been processed",
  apply(db: Database): void {
    for (const userId of usersWithFewestTags(db, ["refund_pending"])) {
      const orders = completedOrders(db, userId);
      if (orders.length === 0) continue;

      const order = orders[0]!;
      order.refundRequested = true;
      order.refundReason = "Product arrived damaged";
      order.updatedAt = isoDaysAgo(5);

      // No crear Transaction de refund — el problema es que falta
      tagUser(db, userId, "refund_pending");
      return;
    }
  },
};

// ── payment_not_reflected ───────────────────────────────────────────
export const paymentNotReflected: Scenario = {
  tag: "payment_not_reflected",
  description: "User made a payment (has external reference) but the installment is still unpaid",
  apply(db: Database): void {
    for (const userId of usersWithFewestTags(db, ["payment_not_reflected"])) {
      const orders = activeOrders(db, userId);
      if (orders.length === 0) continue;

      const order = orders[0]!;
      const installments = db.installments
        .filter((i) => i.orderId === order.id && (i.status === "upcoming" || i.status === "due"))
        .sort((a, b) => a.number - b.number);
      if (installments.length === 0) continue;

      const inst = installments[0]!;
      // El usuario tiene una referencia bancaria externa pero la cuota no se marcó como pagada
      inst.externalReference = `REF_OK${id("").slice(0, 8).toUpperCase()}`;
      // Crear un registro de que el pago se recibió pero no se concilió
      db.transactions.push({
        id: id("txn"),
        userId,
        type: "payment",
        direction: "credit",
        amount: inst.amountDue,
        description: `Bank transfer received (UNRECONCILED) - ref: ${inst.externalReference}`,
        referenceType: "installment",
        referenceId: inst.id,
        createdAt: isoDaysAgo(2),
      });

      tagUser(db, userId, "payment_not_reflected");
      return;
    }
  },
};

// ── failed_payment ──────────────────────────────────────────────────
export const failedPayment: Scenario = {
  tag: "failed_payment",
  description: "Payment failed but the charge went through — installment shows failed but money was taken",
  apply(db: Database): void {
    for (const userId of usersWithFewestTags(db, ["failed_payment"])) {
      const orders = activeOrders(db, userId);
      if (orders.length === 0) continue;

      const order = orders[0]!;
      const installments = db.installments
        .filter((i) => i.orderId === order.id && i.status !== "paid")
        .sort((a, b) => a.number - b.number);
      if (installments.length === 0) continue;

      const inst = installments[0]!;
      inst.status = "failed";
      // Pero sí hay un cobro
      db.transactions.push({
        id: id("txn"),
        userId,
        type: "payment",
        direction: "credit",
        amount: inst.amountDue,
        description: `Charge attempt (FAILED but charged) - ${order.merchantName}`,
        referenceType: "installment",
        referenceId: inst.id,
        createdAt: isoDaysAgo(1),
      });

      tagUser(db, userId, "failed_payment");
      return;
    }
  },
};

// ── overcharged ─────────────────────────────────────────────────────
export const overcharged: Scenario = {
  tag: "overcharged",
  description: "Payment amount is higher than the installment's amount due",
  apply(db: Database): void {
    for (const userId of usersWithFewestTags(db, ["overcharged"])) {
      const orders = activeOrders(db, userId);
      if (orders.length === 0) continue;

      const order = orders[0]!;
      const installments = db.installments
        .filter((i) => i.orderId === order.id && i.status === "paid")
        .sort((a, b) => b.number - a.number);
      if (installments.length === 0) continue;

      const inst = installments[0]!;
      // Buscar la transacción de pago y aumentar el monto
      const txn = db.transactions.find(
        (t) => t.referenceId === inst.id && t.type === "payment",
      );
      if (!txn) continue;

      txn.amount = inst.amountDue + Math.round(inst.amountDue * 0.25); // 25% más
      txn.description += " (OVERCHARGED)";

      tagUser(db, userId, "overcharged");
      return;
    }
  },
};

// ── cancelled_but_charged ───────────────────────────────────────────
export const cancelledButCharged: Scenario = {
  tag: "cancelled_but_charged",
  description: "Order was cancelled but installments after cancellation are marked as paid",
  apply(db: Database): void {
    for (const userId of usersWithFewestTags(db, ["cancelled_but_charged"])) {
      const orders = [...db.orders.values()].filter(
        (o) => o.userId === userId && o.installmentCount >= 3,
      );
      if (orders.length === 0) continue;

      const order = orders[0]!;
      order.status = "cancelled";
      order.updatedAt = isoDaysAgo(20);

      // Cancelar las últimas cuotas pero dejar las primeras pagadas
      const installments = db.installments
        .filter((i) => i.orderId === order.id)
        .sort((a, b) => a.number - b.number);
      const cutoff = Math.ceil(installments.length / 2);
      for (const inst of installments) {
        if (inst.number > cutoff) {
          inst.status = "paid";
          inst.paidDate = isoDaysAgo(randInt2(1, 15));
        }
      }

      // Recalcular crédito
      const credit = [...db.creditAccounts.values()].find((c) => c.userId === userId);
      if (credit) {
        const allInst = db.installments.filter((i) => i.userId === userId);
        const updated = recalcCreditAccount(credit, allInst);
        db.creditAccounts.set(updated.id, updated);
      }

      tagUser(db, userId, "cancelled_but_charged");
      return;
    }
  },
};

function randInt2(min: number, max: number): number {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

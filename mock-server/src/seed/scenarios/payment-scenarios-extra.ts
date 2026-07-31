/**
 * Escenario: payment_wrong_order
 *
 * El pago del cliente fue validado y aplicado, pero se asignó a la
 * cuota de una orden equivocada. El agente debe descubrir el mismatch
 * y usar POST /payments/:id/reassign para moverlo a la cuota correcta.
 *
 * Cómo se construye la anomalía:
 * 1. Se toma un usuario con al menos 2 órdenes activas con cuotas impagas.
 * 2. Se crea un Payment en estado `validated`, aplicado a la cuota A (equivocada).
 * 3. La cuota A se marca como `paid` (el sistema la dio por pagada).
 * 4. Se registra `correctInstallmentId` apuntando a la cuota B (la que el
 *    cliente realmente quería pagar, que sigue impaga).
 * 5. Se actualiza el credit account para reflejar el estado inconsistente.
 */

import { id } from "../../utils/id.js";
import { isoDaysAgo, nowISO } from "../generators.js";
import type { Database } from "../../db.js";
import type { Payment, Installment } from "../../schema/index.js";
import type { Scenario } from "./types.js";
import { tagUser, usersWithFewestTags } from "./types.js";

export const paymentWrongOrder: Scenario = {
  tag: "payment_wrong_order",
  description:
    "Payment was validated and applied to the wrong order's installment — needs reassignment",
  apply(db: Database): void {
    for (const userId of usersWithFewestTags(db, ["payment_wrong_order"])) {
      // Buscar cuotas impagas del usuario, agrupadas por orden
      const unpaid = db.installments.filter(
        (i) => i.userId === userId && (i.status === "upcoming" || i.status === "due" || i.status === "overdue"),
      );
      if (unpaid.length < 2) continue;

      // Agrupar por orderId
      const byOrder = new Map<string, Installment[]>();
      for (const inst of unpaid) {
        const arr = byOrder.get(inst.orderId) ?? [];
        arr.push(inst);
        byOrder.set(inst.orderId, arr);
      }
      if (byOrder.size < 2) continue;

      // Tomar dos órdenes distintas
      const orderGroups = [...byOrder.values()];
      const wrongGroup = orderGroups[0]!;
      const correctGroup = orderGroups[1]!;
      const wrongInst = wrongGroup[0]!;
      const correctInst = correctGroup[0]!;

      // Marcar la cuota equivocada como pagada (el sistema se equivocó)
      wrongInst.status = "paid";
      wrongInst.paidDate = isoDaysAgo(2);
      wrongInst.paymentMethodId = null;

      // Crear transacción de pago
      const wrongOrder = db.orders.get(wrongInst.orderId);
      db.transactions.push({
        id: id("txn"),
        userId,
        type: "payment",
        direction: "credit",
        amount: wrongInst.amountDue,
        description: `Payment - Installment ${wrongInst.number}/${wrongOrder?.installmentCount ?? "?"} - ${wrongOrder?.merchantName ?? "Unknown"}`,
        referenceType: "installment",
        referenceId: wrongInst.id,
        createdAt: isoDaysAgo(2),
      });

      // Crear el Payment ya validado, aplicado a la cuota equivocada
      const payment: Payment = {
        id: id("pmt"),
        userId,
        externalReference: `REF_WRONG${id("").slice(0, 8).toUpperCase()}`,
        amount: correctInst.amountDue, // el monto que el cliente realmente pagó
        currency: "MXN",
        method: "spei",
        status: "validated",
        appliedTo: {
          installmentId: wrongInst.id,
          orderId: wrongInst.orderId,
          orderMerchantName: wrongOrder?.merchantName ?? null,
          installmentNumber: wrongInst.number,
        },
        validatedAt: isoDaysAgo(2),
        correctInstallmentId: correctInst.id, // ← la cuota que el cliente quería pagar
        createdAt: isoDaysAgo(3),
      };
      db.payments.set(payment.id, payment);

      // Recalcular credit account
      const credit = [...db.creditAccounts.values()].find((c) => c.userId === userId);
      if (credit) {
        const allInst = db.installments.filter((i) => i.userId === userId);
        const outstanding = allInst
          .filter((i) => i.status !== "paid")
          .reduce((sum, i) => sum + i.amountDue, 0);
        credit.outstandingBalance = outstanding;
        credit.availableCredit = credit.creditLimit - outstanding;
        credit.utilizationPct = credit.creditLimit > 0
          ? Math.round((outstanding / credit.creditLimit) * 10000) / 100
          : 0;
        credit.updatedAt = nowISO();
      }

      tagUser(db, userId, "payment_wrong_order");
      return;
    }
  },
};

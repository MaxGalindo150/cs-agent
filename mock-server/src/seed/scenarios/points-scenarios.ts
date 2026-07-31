/**
 * Escenarios de anomalías de PUNTOS y NIVELES.
 */

import { id } from "../../utils/id.js";
import { isoDaysAgo } from "../generators.js";
import { tierForPoints, tierProgressForPoints } from "../tiers.js";
import type { Database } from "../../db.js";
import type { Scenario } from "./types.js";
import { tagUser, usersWithFewestTags, activeOrders, completedOrders } from "./types.js";

// ── missing_points ──────────────────────────────────────────────────
export const missingPoints: Scenario = {
  tag: "missing_points",
  description: "Order is completed with all installments paid, but no points were ever awarded",
  apply(db: Database): void {
    for (const userId of usersWithFewestTags(db, ["missing_points"])) {
      const orders = completedOrders(db, userId);
      if (orders.length === 0) continue;

      const order = orders[orders.length - 1]!; // la más reciente
      // Eliminar todos los points transactions de las cuotas de esta orden
      const orderInstIds = db.installments
        .filter((i) => i.orderId === order.id)
        .map((i) => i.id);
      db.pointsTransactions = db.pointsTransactions.filter(
        (p) => !(p.userId === userId && p.referenceId && orderInstIds.includes(p.referenceId)),
      );

      // Recalcular membership
      recalcMembershipSafe(db, userId);

      tagUser(db, userId, "missing_points");
      return;
    }
  },
};

// ── partial_points ──────────────────────────────────────────────────
export const partialPoints: Scenario = {
  tag: "partial_points",
  description: "Points were awarded but at a lower rate than expected (e.g. half)",
  apply(db: Database): void {
    for (const userId of usersWithFewestTags(db, ["partial_points"])) {
      const orders = completedOrders(db, userId);
      if (orders.length === 0) continue;

      const order = orders[0]!;
      const orderInstIds = db.installments
        .filter((i) => i.orderId === order.id)
        .map((i) => i.id);

      // Reducir a la mitad los puntos de esta orden
      for (const pts of db.pointsTransactions) {
        if (pts.userId === userId && pts.referenceId && orderInstIds.includes(pts.referenceId)) {
          pts.amount = Math.floor(pts.amount / 2);
          pts.description += " (PARTIAL)";
        }
      }

      recalcMembershipSafe(db, userId);
      tagUser(db, userId, "partial_points");
      return;
    }
  },
};

// ── stale_tier ──────────────────────────────────────────────────────
export const staleTier: Scenario = {
  tag: "stale_tier",
  description: "User's points balance qualifies for a higher tier, but tier was not updated",
  apply(db: Database): void {
    for (const userId of usersWithFewestTags(db, ["stale_tier"])) {
      const membership = [...db.memberships.values()].find((m) => m.userId === userId);
      if (!membership) continue;

      // Subir los puntos a un nivel que cruza el siguiente tier,
      // pero NO actualizar el campo tier.
      const currentTierIndex = ["bronze", "silver", "gold", "platinum"].indexOf(membership.tier);
      if (currentTierIndex >= 3) continue; // ya es platinum

      const nextThresholds = [1000, 5000, 20000]; // silver, gold, platinum
      const threshold = nextThresholds[currentTierIndex]!;

      membership.pointsBalance = threshold + 200;
      membership.tierProgress = tierProgressForPoints(membership.pointsBalance);
      // NO actualizar tier — ese es el bug
      membership.updatedAt = isoDaysAgo(7);

      tagUser(db, userId, "stale_tier");
      return;
    }
  },
};

// ── overdue_unnotified ──────────────────────────────────────────────
export const overdueUnnotified: Scenario = {
  tag: "overdue_unnotified",
  description: "Installment is overdue but user was never notified — looks unaware",
  apply(db: Database): void {
    for (const userId of usersWithFewestTags(db, ["overdue_unnotified"])) {
      const orders = activeOrders(db, userId);
      if (orders.length === 0) continue;

      const order = orders[0]!;
      const installments = db.installments
        .filter((i) => i.orderId === order.id && (i.status === "upcoming" || i.status === "due"))
        .sort((a, b) => a.number - b.number);
      if (installments.length === 0) continue;

      const inst = installments[0]!;
      inst.status = "overdue";
      inst.dueDate = isoDaysAgo(10);

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

      tagUser(db, userId, "overdue_unnotified");
      return;
    }
  },
};

// ── phantom_order ───────────────────────────────────────────────────
export const phantomOrder: Scenario = {
  tag: "phantom_order",
  description: "Order exists that the user does not recognize — suspicious merchant/device",
  apply(db: Database): void {
    for (const userId of usersWithFewestTags(db, ["phantom_order"])) {
      // Crear una orden nueva y sospechosa
      const order = {
        id: id("ord"),
        userId,
        merchantId: "mch_unknown",
        merchantName: "Unknown Merchant #4892",
        items: [
          {
            sku: "UNKNOWN001",
            name: "Digital Service Subscription",
            qty: 1,
            unitPrice: 49900, // $499.00
          },
        ],
        subtotal: 49900,
        shipping: 0,
        tax: 7984,
        totalAmount: 57884,
        plan: "monthly_12" as const,
        status: "active" as const,
        financing: {
          principal: 49900,
          interest: 9182,
          fees: 499,
          apr: 22,
          termMonths: 12,
        },
        installmentCount: 12,
        refundRequested: false,
        refundReason: null,
        createdAt: isoDaysAgo(3),
        updatedAt: isoDaysAgo(3),
      };
      db.orders.set(order.id, order);

      // Crear primera cuota en estado due
      db.installments.push({
        id: id("ins"),
        orderId: order.id,
        userId,
        number: 1,
        amountDue: 4805,
        principal: 4158,
        interest: 765,
        fees: 499,
        dueDate: isoDaysAgo(3),
        paidDate: null,
        status: "due",
        paymentMethodId: null,
        externalReference: null,
      });

      db.transactions.push({
        id: id("txn"),
        userId,
        type: "purchase",
        direction: "debit",
        amount: 57884,
        description: "Purchase at Unknown Merchant #4892",
        referenceType: "order",
        referenceId: order.id,
        createdAt: isoDaysAgo(3),
      });

      tagUser(db, userId, "phantom_order");
      return;
    }
  },
};

// ── Helper ──────────────────────────────────────────────────────────
function recalcMembershipSafe(db: Database, userId: string): void {
  const membership = [...db.memberships.values()].find((m) => m.userId === userId);
  if (!membership) return;
  const userPoints = db.pointsTransactions.filter((p) => p.userId === userId);
  const totalPoints = userPoints.reduce((sum, p) => sum + p.amount, 0);
  membership.pointsBalance = totalPoints;
  // Aquí SÍ actualizamos el tier (a diferencia de stale_tier)
  membership.tier = tierForPoints(totalPoints);
  membership.tierProgress = tierProgressForPoints(totalPoints);
  membership.updatedAt = nowISO();
}

function nowISO(): string {
  return new Date().toISOString();
}

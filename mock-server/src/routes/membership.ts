import { Hono } from "hono";
import { getDB } from "../db.js";
import { simulatedDelay } from "../utils/delay.js";
import { id } from "../utils/id.js";

export const membershipRoutes = new Hono();

/**
 * POST /api/v1/memberships/:id/redeem
 * Body: { amount: number }  — puntos a canjear contra el saldo
 * Resta puntos del balance, reduce el outstanding balance de crédito.
 */
membershipRoutes.post("/memberships/:id/redeem", async (c) => {
  await simulatedDelay();
  const db = getDB();
  const membershipId = c.req.param("id");

  const membership = [...db.memberships.values()].find((m) => m.id === membershipId);
  if (!membership) return c.json({ error: "Membership not found" }, 404);

  let body: { amount?: number };
  try {
    body = await c.req.json();
  } catch {
    return c.json({ error: "Invalid body" }, 400);
  }

  if (!body.amount || body.amount <= 0) {
    return c.json({ error: "amount must be a positive number" }, 400);
  }

  if (body.amount > membership.pointsBalance) {
    return c.json({ error: "Insufficient points balance" }, 409);
  }

  const now = new Date().toISOString();

  // Restar puntos
  membership.pointsBalance -= body.amount;

  // Recalcular tier progress
  const { tierProgressForPoints } = await import("../seed/tiers.js");
  membership.tierProgress = tierProgressForPoints(membership.pointsBalance);
  membership.updatedAt = now;

  // Crear points transaction de canje
  db.pointsTransactions.push({
    id: id("pts"),
    userId: membership.userId,
    type: "redeemed",
    amount: -body.amount,
    source: "redemption",
    referenceId: null,
    description: `Points redeemed (${body.amount} pts)`,
    createdAt: now,
  });

  // Reducir outstanding balance del credit account (1 punto = $0.01)
  const credit = [...db.creditAccounts.values()].find((cr) => cr.userId === membership.userId);
  if (credit) {
    const creditAmount = body.amount * 100; // 1 pt = 1 cent
    credit.outstandingBalance = Math.max(0, credit.outstandingBalance - creditAmount);
    credit.availableCredit = credit.creditLimit - credit.outstandingBalance;
    credit.utilizationPct = credit.creditLimit > 0
      ? Math.round((credit.outstandingBalance / credit.creditLimit) * 10000) / 100
      : 0;
    credit.updatedAt = now;
  }

  return c.json({ status: "redeemed", membership, pointsRedeemed: body.amount });
});

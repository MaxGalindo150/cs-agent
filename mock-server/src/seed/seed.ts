/**
 * Orquestador del seed: genera 3 usuarios de demo (memorable, estables entre
 * reinicios) con su árbol completo de entidades (direcciones, pagos, crédito,
 * membresía, órdenes, cuotas, envíos, transacciones, puntos) y un escenario de
 * soporte conocido cada uno.
 */

import { f, initFaker } from "./faker.js";
import { resetIdCounter, id } from "../utils/id.js";
import { createEmptyDB, setDB, type Database } from "../db.js";
import {
  makeMerchants, makeUser, makeAddress, makePaymentMethod,
  makeCreditAccount, makeMembership, randomPointsForTier,
  generateOrder, recalcCreditAccount, recalcMembership,
  makePendingPayment,
} from "./generators.js";
import type { Installment } from "../schema/index.js";
import { shipmentStuck } from "./scenarios/shipment-scenarios.js";
import { doublePayment, failedPayment } from "./scenarios/payment-scenarios.js";

/** Fixed demo identities — memorable names/emails for the login selector.
 * Everything else about them (dob, orders, credit, points…) still comes from
 * the seeded faker instance, so it's rich but deterministic across restarts. */
export const DEMO_USERS = [
  { firstName: "Ana", lastName: "Rodríguez", email: "ana.rodriguez@example.com", phone: "+584125551001" },
  { firstName: "Carlos", lastName: "Mendoza", email: "carlos.mendoza@example.com", phone: "+584145551002" },
  { firstName: "Luisana", lastName: "Pérez", email: "luisana.perez@example.com", phone: "+584245551003" },
] as const;

export const SEED_USER_COUNT = DEMO_USERS.length;

// One known support scenario per demo user (see seed/scenarios/) instead of
// the random distribution `applyScenarios` used across the old 50-user pool.
// Each targets a fresh tag, so `usersWithFewestTags` (scenarios/types.ts)
// deterministically lands on a different user every time, in this order.
const DEMO_SCENARIOS = [shipmentStuck, doublePayment, failedPayment];

export function runSeed(): Database {
  initFaker();
  resetIdCounter();
  const db = createEmptyDB();

  // ── Merchants ──────────────────────────────────────────────
  const merchants = makeMerchants();
  for (const m of merchants) db.merchants.set(m.id, m);

  // ── Usuarios de demo ─────────────────────────────────────────
  for (const demoUser of DEMO_USERS) {
    const user = makeUser({ ...demoUser, status: "active", kycStatus: "verified" });
    db.users.set(user.id, user);

    const address = makeAddress(user.id);
    address.isDefault = true;
    db.addresses.set(address.id, address);

    const paymentMethod = makePaymentMethod(user.id);
    paymentMethod.isDefault = true;
    db.paymentMethods.set(paymentMethod.id, paymentMethod);

    const credit = makeCreditAccount(user.id);
    const basePoints = randomPointsForTier();
    const membership = makeMembership(user.id, basePoints);

    if (basePoints > 0) {
      db.pointsTransactions.push({
        id: id("pts"),
        userId: user.id,
        type: "earned",
        amount: 500,
        source: "signup_bonus",
        referenceId: null,
        description: "Welcome bonus points",
        createdAt: user.createdAt,
      });
    }

    // ── Órdenes ──────────────────────────────────────────────
    const orderCount = randInt(3, 5);
    const userAllInstallments: Installment[] = [];
    let totalSpent = 0;

    for (let o = 0; o < orderCount; o++) {
      const merchant = pick(merchants);
      const ctx = generateOrder(user, merchant, address, paymentMethod, credit);
      if (!ctx) continue;

      db.orders.set(ctx.order.id, ctx.order);
      db.installments.push(...ctx.installments);
      db.shipments.set(ctx.shipment.id, ctx.shipment);
      db.transactions.push(...ctx.transactions);
      db.pointsTransactions.push(...ctx.pointsTxns);

      userAllInstallments.push(...ctx.installments);
      const paid = ctx.installments.filter((x) => x.status === "paid").reduce((s, x) => s + x.amountDue, 0);
      totalSpent += paid;
    }

    // ── Recalcular derivados ─────────────────────────────────
    const updatedCredit = recalcCreditAccount(credit, userAllInstallments);
    if (updatedCredit.outstandingBalance > updatedCredit.creditLimit) {
      updatedCredit.creditLimit = updatedCredit.outstandingBalance + Math.round(updatedCredit.outstandingBalance * 0.3);
      updatedCredit.availableCredit = updatedCredit.creditLimit - updatedCredit.outstandingBalance;
      updatedCredit.utilizationPct = Math.round((updatedCredit.outstandingBalance / updatedCredit.creditLimit) * 10000) / 100;
    }
    db.creditAccounts.set(updatedCredit.id, updatedCredit);

    const allUserPoints = db.pointsTransactions.filter((p) => p.userId === user.id);
    const updatedMembership = recalcMembership(membership, allUserPoints, totalSpent);
    db.memberships.set(updatedMembership.id, updatedMembership);
  }

  // ── Aplicar un escenario de anomalía conocido por usuario ───
  for (const scenario of DEMO_SCENARIOS) {
    scenario.apply(db);
  }

  // ── Generar pagos pendientes de validación ──────────────────
  // Para cada usuario con cuotas impagas, crear 0–2 payments pending_validation.
  // Esto da material para que el endpoint POST /payments/validate funcione.
  for (const user of db.users.values()) {
    const unpaid = db.installments.filter(
      (i) => i.userId === user.id && i.status !== "paid" && i.status !== "failed",
    );
    if (unpaid.length === 0) continue;
    const count = Math.min(unpaid.length, randInt(0, 2));
    for (let p = 0; p < count; p++) {
      const inst = pick(unpaid);
      const payment = makePendingPayment(user.id, inst);
      db.payments.set(payment.id, payment);
    }
  }

  setDB(db);
  return db;
}

// Seeded via `f` (faker.seed(SEED) in initFaker) — deterministic across
// restarts, unlike the old orchestration which used raw Math.random() here.
function randInt(min: number, max: number): number {
  return Math.floor(f.number.float({ min, max: max + 1 - 0.0001 }));
}

function pick<T>(arr: T[]): T {
  return arr[Math.floor(f.number.float({ min: 0, max: arr.length - 0.0001 }))]!;
}

/** Conveniencia: re-seed desde cero. */
export function reseed(): Database {
  return runSeed();
}

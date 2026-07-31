/**
 * Orquestador del seed: genera el dataset completo de 50 usuarios
 * con todo su árbol de entidades (direcciones, pagos, crédito, membresía,
 * órdenes, cuotas, envíos, transacciones, puntos).
 */

import { initFaker } from "./faker.js";
import { resetIdCounter, id } from "../utils/id.js";
import { createEmptyDB, setDB, type Database } from "../db.js";
import {
  makeMerchants, makeUser, makeAddress, makePaymentMethod,
  makeCreditAccount, makeMembership, randomPointsForTier,
  generateOrder, recalcCreditAccount, recalcMembership,
  isoDaysAgo, nowISO, makePendingPayment,
} from "./generators.js";
import type { User, Order, Installment } from "../schema/index.js";
import { applyScenarios } from "./scenarios/index.js";

export const SEED_USER_COUNT = 50;

export function runSeed(): Database {
  initFaker();
  resetIdCounter();
  const db = createEmptyDB();

  // ── Merchants ──────────────────────────────────────────────
  const merchants = makeMerchants();
  for (const m of merchants) db.merchants.set(m.id, m);

  // ── Usuarios ───────────────────────────────────────────────
  for (let i = 0; i < SEED_USER_COUNT; i++) {
    const user = makeUser();
    db.users.set(user.id, user);

    // Direcciones: 1–2
    const addrCount = 1 + (i % 3 === 0 ? 1 : 0);
    const addresses = [];
    for (let a = 0; a < addrCount; a++) {
      const addr = makeAddress(user.id);
      if (a === 0) addr.isDefault = true;
      db.addresses.set(addr.id, addr);
      addresses.push(addr);
    }

    // Métodos de pago: 1–3
    const pmCount = 1 + (i % 4); // 1–4... ajustar a 1-3
    const paymentMethods = [];
    for (let p = 0; p < Math.min(pmCount, 3); p++) {
      const pm = makePaymentMethod(user.id);
      if (p === 0) pm.isDefault = true;
      db.paymentMethods.set(pm.id, pm);
      paymentMethods.push(pm);
    }

    // Cuenta de crédito
    const credit = makeCreditAccount(user.id);
    db.creditAccounts.set(credit.id, credit);

    // Membresía — puntos base aleatorios por tier
    const basePoints = randomPointsForTier();
    const membership = makeMembership(user.id, basePoints);
    db.memberships.set(membership.id, membership);

    // Puntos de signup bonus para algunos
    if (basePoints > 0 && i % 5 === 0) {
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
    const orderCount = i < 5 ? randOrderCount(4, 8)
      : i < 20 ? randOrderCount(1, 5)
      : i < 35 ? randOrderCount(0, 3)
      : randOrderCount(0, 2);

    const userAllInstallments: Installment[] = [];
    let totalSpent = 0;

    for (let o = 0; o < orderCount; o++) {
      const merchant = merchants[Math.floor(Math.random() * merchants.length)]!;
      const address = addresses[Math.floor(Math.random() * addresses.length)]!;
      const pm = paymentMethods[Math.floor(Math.random() * paymentMethods.length)]!;

      const ctx = generateOrder(user, merchant, address, pm, credit);
      if (!ctx) continue;

      db.orders.set(ctx.order.id, ctx.order);
      db.installments.push(...ctx.installments);
      db.shipments.set(ctx.shipment.id, ctx.shipment);
      db.transactions.push(...ctx.transactions);
      db.pointsTransactions.push(...ctx.pointsTxns);

      userAllInstallments.push(...ctx.installments);
      // totalSpent = suma de cuotas pagadas
      const paid = ctx.installments.filter((x) => x.status === "paid").reduce((s, x) => s + x.amountDue, 0);
      totalSpent += paid;
    }

    // ── Recalcular derivados ─────────────────────────────────
    const updatedCredit = recalcCreditAccount(credit, userAllInstallments);
    // Si outstanding > creditLimit (por múltiples órdenes activas),
    // ajustar el creditLimit para que sea coherente.
    if (updatedCredit.outstandingBalance > updatedCredit.creditLimit) {
      updatedCredit.creditLimit = updatedCredit.outstandingBalance + Math.round(updatedCredit.outstandingBalance * 0.3);
      updatedCredit.availableCredit = updatedCredit.creditLimit - updatedCredit.outstandingBalance;
      updatedCredit.utilizationPct = Math.round((updatedCredit.outstandingBalance / updatedCredit.creditLimit) * 10000) / 100;
    }
    db.creditAccounts.set(updatedCredit.id, updatedCredit);

    // Recalcular membresía: puntos base + puntos de órdenes + signup
    const allUserPoints = db.pointsTransactions.filter((p) => p.userId === user.id);
    const updatedMembership = recalcMembership(membership, allUserPoints, totalSpent);
    db.memberships.set(updatedMembership.id, updatedMembership);
  }

  // ── Aplicar escenarios de anomalías ─────────────────────────
  applyScenarios(db);

  // ── Generar pagos pendientes de validación ──────────────────
  // Para cada usuario con cuotas impagas, crear 0–2 payments pending_validation.
  // Esto da material para que el endpoint POST /payments/validate funcione.
  for (const user of db.users.values()) {
    const unpaid = db.installments.filter(
      (i) => i.userId === user.id && i.status !== "paid" && i.status !== "failed",
    );
    if (unpaid.length === 0) continue;
    const count = Math.min(unpaid.length, Math.floor(Math.random() * 3)); // 0–2
    for (let p = 0; p < count; p++) {
      const inst = unpaid[Math.floor(Math.random() * unpaid.length)]!;
      const payment = makePendingPayment(user.id, inst);
      db.payments.set(payment.id, payment);
    }
  }

  setDB(db);
  return db;
}

function randOrderCount(min: number, max: number): number {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

/** Conveniencia: re-seed desde cero. */
export function reseed(): Database {
  return runSeed();
}

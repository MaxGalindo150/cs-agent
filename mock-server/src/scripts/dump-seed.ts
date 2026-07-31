/**
 * Vuelca el dataset completo a data/seed.json para inspección.
 * Uso: bun run seed:dump
 */

import { writeFileSync, mkdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { runSeed } from "../seed/seed.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const outPath = join(__dirname, "..", "..", "data", "seed.json");

console.log("🌱 Generating seed data...");
const db = runSeed();

const snapshot = {
  generatedAt: new Date().toISOString(),
  stats: {
    users: db.users.size,
    addresses: db.addresses.size,
    paymentMethods: db.paymentMethods.size,
    creditAccounts: db.creditAccounts.size,
    memberships: db.memberships.size,
    merchants: db.merchants.size,
    orders: db.orders.size,
    installments: db.installments.length,
    shipments: db.shipments.size,
    transactions: db.transactions.length,
    pointsTransactions: db.pointsTransactions.length,
    payments: db.payments.size,
    usersWithAnomalies: [...db.users.values()].filter((u) => u.scenarioTags.length > 0).length,
  },
  data: {
    users: [...db.users.values()],
    addresses: [...db.addresses.values()],
    paymentMethods: [...db.paymentMethods.values()],
    creditAccounts: [...db.creditAccounts.values()],
    memberships: [...db.memberships.values()],
    merchants: [...db.merchants.values()],
    orders: [...db.orders.values()],
    installments: db.installments,
    shipments: [...db.shipments.values()],
    transactions: db.transactions,
    pointsTransactions: db.pointsTransactions,
    payments: [...db.payments.values()],
  },
};

mkdirSync(dirname(outPath), { recursive: true });
writeFileSync(outPath, JSON.stringify(snapshot, null, 2));
console.log(`✅ Written to ${outPath}`);
console.log(`   Stats:`, snapshot.stats);

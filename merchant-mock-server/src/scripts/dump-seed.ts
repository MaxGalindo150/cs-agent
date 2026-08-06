// ── Seed dump script ───────────────────────────────────────────────
// Genera data/seed.json con el dataset completo (`bun run seed:dump`).

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { getDB } from "../db.js";
import { runSeed } from "../seed/seed.js";

// Ejecutar seed antes de dumpear
runSeed();

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const outputDir = path.join(__dirname, "..", "..", "data");
const outputFile = path.join(outputDir, "seed.json");

const db = getDB();

const dump = {
  generatedAt: new Date().toISOString(),
  stats: {
    merchants: db.merchants.size,
    stores: db.stores.size,
    employees: db.employees.size,
    orders: db.orders.size,
    installments: db.installments.length,
    dailyConciliations: db.dailyConciliations.length,
    monthlyReports: db.monthlyReports.length,
    payouts: db.payouts.length,
    invoices: db.invoices.length,
    promotions: db.promotions.length,
    pos: db.pos.length,
    paymentMethods: db.paymentMethods.length,
    products: db.products.length,
    inventoryJobs: db.inventoryJobs.length,
    onboardings: db.onboardings.size,
    reports: db.reports.length,
    movements: db.movements.length,
  },
  data: {
    merchants: [...db.merchants.values()],
    stores: [...db.stores.values()],
    employees: [...db.employees.values()],
    orders: [...db.orders.values()],
    installments: db.installments,
    dailyConciliations: db.dailyConciliations,
    monthlyReports: db.monthlyReports,
    payouts: db.payouts,
    invoices: db.invoices,
    promotions: db.promotions,
    pos: db.pos,
    paymentMethods: db.paymentMethods,
    products: db.products,
    inventoryJobs: db.inventoryJobs,
    onboardings: [...db.onboardings.values()],
    reports: db.reports,
    movements: db.movements,
  },
};

fs.mkdirSync(outputDir, { recursive: true });
fs.writeFileSync(outputFile, JSON.stringify(dump, null, 2));
console.log(`📄 Seed dump written to ${outputFile}`);
console.log(`   Stats:`, dump.stats);

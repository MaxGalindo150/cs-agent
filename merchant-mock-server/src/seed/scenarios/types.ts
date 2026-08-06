import type { Database } from "../../db.js";

// ── Scenario interface ─────────────────────────────────────────────
// Igual que el mock BNPL: cada escenario muta la DB para crear una
// anomalía observable y etiqueta la entidad afectada.

export interface Scenario {
  tag: string;
  description: string;
  apply(db: Database): void;
}

// ── Helpers ────────────────────────────────────────────────────────

function tagMerchant(db: Database, merchantId: number, tag: string): void {
  const m = db.merchants.get(merchantId);
  if (m && !m.scenarioTags.includes(tag)) {
    m.scenarioTags.push(tag);
  }
}

function tagStore(db: Database, storeUuid: string, tag: string): void {
  const s = db.stores.get(storeUuid);
  if (s && !s.scenarioTags.includes(tag)) {
    s.scenarioTags.push(tag);
  }
}

function tagEmployee(db: Database, employeeId: string, tag: string): void {
  const e = db.employees.get(employeeId);
  if (e && !e.scenarioTags.includes(tag)) {
    e.scenarioTags.push(tag);
  }
}

function tagOrder(db: Database, orderNumber: string, tag: string): void {
  const o = db.orders.get(orderNumber);
  if (o && !o.scenarioTags.includes(tag)) {
    o.scenarioTags.push(tag);
  }
}

function tagPayout(db: Database, payoutId: string, tag: string): void {
  const p = db.payouts.find((p) => p.id === payoutId);
  if (p && !p.scenarioTags.includes(tag)) {
    p.scenarioTags.push(tag);
  }
}

function tagInvoice(db: Database, invoiceId: string, tag: string): void {
  const i = db.invoices.find((i) => i.id === invoiceId);
  if (i && !i.scenarioTags.includes(tag)) {
    i.scenarioTags.push(tag);
  }
}

function tagPOS(db: Database, posUuid: string, tag: string): void {
  const p = db.pos.find((p) => p.posUuid === posUuid);
  if (p && !p.scenarioTags.includes(tag)) {
    p.scenarioTags.push(tag);
  }
}

function tagOnboarding(db: Database, onboardingId: string, tag: string): void {
  const o = db.onboardings.get(onboardingId);
  if (o && !o.scenarioTags.includes(tag)) {
    o.scenarioTags.push(tag);
  }
}

// Encontrar primer merchant con menos scenario tags
function merchantsByFewestTags(db: Database, excludeTags: string[] = []): number[] {
  return [...db.merchants.values()]
    .filter((m) => m.status === "ACTIVE")
    .filter((m) => !excludeTags.some((t) => m.scenarioTags.includes(t)))
    .sort((a, b) => a.scenarioTags.length - b.scenarioTags.length)
    .map((m) => m.id);
}

// Encontrar primer empleado de cierto rol con menos tags
function employeesByRole(
  db: Database,
  role: string,
  merchantId?: number,
): import("../../schema/entities.js").Employee[] {
  return [...db.employees.values()]
    .filter((e) => e.role === role)
    .filter((e) => merchantId === undefined || e.merchantId === merchantId)
    .sort((a, b) => a.scenarioTags.length - b.scenarioTags.length);
}

// Encontrar órdenes por estado
function ordersByStatus(
  db: Database,
  merchantId: number,
  status: string,
): import("../../schema/entities.js").Order[] {
  return [...db.orders.values()].filter(
    (o) => o.merchantId === merchantId && o.status === status,
  );
}

export const scenarioHelpers = {
  tagMerchant,
  tagStore,
  tagEmployee,
  tagOrder,
  tagPayout,
  tagInvoice,
  tagPOS,
  tagOnboarding,
  merchantsByFewestTags,
  employeesByRole,
  ordersByStatus,
};

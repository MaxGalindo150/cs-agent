import type {
  Merchant,
  Store,
  Employee,
  Order,
  OrderInstallment,
  DailyConciliation,
  MonthlyReport,
  Payout,
  Invoice,
  Promotion,
  POS,
  PaymentMethod,
  Product,
  InventoryJob,
  Onboarding,
  Report,
  Movement,
} from "./schema/index.js";
import { rifDigits } from "./utils/rif.js";

// ── Database interface ─────────────────────────────────────────────
// Map = keyed entities (lookup por id/uuid)
// Array = colecciones sin key natural o que requieren filtering

export interface Database {
  merchants: Map<number, Merchant>;
  stores: Map<string, Store>;
  employees: Map<string, Employee>;
  orders: Map<string, Order>; // keyed by orderNumber
  installments: OrderInstallment[];
  dailyConciliations: DailyConciliation[];
  monthlyReports: MonthlyReport[];
  payouts: Payout[];
  invoices: Invoice[];
  promotions: Promotion[];
  promotionEnrollments: Map<string, Promotion["enrollmentStatus"]>;
  otpChallenges: Map<string, number>;
  pos: POS[];
  paymentMethods: PaymentMethod[];
  products: Product[];
  inventoryJobs: InventoryJob[];
  onboardings: Map<string, Onboarding>;
  reports: Report[];
  movements: Movement[];
}

function createEmptyDB(): Database {
  return {
    merchants: new Map(),
    stores: new Map(),
    employees: new Map(),
    orders: new Map(),
    installments: [],
    dailyConciliations: [],
    monthlyReports: [],
    payouts: [],
    invoices: [],
    promotions: [],
    promotionEnrollments: new Map(),
    otpChallenges: new Map(),
    pos: [],
    paymentMethods: [],
    products: [],
    inventoryJobs: [],
    onboardings: new Map(),
    reports: [],
    movements: [],
  };
}

// ── Singleton ──────────────────────────────────────────────────────

let db: Database = createEmptyDB();

export function getDB(): Database {
  return db;
}

export function setDB(newDB: Database): void {
  db = newDB;
}

export function resetDB(): void {
  db = createEmptyDB();
}

// ── Query helpers ──────────────────────────────────────────────────

export function findMerchant(id: number | string): Merchant | undefined {
  if (typeof id === "number") return db.merchants.get(id);
  // Si es string, intentar como número primero
  if (/^\d+$/.test(id)) {
    const numId = Number(id);
    if (db.merchants.has(numId)) return db.merchants.get(numId);
  }
  // Luego como UUID
  for (const m of db.merchants.values()) {
    if (m.uuid === id) return m;
  }
  return undefined;
}

export function findMerchantByRif(rif: string): Merchant | undefined {
  for (const m of db.merchants.values()) {
    if (rifDigits(rif) === rifDigits(m.rif)) return m;
  }
  return undefined;
}

export function merchantStores(merchantId: number): Store[] {
  return [...db.stores.values()].filter((s) => s.merchantId === merchantId);
}

export function merchantEmployees(merchantId: number): Employee[] {
  return [...db.employees.values()].filter((e) => e.merchantId === merchantId);
}

export function merchantOrders(merchantId: number): Order[] {
  return [...db.orders.values()].filter((o) => o.merchantId === merchantId);
}

export function merchantPayouts(merchantId: number): Payout[] {
  return db.payouts.filter((p) => p.merchantId === merchantId);
}

export function merchantInvoices(merchantId: number): Invoice[] {
  return db.invoices.filter((i) => i.merchantId === merchantId);
}

export function merchantMonthlyReports(merchantId: number): MonthlyReport[] {
  return db.monthlyReports.filter((r) => r.merchantId === merchantId);
}

export function merchantPromotions(merchantId: number): Promotion[] {
  // Las promociones globales no tienen merchantId; las específicas sí
  return db.promotions
    .filter((p) => p.merchantId === undefined || p.merchantId === merchantId)
    .map((promotion) => ({
      ...promotion,
      enrollmentStatus:
        db.promotionEnrollments.get(`${merchantId}:${promotion.id}`) ??
        promotion.enrollmentStatus,
    }));
}

export function setMerchantPromotionEnrollment(
  merchantId: number,
  promotionId: string,
  status: Promotion["enrollmentStatus"],
): void {
  db.promotionEnrollments.set(`${merchantId}:${promotionId}`, status);
}

export function storeOrders(storeUuid: string): Order[] {
  return [...db.orders.values()].filter((o) => o.storeUuid === storeUuid);
}

export function storeConciliations(storeUuid: string): DailyConciliation[] {
  return db.dailyConciliations.filter((c) => c.storeUuid === storeUuid);
}

export function storePOS(storeUuid: string): POS[] {
  return db.pos.filter((p) => p.storeUuid === storeUuid);
}

export function storePaymentMethods(storeUuid: string): PaymentMethod[] {
  return db.paymentMethods.filter((pm) => pm.storeUuid === storeUuid);
}

export function storeProducts(storeUuid: string): Product[] {
  return db.products.filter((p) => p.storeUuid === storeUuid);
}

export function storeInventoryJobs(storeUuid: string): InventoryJob[] {
  return db.inventoryJobs.filter((j) => j.storeUuid === storeUuid);
}

export function findStore(uuid: string): Store | undefined {
  return db.stores.get(uuid);
}

export function findOrder(orderNumber: string): Order | undefined {
  return db.orders.get(orderNumber);
}

export function findEmployee(id: string): Employee | undefined {
  return db.employees.get(id);
}

export function findPOS(uuid: string): POS | undefined {
  return db.pos.find((p) => p.posUuid === uuid);
}

export function orderInstallments(orderUuid: string): OrderInstallment[] {
  return db.installments
    .filter((i) => i.orderUuid === orderUuid)
    .sort((a, b) => a.installmentNumber - b.installmentNumber);
}

export function findPromotion(id: string): Promotion | undefined {
  return db.promotions.find((p) => p.id === id);
}

export function findOnboarding(id: string): Onboarding | undefined {
  return db.onboardings.get(id);
}

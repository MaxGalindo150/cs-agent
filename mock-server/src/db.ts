import type {
  User, Address, PaymentMethod, CreditAccount, Membership,
  PointsTransaction, Merchant, Order, Installment, Shipment, Transaction,
  Payment,
} from "../schema/index.js";

export interface Database {
  users: Map<string, User>;
  addresses: Map<string, Address>;
  paymentMethods: Map<string, PaymentMethod>;
  creditAccounts: Map<string, CreditAccount>;
  memberships: Map<string, Membership>;
  pointsTransactions: PointsTransaction[];
  merchants: Map<string, Merchant>;
  orders: Map<string, Order>;
  installments: Installment[];
  shipments: Map<string, Shipment>;
  transactions: Transaction[];
  payments: Map<string, Payment>;
}

export function createEmptyDB(): Database {
  return {
    users: new Map(),
    addresses: new Map(),
    paymentMethods: new Map(),
    creditAccounts: new Map(),
    memberships: new Map(),
    pointsTransactions: [],
    merchants: new Map(),
    orders: new Map(),
    installments: [],
    shipments: new Map(),
    transactions: [],
    payments: new Map(),
  };
}

// Singleton — vive mientras el proceso vive. Reseteable vía resetDB().
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

// ── Helpers de consulta frecuentes ──────────────────────────────────
export function findUser(id: string): User | undefined {
  return db.users.get(id);
}

export function userOrders(userId: string): Order[] {
  return [...db.orders.values()].filter((o) => o.userId === userId);
}

export function userInstallments(userId: string): Installment[] {
  return db.installments.filter((i) => i.userId === userId);
}

export function orderInstallments(orderId: string): Installment[] {
  return db.installments
    .filter((i) => i.orderId === orderId)
    .sort((a, b) => a.number - b.number);
}

export function orderShipment(orderId: string): Shipment | undefined {
  return [...db.shipments.values()].find((s) => s.orderId === orderId);
}

export function userTransactions(userId: string): Transaction[] {
  return db.transactions.filter((t) => t.userId === userId);
}

export function userPointsTransactions(userId: string): PointsTransaction[] {
  return db.pointsTransactions.filter((t) => t.userId === userId);
}

export function userCreditAccount(userId: string): CreditAccount | undefined {
  return [...db.creditAccounts.values()].find((c) => c.userId === userId);
}

export function userMembership(userId: string): Membership | undefined {
  return [...db.memberships.values()].find((m) => m.userId === userId);
}

export function userPaymentMethods(userId: string): PaymentMethod[] {
  return [...db.paymentMethods.values()].filter((p) => p.userId === userId);
}

export function userAddresses(userId: string): Address[] {
  return [...db.addresses.values()].filter((a) => a.userId === userId);
}

export function userPayments(userId: string): Payment[] {
  return [...db.payments.values()].filter((p) => p.userId === userId);
}

export function findPaymentByReference(externalReference: string, userId: string): Payment | undefined {
  return [...db.payments.values()].find(
    (p) => p.externalReference === externalReference && p.userId === userId,
  );
}

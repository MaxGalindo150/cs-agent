/**
 * Generadores de entidades sintéticas.
 * Todo el dinero está en centavos (enteros).
 * Las fechas se generan relativas a `now` para que siempre se vean frescas.
 */

import { f } from "./faker.js";
import { id } from "../utils/id.js";
import {
  pointsForPayment,
  tierForPoints,
  tierProgressForPoints,
  pickWeightedTier,
  pointsRangeForTier,
} from "./tiers.js";
import type {
  User, Address, PaymentMethod, CreditAccount, Membership,
  Merchant, Order, OrderItem, Installment, Shipment, Transaction,
  PointsTransaction, Financing, OrderPlan, Tier, Payment,
} from "../schema/index.js";
import type { Carrier } from "../schema/index.js";

const NOW = Date.now();
const DAY = 86_400_000;

export function nowISO(): string {
  return new Date().toISOString();
}

export function isoDaysAgo(days: number): string {
  return new Date(NOW - days * DAY).toISOString();
}

export function isoDaysFromNow(days: number): string {
  return new Date(NOW + days * DAY).toISOString();
}

function pick<T>(arr: T[]): T {
  return arr[Math.floor(f.number.float({ min: 0, max: arr.length - 0.0001 }))];
}

function randInt(min: number, max: number): number {
  return f.number.int({ min, max });
}

function money(min: number, max: number): number {
  // centavos, múltiplos de 100
  return randInt(min, max) * 100;
}

// ── Merchants ───────────────────────────────────────────────────────

const MERCHANT_DATA: Array<{ name: string; category: string }> = [
  { name: "Cashea FCB", category: "electronics" },
  { name: "Cashea C.C. Sambil Valencia", category: "electronics" },
  { name: "Electrosak Catia La Mar", category: "electronics" },
  { name: "Electrosak Maracay", category: "electronics" },
  { name: "Rio Supermarket C.C. Plaza Mayor", category: "grocery" },
  { name: "Rio Supermarket Puente Real", category: "grocery" },
  { name: "Comeval Mercado Isabelica", category: "grocery" },
  { name: "Palacio del Blumer Carmen Sur Goajiros Sta Rosa 2 Val", category: "grocery" },
  { name: "Redu Av. 100 Plaza Bolivar Centro Valencia", category: "fashion" },
  { name: "Tienda Glow C.C. Cristal", category: "beauty" },
];

export function makeMerchants(): Merchant[] {
  return MERCHANT_DATA.map((m) => ({
    id: id("mch"),
    name: m.name,
    category: m.category,
    logoUrl: null,
    status: "active" as const,
    createdAt: isoDaysAgo(randInt(365, 730)),
  }));
}

// ── Users ───────────────────────────────────────────────────────────

export interface UserOverrides {
  firstName?: string;
  lastName?: string;
  email?: string;
  phone?: string;
  status?: User["status"];
  kycStatus?: User["kycStatus"];
}

/** Every field is optional and falls back to the seeded faker instance — the
 * demo seed (see seed.ts) passes fixed identity fields so its users have
 * memorable, stable names/emails across restarts. */
export function makeUser(overrides: UserOverrides = {}): User {
  const firstName = overrides.firstName ?? f.person.firstName();
  const lastName = overrides.lastName ?? f.person.lastName();
  return {
    id: id("usr"),
    email: overrides.email ?? f.internet.email({ firstName, lastName }).toLowerCase(),
    phone: overrides.phone ?? vePhone(),
    firstName,
    lastName,
    dob: new Date(f.date.birthdate({ min: 18, max: 75 })).toISOString(),
    status:
      overrides.status ??
      (f.number.float({ min: 0, max: 1 }) < 0.92 ? "active" : pick(["suspended", "blocked"])),
    kycStatus:
      overrides.kycStatus ??
      f.helpers.arrayElement(["verified", "verified", "verified", "pending", "unverified"]),
    avatarUrl: null,
    scenarioTags: [],
    createdAt: isoDaysAgo(randInt(30, 730)),
  };
}

// ── Data venezolana ─────────────────────────────────────────────────

const VE_CITIES: Array<{ city: string; state: string }> = [
  { city: "Caracas", state: "Distrito Capital" },
  { city: "Maracaibo", state: "Zulia" },
  { city: "Valencia", state: "Carabobo" },
  { city: "Maracay", state: "Aragua" },
  { city: "Barquisimeto", state: "Lara" },
  { city: "Mérida", state: "Mérida" },
  { city: "San Cristóbal", state: "Táchira" },
  { city: "Ciudad Bolívar", state: "Bolívar" },
  { city: "Puerto La Cruz", state: "Anzoátegui" },
  { city: "Punto Fijo", state: "Falcón" },
];

const VE_BANKS = [
  "Banco de Venezuela",
  "Banco Nacional de Crédito",
  "Banco Mercantil",
  "Banco Provincial (BBVA)",
  "Banesco",
  "Banco Sofitasa C.A.",
  "Banco Exterior",
  "Banco Bicentenario",
  "Bancaribe",
  "Banco del Tesoro",
];

const VE_MOBILE_PREFIXES = ["412", "414", "424", "416", "426"];

/** Genera un teléfono venezolano: +58 4XX XXXXXXX */
function vePhone(): string {
  const prefix = f.helpers.arrayElement(VE_MOBILE_PREFIXES);
  const rest = f.string.numeric({ length: 7 });
  return `+58${prefix}${rest}`;
}

/** Genera una cédula venezolana: V-XXXXXXX (7-8 dígitos) */
function veCedula(): string {
  const digits = f.string.numeric({ length: f.helpers.arrayElement([7, 8]) });
  return `V-${digits}`;
}

/** Genera una referencia bancaria venezolana: 8-12 dígitos numéricos */
function veBankReference(): string {
  return f.string.numeric({ length: f.helpers.arrayElement([8, 10, 12]) });
}

export function makeAddress(userId: string): Address {
  const loc = f.helpers.arrayElement(VE_CITIES);
  return {
    id: id("addr"),
    userId,
    type: f.helpers.arrayElement(["shipping", "billing"]),
    line1: f.location.streetAddress(),
    line2: f.helpers.maybe(() => f.location.secondaryAddress(), { probability: 0.3 }) ?? null,
    city: loc.city,
    state: loc.state,
    zip: f.string.numeric({ length: 4 }),
    country: "VE",
    isDefault: false,
    createdAt: isoDaysAgo(randInt(30, 730)),
  };
}

export function makePaymentMethod(userId: string): PaymentMethod {
  const isCard = f.number.float({ min: 0, max: 1 }) < 0.8;
  if (isCard) {
    return {
      id: id("pm"),
      userId,
      type: "card",
      brand: pick(["visa", "mastercard", "amex"] as const),
      bankName: null,
      last4: f.string.numeric({ length: 4 }),
      expiryMonth: randInt(1, 12),
      expiryYear: randInt(2026, 2031),
      isDefault: false,
      createdAt: isoDaysAgo(randInt(30, 730)),
    };
  }
  return {
    id: id("pm"),
    userId,
    type: "bank_account",
    brand: null,
    bankName: f.helpers.arrayElement(VE_BANKS),
    last4: f.string.numeric({ length: 4 }),
    expiryMonth: null,
    expiryYear: null,
    isDefault: false,
    createdAt: isoDaysAgo(randInt(30, 730)),
  };
}

// ── Credit account + membership ─────────────────────────────────────

export function makeCreditAccount(userId: string): CreditAccount {
  const creditLimit = pick([50000, 75000, 100000, 150000, 200000, 300000, 500000]);
  return {
    id: id("crd"),
    userId,
    creditLimit,
    outstandingBalance: 0, // se recalcula tras generar órdenes
    availableCredit: creditLimit,
    interestRate: f.number.float({ min: 0, max: 36, fractionDigits: 1 }),
    utilizationPct: 0,
    status: "active",
    createdAt: isoDaysAgo(randInt(30, 730)),
    updatedAt: nowISO(),
  };
}

export function makeMembership(userId: string, points: number): Membership {
  return {
    id: id("mbr"),
    userId,
    pointsBalance: points,
    tier: tierForPoints(points),
    tierProgress: tierProgressForPoints(points),
    totalSpent: 0, // se recalcula tras generar órdenes
    joinedAt: isoDaysAgo(randInt(30, 730)),
    updatedAt: nowISO(),
  };
}

export function randomPointsForTier(): number {
  const tier = pickWeightedTier();
  const range = pointsRangeForTier(tier);
  return randInt(range.min, range.max);
}

// ── Order lifecycle ────────────────────────────────────────────────

const PRODUCT_CATALOG: Record<string, Array<{ name: string; priceRange: [number, number] }>> = {
  grocery: [
    { name: "Canasta Básica Familiar", priceRange: [15, 60] },
    { name: "Ración Alimentaria (bulk)", priceRange: [8, 35] },
    { name: "Harina P.A.N. 1kg x6", priceRange: [10, 25] },
    { name: "Aceite Vegetal 1L x4", priceRange: [12, 30] },
    { name: "Carne de Res 1kg", priceRange: [8, 20] },
    { name: "Queso Blanco 500g x2", priceRange: [6, 18] },
    { name: "Productos de Limpieza Set", priceRange: [10, 40] },
  ],
  electronics: [
    { name: "Wireless Headphones Pro", priceRange: [80, 350] },
    { name: "Smart Watch Series 7", priceRange: [150, 500] },
    { name: "Bluetooth Speaker", priceRange: [40, 200] },
    { name: "USB-C Hub 8-in-1", priceRange: [25, 80] },
    { name: "4K Webcam", priceRange: [60, 250] },
    { name: "Mechanical Keyboard", priceRange: [70, 220] },
  ],
  fashion: [
    { name: "Denim Jacket Premium", priceRange: [45, 150] },
    { name: "Sneakers Urban Edition", priceRange: [60, 250] },
    { name: "Leather Wallet", priceRange: [20, 80] },
    { name: "Sunglasses Classic", priceRange: [30, 120] },
    { name: "Winter Coat", priceRange: [80, 400] },
  ],
  home: [
    { name: "Coffee Maker Deluxe", priceRange: [50, 300] },
    { name: "Robot Vacuum", priceRange: [120, 600] },
    { name: "Air Purifier HEPA", priceRange: [80, 350] },
    { name: "LED Desk Lamp", priceRange: [20, 90] },
    { name: "Espresso Machine", priceRange: [150, 800] },
  ],
  sports: [
    { name: "Yoga Mat Premium", priceRange: [20, 80] },
    { name: "Adjustable Dumbbells", priceRange: [80, 350] },
    { name: "Running Shoes Elite", priceRange: [70, 280] },
    { name: "Cycling Helmet", priceRange: [35, 150] },
  ],
  beauty: [
    { name: "Skincare Set Deluxe", priceRange: [40, 200] },
    { name: "Hair Dryer Ionic", priceRange: [35, 180] },
    { name: "Perfume Eau de Parfum", priceRange: [50, 250] },
    { name: "Makeup Palette Pro", priceRange: [25, 120] },
  ],
  toys: [
    { name: "Building Blocks 1000pc", priceRange: [30, 120] },
    { name: "RC Car Pro", priceRange: [40, 200] },
    { name: "Board Game Strategy", priceRange: [25, 80] },
  ],
  automotive: [
    { name: "Dash Cam 4K", priceRange: [50, 250] },
    { name: "Car Phone Mount", priceRange: [15, 50] },
    { name: "Tire Inflator Portable", priceRange: [30, 120] },
  ],
  books: [
    { name: "Bestseller Novel", priceRange: [12, 35] },
    { name: "Cookbook Deluxe Edition", priceRange: [20, 60] },
    { name: "Tech Reference Bundle", priceRange: [30, 90] },
  ],
  garden: [
    { name: "Garden Tool Set", priceRange: [25, 100] },
    { name: "Plant Pots Ceramic Set", priceRange: [20, 80] },
    { name: "Outdoor Solar Lights", priceRange: [15, 70] },
  ],
};

const PLAN_CONFIG: Record<OrderPlan, { count: number; intervalDays: number; apr: number }> = {
  pay_in_4: { count: 4, intervalDays: 14, apr: 0 },
  pay_in_30: { count: 1, intervalDays: 30, apr: 0 },
  monthly_3: { count: 3, intervalDays: 30, apr: 15 },
  monthly_6: { count: 6, intervalDays: 30, apr: 18 },
  monthly_12: { count: 12, intervalDays: 30, apr: 22 },
};

const CARRIERS: Carrier[] = ["dhl", "fedex", "ups", "estafeta", "local"];

interface OrderContext {
  order: Order;
  installments: Installment[];
  shipment: Shipment;
  transactions: Transaction[];
  pointsTxns: PointsTransaction[];
}

/** IDs de orden ya generados en este seed — evita colisiones silenciosas. */
const generatedOrderIds = new Set<string>();

/** Genera un ID de orden numérico de 9 dígitos, garantizando unicidad dentro del seed. */
function uniqueOrderId(): string {
  let candidate = f.string.numeric({ length: 9 });
  while (generatedOrderIds.has(candidate)) {
    candidate = f.string.numeric({ length: 9 });
  }
  generatedOrderIds.add(candidate);
  return candidate;
}

export function generateOrder(
  user: User,
  merchant: Merchant,
  address: Address,
  paymentMethod: PaymentMethod,
  creditAccount: CreditAccount,
): OrderContext | null {
  // Generar items del catálogo del merchant
  const catalog = PRODUCT_CATALOG[merchant.category] ?? PRODUCT_CATALOG.electronics;
  const itemCount = randInt(1, 4);
  const items: OrderItem[] = [];
  for (let i = 0; i < itemCount; i++) {
    const product = pick(catalog);
    items.push({
      sku: f.string.alphanumeric({ length: 8, casing: "upper" }),
      name: product.name,
      qty: randInt(1, 3),
      unitPrice: money(product.priceRange[0], product.priceRange[1]),
    });
  }

  const subtotal = items.reduce((sum, it) => sum + it.unitPrice * it.qty, 0);
  const shipping = subtotal > 5000 ? 0 : money(5, 15); // envío gratis > $50
  const tax = Math.round(subtotal * 0.16); // IVA 16%
  const totalAmount = subtotal + shipping + tax;

  // Plan aleatorio (pay_in_4 y monthly son los más comunes)
  const planRoll = f.number.float({ min: 0, max: 1 });
  const plan: OrderPlan = planRoll < 0.35 ? "pay_in_4"
    : planRoll < 0.45 ? "pay_in_30"
    : planRoll < 0.65 ? "monthly_3"
    : planRoll < 0.85 ? "monthly_6"
    : "monthly_12";

  const config = PLAN_CONFIG[plan];
  const apr = config.apr;

  // Financiamiento
  let interest = 0;
  let fees = 0;
  if (apr > 0) {
    interest = Math.round(totalAmount * (apr / 100) * (config.count / 12));
    fees = Math.round(totalAmount * 0.01); // 1% origination fee
  }

  const financing: Financing = {
    principal: totalAmount,
    interest,
    fees,
    apr,
    termMonths: config.count,
  };

  const orderAgeDays = randInt(1, 360);
  const createdAt = isoDaysAgo(orderAgeDays);

  // Determinar estado de la orden según antigüedad y plan
  const totalTermDays = config.count * config.intervalDays;
  const orderComplete = orderAgeDays > totalTermDays + 15; // margen

  let orderStatus: Order["status"];
  if (orderComplete) {
    orderStatus = "completed";
  } else {
    orderStatus = pick(["approved", "active", "active", "active"] as const);
  }

  const order: Order = {
    id: uniqueOrderId(),
    userId: user.id,
    merchantId: merchant.id,
    merchantName: merchant.name,
    items,
    subtotal,
    shipping,
    tax,
    totalAmount,
    plan,
    status: orderStatus,
    financing,
    installmentCount: config.count,
    refundRequested: false,
    refundReason: null,
    createdAt,
    updatedAt: createdAt,
  };

  // ── Generar cuotas ────────────────────────────────────────────
  const baseAmount = Math.round((totalAmount + interest + fees) / config.count);
  const installments: Installment[] = [];
  for (let i = 0; i < config.count; i++) {
    const dueDate = new Date(NOW - (orderAgeDays - (i + 1) * config.intervalDays) * DAY).toISOString();
    const isPast = new Date(dueDate).getTime() < NOW;

    let instStatus: Installment["status"];
    let paidDate: string | null = null;

    if (isPast) {
      if (orderComplete) {
        instStatus = "paid";
        paidDate = new Date(new Date(dueDate).getTime() + randInt(0, 3) * DAY).toISOString();
      } else if (f.number.float({ min: 0, max: 1 }) < 0.85) {
        instStatus = "paid";
        paidDate = new Date(new Date(dueDate).getTime() + randInt(0, 3) * DAY).toISOString();
      } else {
        instStatus = "overdue";
      }
    } else {
      // Cuota próxima con due_date cercano
      const daysUntilDue = Math.round((new Date(dueDate).getTime() - NOW) / DAY);
      instStatus = daysUntilDue <= 3 ? "due" : "upcoming";
    }

    installments.push({
      id: id("ins"),
      orderId: order.id,
      userId: user.id,
      number: i + 1,
      amountDue: baseAmount,
      principal: Math.round(totalAmount / config.count),
      interest: Math.round(interest / config.count),
      fees: i === 0 ? fees : 0, // fees en la primera cuota
      dueDate,
      paidDate,
      status: instStatus,
      paymentMethodId: instStatus === "paid" ? paymentMethod.id : null,
      externalReference: null,
    });
  }

  // ── Generar envío ──────────────────────────────────────────────
  const shipment = generateShipment(order, address, orderAgeDays, orderComplete);

  // ── Generar transacciones ─────────────────────────────────────
  const transactions: Transaction[] = [];

  // Transacción de compra
  transactions.push({
    id: id("txn"),
    userId: user.id,
    type: "purchase",
    direction: "debit",
    amount: totalAmount,
    description: `Purchase at ${merchant.name}`,
    referenceType: "order",
    referenceId: order.id,
    createdAt,
  });

  // Transacciones de pago (una por cuota pagada)
  const pointsTxns: PointsTransaction[] = [];
  for (const inst of installments) {
    if (inst.status === "paid" && inst.paidDate) {
      transactions.push({
        id: id("txn"),
        userId: user.id,
        type: "payment",
        direction: "credit",
        amount: inst.amountDue,
        description: `Payment - Installment ${inst.number}/${config.count} - ${merchant.name}`,
        referenceType: "installment",
        referenceId: inst.id,
        createdAt: inst.paidDate,
      });

      // Puntos ganados
      const pts = pointsForPayment(inst.amountDue);
      pointsTxns.push({
        id: id("pts"),
        userId: user.id,
        type: "earned",
        amount: pts,
        source: "order_payment",
        referenceId: inst.id,
        description: `Points earned - Installment ${inst.number} - ${merchant.name}`,
        createdAt: inst.paidDate,
      });
    }
  }

  return { order, installments, shipment, transactions, pointsTxns };
}

function generateShipment(order: Order, address: Address, orderAgeDays: number, isComplete: boolean): Shipment {
  const carrier = pick(CARRIERS);
  const trackingNumber = f.string.alphanumeric({ length: 12, casing: "upper" });
  const events: Shipment["events"] = [];

  let status: Shipment["status"] = "preparing";
  let shippedAt: string | null = null;
  let deliveredAt: string | null = null;
  let estimatedDelivery: string | null = null;

  const transitDays = randInt(3, 10);
  const shipDelayDays = randInt(1, 3); // días entre compra y envío

  if (orderAgeDays > shipDelayDays) {
    shippedAt = isoDaysAgo(orderAgeDays - shipDelayDays);
    status = "shipped";
    estimatedDelivery = isoDaysAgo(orderAgeDays - shipDelayDays - transitDays);

    events.push({
      status: "preparing",
      description: "Order received and being prepared",
      location: "Fulfillment Center",
      timestamp: isoDaysAgo(orderAgeDays),
    });
    events.push({
      status: "shipped",
      description: `Package handed to ${carrier.toUpperCase()}`,
      location: "Fulfillment Center",
      timestamp: shippedAt,
    });

    if (orderAgeDays > shipDelayDays + transitDays) {
      // Ya debería haber llegado
      if (isComplete) {
        deliveredAt = isoDaysAgo(orderAgeDays - shipDelayDays - transitDays);
        status = "delivered";
        events.push({
          status: "in_transit",
          description: "In transit to destination",
          location: f.location.city(),
          timestamp: isoDaysAgo(orderAgeDays - shipDelayDays - 1),
        });
        events.push({
          status: "out_for_delivery",
          description: "Out for delivery",
          location: f.location.city(),
          timestamp: isoDaysAgo(orderAgeDays - shipDelayDays - transitDays + 1),
        });
        events.push({
          status: "delivered",
          description: "Package delivered successfully",
          location: `${address.city}, ${address.state}`,
          timestamp: deliveredAt,
        });
      } else {
        // En tránsito normal
        status = "in_transit";
        events.push({
          status: "in_transit",
          description: "In transit to destination",
          location: f.location.city(),
          timestamp: isoDaysAgo(randInt(1, shipDelayDays)),
        });
      }
    } else {
      // Aún en tránsito
      status = "in_transit";
      events.push({
        status: "in_transit",
        description: "In transit to destination",
        location: f.location.city(),
        timestamp: isoDaysAgo(randInt(0, shipDelayDays)),
      });
    }
  } else {
    // Aún preparando
    estimatedDelivery = isoDaysFromNow(transitDays);
    events.push({
      status: "preparing",
      description: "Order received and being prepared",
      location: "Fulfillment Center",
      timestamp: isoDaysAgo(orderAgeDays),
    });
  }

  return {
    id: id("shp"),
    orderId: order.id,
    userId: order.userId,
    carrier,
    trackingNumber,
    status,
    address: {
      line1: address.line1,
      city: address.city,
      state: address.state,
      zip: address.zip,
      country: address.country,
    },
    estimatedDelivery,
    shippedAt,
    deliveredAt,
    events,
    createdAt: order.createdAt,
    updatedAt: events.length > 0 ? events[events.length - 1].timestamp : order.createdAt,
  };
}

// ── Recalcular derivados ───────────────────────────────────────────

export function recalcCreditAccount(account: CreditAccount, installments: Installment[]): CreditAccount {
  const outstanding = installments
    .filter((i) => i.status !== "paid")
    .reduce((sum, i) => sum + i.amountDue, 0);
  const available = account.creditLimit - outstanding;
  const utilization = account.creditLimit > 0
    ? Math.round((outstanding / account.creditLimit) * 10000) / 100
    : 0;

  return {
    ...account,
    outstandingBalance: outstanding,
    availableCredit: available,
    utilizationPct: utilization,
    updatedAt: nowISO(),
  };
}

export function recalcMembership(membership: Membership, pointsTxns: PointsTransaction[], totalSpent: number): Membership {
  const points = pointsTxns.reduce((sum, p) => sum + p.amount, 0);
  return {
    ...membership,
    pointsBalance: points,
    tier: tierForPoints(points),
    tierProgress: tierProgressForPoints(points),
    totalSpent,
    updatedAt: nowISO(),
  };
}

// ── Pagos pendientes de validación ─────────────────────────────────

/**
 * Crea un payment en estado `pending_validation` para una cuota impaga.
 * Estos son los pagos que el agente puede validar con `POST /payments/validate`.
 */
export function makePendingPayment(userId: string, installment: Installment): Payment {
  // Prefijo `10` — POST /payments/validate decide el desenlace por prefijo
  // (ver OUTCOME_BY_PREFIX en routes/payments.ts).
  const ref = `10${f.string.numeric({ length: 10 })}`;
  return {
    id: id("pmt"),
    userId,
    externalReference: ref,
    amount: installment.amountDue,
    currency: "VES",
    method: f.helpers.arrayElement(["bank_transfer", "bank_transfer", "card"]),

    status: "pending_validation",
    appliedTo: {
      installmentId: null,
      orderId: null,
      orderMerchantName: null,
      installmentNumber: null,
    },
    validatedAt: null,
    correctInstallmentId: null,
    createdAt: isoDaysAgo(randInt(1, 5)),
  };
}

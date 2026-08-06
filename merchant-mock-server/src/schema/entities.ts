// ── Esquemas de entidad — Fase A (placeholders mínimos) ────────────
// Estos esquemas se amplían con todos los campos del dominio en la Fase B.
// Por ahora definen la estructura mínima para que el Database interface
// y los routers puedan compilarse.

import { z } from "zod";
import { IsoDate, MerchantModel, MerchantStatus, FcbPeriod } from "./common.js";

// ── Merchant ───────────────────────────────────────────────────────
export const Merchant = z.object({
  id: z.number().int(),
  uuid: z.string(),
  rif: z.string(),
  legalName: z.string(),
  tradeName: z.string(),
  categoryId: z.number().int(),
  model: MerchantModel,
  merchantGroup: z.string().nullable(),
  status: MerchantStatus,
  activeFcb: z.boolean(),
  fcbPeriod: FcbPeriod,
  fcbStartDate: IsoDate.nullable(),
  adminEmail: z.string().email(),
  createdAt: IsoDate,
  scenarioTags: z.array(z.string()).default([]),
});
export type Merchant = z.infer<typeof Merchant>;

// ── Store ──────────────────────────────────────────────────────────
export const Store = z.object({
  id: z.number().int(),
  uuid: z.string(),
  merchantId: z.number().int(),
  name: z.string(),
  email: z.string().email().nullable(),
  statusId: z.union([z.literal(1), z.literal(2)]),
  channels: z.array(z.string()).default([]),
  isPhysical: z.boolean(),
  inventoryMigrated: z.boolean(),
  minimumDownPayment: z.number().int().nonnegative(),
  minimumFinanceableAmount: z.number().int().nonnegative().nullable(),
  address: z
    .object({
      name: z.string().nullable(),
      long: z.number().nullable(),
      lat: z.number().nullable(),
      location: z.string().nullable(),
      shipmentsEnabled: z.boolean(),
    })
    .nullable(),
  createdAt: IsoDate,
  scenarioTags: z.array(z.string()).default([]),
  // Flags internos para escenarios
  invoiceRegistrationFailing: z.boolean().default(false),
  orderCreateConnectionError: z.boolean().default(false),
});
export type Store = z.infer<typeof Store>;

// ── Employee ───────────────────────────────────────────────────────
export const Employee = z.object({
  id: z.string(),
  storeUuid: z.string(),
  merchantId: z.number().int(),
  name: z.string(),
  email: z.string().email(),
  role: z.enum(["ADMIN", "MANAGER", "CASHIER"]),
  onboardingStatus: z.enum([
    "IN_PROGRESS",
    "IN_PROGRESS_RTG",
    "FINISHED",
    "INACTIVE",
  ]),
  phoneRegistered: z.boolean(),
  phoneNumber: z.string().nullable(),
  mustChangePassword: z.boolean(),
  securityCodeSet: z.boolean(),
  lastLoginAt: IsoDate.nullable(),
  createdAt: IsoDate,
  scenarioTags: z.array(z.string()).default([]),
  // Flags internos para escenarios
  otpNeverArrives: z.boolean().default(false),
});
export type Employee = z.infer<typeof Employee>;

// ── Order (vista del aliado) ───────────────────────────────────────
export const Order = z.object({
  orderNumber: z.string(),
  uuid: z.string(),
  storeUuid: z.string(),
  merchantId: z.number().int(),
  status: z.enum(["IN_PROGRESS", "CLOSED", "OPEN", "CANCELLED", "PENDING"]),
  statusId: z.number().int(),
  channel: z.enum(["IN_STORE", "REMOTE", "OFFLINE", "IN_APP"]),
  deliveryType: z.string().nullable(),
  deliveryStatus: z.string(),
  shipmentStatus: z.string().nullable(),
  totalAmount: z.number().int().nonnegative(),
  downPaymentAmount: z.number().int().nonnegative(),
  financedAmount: z.number().int().nonnegative(),
  currency: z.string().default("USD"),
  products: z.array(
    z.object({
      id: z.string(),
      name: z.string(),
      quantity: z.number().int(),
      price: z.number().int(),
      priceAfterDiscount: z.number().int().nullable(),
    }),
  ),
  buyer: z.object({
    fullName: z.string().nullable(),
    identificationNumber: z.string().nullable(),
    phoneNumber: z.string().nullable(),
    email: z.string().nullable(),
  }),
  pos: z
    .object({
      name: z.string(),
      uuid: z.string().nullable(),
    })
    .nullable(),
  invoice: z.object({
    registered: z.boolean(),
    number: z.string().nullable(),
    registeredAt: IsoDate.nullable(),
  }),
  cancellationData: z
    .object({
      cancelledBy: z.string().nullable(),
      reason: z.string().nullable(),
      cancelledAt: IsoDate.nullable(),
    })
    .nullable(),
  createdAt: IsoDate,
  scenarioTags: z.array(z.string()).default([]),
});
export type Order = z.infer<typeof Order>;

// ── Installment / Payment ──────────────────────────────────────────
export const OrderInstallment = z.object({
  id: z.string(),
  orderUuid: z.string(),
  installmentNumber: z.number().int(),
  amount: z.number().int().nonnegative(),
  dueDate: IsoDate.nullable(),
  status: z.enum([
    "SCHEDULED",
    "DONE",
    "GRACED",
    "PENDING",
    "DELAYED",
    "RENEGOTIATED",
    "CANCELLED",
  ]),
  payments: z.array(
    z.object({
      paymentId: z.string(),
      assignedAmount: z.number().int().nonnegative(),
      paymentMethod: z.object({
        name: z.enum(["PAGO_MOVIL", "TRANSFERENCIA", "EFECTIVO", "TARJETA"]),
      }),
      paymentStatus: z.enum([
        "VERIFIED",
        "CANCELLED",
        "PENDING",
        "RETURNED",
      ]),
      referenceNumber: z.string().nullable(),
      amountVES: z.number().int().nullable(),
      paymentValidationDate: IsoDate.nullable(),
      createdAt: IsoDate,
    }),
  ),
});
export type OrderInstallment = z.infer<typeof OrderInstallment>;

// ── DailyConciliation ──────────────────────────────────────────────
export const DailyConciliation = z.object({
  id: z.number().int(),
  storeUuid: z.string(),
  createdAt: IsoDate,
  date: z.string(), // YYYY-MM-DD
  ordersCount: z.number().int(),
  totalChargedAmount: z.number().int().nonnegative(),
  totalFinancedAmount: z.number().int().nonnegative(),
  posConciliations: z.array(
    z.object({
      pos: z.object({ name: z.string(), uuid: z.string() }),
      ordersCount: z.number().int(),
      totalChargedAmount: z.number().int().nonnegative(),
      totalFinancedAmount: z.number().int().nonnegative(),
    }),
  ),
});
export type DailyConciliation = z.infer<typeof DailyConciliation>;

// ── MonthlyReport ──────────────────────────────────────────────────
export const MonthlyReport = z.object({
  merchantId: z.number().int(),
  period: z.object({ from: IsoDate, to: IsoDate }),
  periodLabel: z.string(), // "2024-07"
  compensation: z.object({
    totalAmount: z.number().int(),
    shouldMerchantPay: z.boolean(),
  }),
  paymentTimeline: z.array(
    z.object({
      stepKey: z.enum([
        "reportSent",
        "calculationConfirmed",
        "invoiceGenerated",
        "bankDeposit",
      ]),
      status: z.enum(["completed", "in-progress", "pending"]),
      date: IsoDate.nullable(),
    }),
  ),
  missedInstallments: z.object({
    amount: z.number().int(),
    expectedAmount: z.number().int(),
    receivedAmount: z.number().int(),
    advancedAmount: z.number().int(),
  }),
  serviceFee: z.object({
    amount: z.number().int(),
    techServicesAmount: z.number().int(),
    ivaAmount: z.number().int(),
    isrlRetainedAmount: z.number().int(),
  }),
  errorsAndAdjustments: z.object({
    amount: z.number().int(),
    paymentErrorsAmount: z.number().int(),
    periodAdjustmentsAmount: z.number().int(),
  }),
});
export type MonthlyReport = z.infer<typeof MonthlyReport>;

// ── Payout ─────────────────────────────────────────────────────────
export const Payout = z.object({
  id: z.string(),
  merchantId: z.number().int(),
  periodFrom: IsoDate,
  periodTo: IsoDate,
  periodLabel: z.string(),
  grossAmount: z.number().int().nonnegative(),
  serviceFee: z.number().int(),
  retentions: z.number().int(),
  adjustments: z.number().int(),
  netAmount: z.number().int(),
  status: z.enum(["PENDING", "SENT", "FAILED"]),
  sentAt: IsoDate.nullable(),
  bankReference: z.string().nullable(),
  bankAccountLast4: z.string(),
  scenarioTags: z.array(z.string()).default([]),
});
export type Payout = z.infer<typeof Payout>;

// ── Invoice ────────────────────────────────────────────────────────
export const Invoice = z.object({
  id: z.string(),
  merchantId: z.number().int(),
  period: z.object({ from: IsoDate, to: IsoDate }),
  periodLabel: z.string(),
  number: z.string(),
  amount: z.number().int().nonnegative(),
  iva: z.number().int().nonnegative(),
  isrlRetained: z.number().int().nonnegative(),
  status: z.enum(["ISSUED", "SENT", "NOT_SENT"]),
  sentToEmail: z.string().nullable(),
  sentAt: IsoDate.nullable(),
  pdfUrl: z.string(),
  scenarioTags: z.array(z.string()).default([]),
});
export type Invoice = z.infer<typeof Invoice>;

// ── Promotion ──────────────────────────────────────────────────────
export const Promotion = z.object({
  id: z.string(),
  title: z.string(),
  description: z.string().nullable(),
  status: z.enum(["ACTIVE", "INACTIVE"]),
  scheduleState: z.enum(["NOT_STARTED", "ACTIVE"]),
  startsAt: IsoDate.nullable(),
  endsAt: IsoDate.nullable(),
  enrollmentStatus: z.enum(["AVAILABLE", "JOINED", "NONE"]),
  mechanics: z.array(
    z.object({
      kind: z.enum(["DISCOUNT", "DP_REDUCTION", "EXTRA_INSTALLMENT_PLAN"]),
      label: z.string(),
    }),
  ),
  conditionGroups: z.array(
    z.object({
      id: z.string(),
      name: z.string(),
      conditions: z.array(
        z.object({
          kind: z.enum(["USER_LEVEL", "INCLUDED_MERCHANTS"]),
          label: z.string(),
        }),
      ),
    }),
  ),
  links: z.object({
    infoDocumentUrl: z.string().nullable(),
    termsAndConditionsUrl: z.string().nullable(),
  }),
  merchantId: z.number().int().optional(),
});
export type Promotion = z.infer<typeof Promotion>;

// ── POS ────────────────────────────────────────────────────────────
export const POS = z.object({
  posUuid: z.string(),
  name: z.string(),
  storeUuid: z.string(),
  merchantId: z.number().int(),
  qrLinked: z.boolean(),
  qrCode: z
    .object({
      activationCode: z.string(),
      status: z.enum(["AVAILABLE", "LINKED", "DELETED", "DISABLED"]),
    })
    .nullable(),
  lastOrderAt: IsoDate.nullable(),
  scenarioTags: z.array(z.string()).default([]),
});
export type POS = z.infer<typeof POS>;

// ── PaymentMethod ──────────────────────────────────────────────────
export const PaymentMethod = z.object({
  id: z.number().int(),
  storeUuid: z.string(),
  name: z.enum(["PAGO_MOVIL", "TRANSFERENCIA", "EFECTIVO", "TARJETA"]),
  type: z.string().nullable(),
  bankName: z.string().nullable(),
  bankHolder: z.string().nullable(),
  account: z.string().nullable(),
  accountType: z.string().nullable(),
  phoneNumber: z.string().nullable(),
  currencyId: z.number().int(),
  currency: z.object({ id: z.number().int(), name: z.string() }),
  category: z.string().default("IN_STORE"),
  fees: z.array(
    z.object({
      id: z.number().int(),
      amount: z.number().int(),
      type: z.string(),
      description: z.string().nullable(),
    }),
  ),
});
export type PaymentMethod = z.infer<typeof PaymentMethod>;

// ── Product / Inventory ────────────────────────────────────────────
export const Product = z.object({
  uuid: z.string(),
  storeUuid: z.string(),
  sku: z.string(),
  name: z.string(),
  price: z.number().int().nonnegative(),
  stock: z.number().int(),
  categoryId: z.number().int(),
  categoryName: z.string(),
  status: z.enum(["ACTIVE", "PAUSED"]),
  type: z.enum(["PHYSICAL", "DIGITAL"]),
  imgUrl: z.string().default(""),
});
export type Product = z.infer<typeof Product>;

export const InventoryJob = z.object({
  jobUuid: z.string(),
  storeUuid: z.string(),
  fileName: z.string(),
  status: z.enum([
    "PENDING",
    "PROCESSING",
    "COMPLETED",
    "FAILED",
    "COMPLETED_WITH_ERRORS",
  ]),
  createdAt: IsoDate,
  finishedAt: IsoDate.nullable(),
  totalProducts: z.number().int().nullable(),
  processedProducts: z.number().int().nullable(),
  successCount: z.number().int().nullable(),
  errorCount: z.number().int().nullable(),
  errors: z.array(
    z.object({
      fileRow: z.number().int().optional(),
      fileColumn: z.string(),
      error: z.string(),
      sku: z.string().optional(),
    }),
  ),
});
export type InventoryJob = z.infer<typeof InventoryJob>;

// ── Onboarding ─────────────────────────────────────────────────────
export const Onboarding = z.object({
  onboardingId: z.string(),
  merchantId: z.number().int().optional(),
  step: z.enum([
    "BASIC_INFO",
    "LEGAL_DOCUMENTS",
    "BANK_VERIFICATION",
    "PLAN_SELECTION",
    "CHANNEL_SETUP",
    "REVIEW",
    "COMPLETED",
  ]),
  status: z.enum(["IN_PROGRESS", "SUBMITTED", "APPROVED", "REJECTED"]),
  failedRules: z.array(z.string()),
  legalDocuments: z.array(
    z.object({
      name: z.string(),
      status: z.enum(["PENDING", "SIGNED"]),
    }),
  ),
  bankAccountVerified: z.boolean(),
  readyToGo: z.boolean(),
  plan: z.string().nullable(),
  channelsSelected: z.array(z.string()),
  createdAt: IsoDate,
  scenarioTags: z.array(z.string()).default([]),
});
export type Onboarding = z.infer<typeof Onboarding>;

// ── Report (reports-hub) ───────────────────────────────────────────
export const Report = z.object({
  id: z.string(),
  title: z.string(),
  description: z.string().nullable(),
  longDescription: z.string().nullable(),
  url: z.string(),
});
export type Report = z.infer<typeof Report>;

export const Movement = z.object({
  id: z.string(),
  title: z.string(),
  description: z.string().nullable(),
  longDescription: z.string().nullable(),
  url: z.string(),
  date: IsoDate,
});
export type Movement = z.infer<typeof Movement>;

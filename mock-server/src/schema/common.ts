import { z } from "zod";

// ── Dinero: siempre centavos (enteros) ──────────────────────────────
export const Money = z.number().int().nonnegative();
export type Money = z.infer<typeof Money>;

// ── Enums del dominio ──────────────────────────────────────────────
export const UserStatus = z.enum(["active", "suspended", "blocked"]);
export const KycStatus = z.enum(["unverified", "pending", "verified", "rejected"]);

export const AddressType = z.enum(["shipping", "billing"]);
export const PaymentMethodType = z.enum(["card", "bank_account"]);
export const CardBrand = z.enum(["visa", "mastercard", "amex"]);

export const CreditAccountStatus = z.enum(["active", "frozen", "closed"]);
export const Tier = z.enum(["bronze", "silver", "gold", "platinum"]);

export const PointsTxnType = z.enum(["earned", "redeemed", "expired", "adjusted"]);
export const PointsTxnSource = z.enum([
  "order_payment",
  "signup_bonus",
  "tier_bonus",
  "redemption",
  "refund",
  "adjustment",
]);

export const OrderStatus = z.enum([
  "pending", "approved", "active", "completed", "defaulted", "cancelled",
]);
export const OrderPlan = z.enum([
  "pay_in_4", "pay_in_30", "monthly_3", "monthly_6", "monthly_12",
]);

export const InstallmentStatus = z.enum([
  "upcoming", "due", "paid", "overdue", "failed",
]);

export const ShipmentStatus = z.enum([
  "preparing", "shipped", "in_transit", "out_for_delivery",
  "delivered", "returned", "failed",
]);
export const Carrier = z.enum(["dhl", "fedex", "ups", "estafeta", "local"]);

export const TxnType = z.enum([
  "purchase", "payment", "refund", "fee", "interest",
  "points_earned", "points_redeemed", "adjustment",
]);
export const TxnDirection = z.enum(["debit", "credit"]);

export const MerchantStatus = z.enum(["active", "inactive"]);

export const PaymentStatus = z.enum([
  "pending_validation", "validated", "reassigned",
]);
export const PaymentMethod = z.enum([
  "spei", "card", "cash", "bank_transfer",
]);

export const ScenarioTag = z.enum([
  "double_payment",
  "refund_pending",
  "shipment_stuck",
  "shipment_lost",
  "shipment_never_shipped",
  "payment_not_reflected",
  "missing_points",
  "partial_points",
  "stale_tier",
  "overdue_unnotified",
  "failed_payment",
  "overcharged",
  "phantom_order",
  "cancelled_but_charged",
  "payment_wrong_order",
]);

// ── Tipos de paginación ─────────────────────────────────────────────
export const PaginatedMeta = z.object({
  page: z.number().int(),
  limit: z.number().int(),
  total: z.number().int(),
  totalPages: z.number().int(),
});

// ── ISO timestamp helper ─────────────────────────────────────────────
export const IsoDate = z.string().datetime();

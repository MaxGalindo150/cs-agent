import { z } from "zod";

// ── Dinero ─────────────────────────────────────────────────────────
// Todos los montos son enteros en centavos. El campo `currency` indica
// la moneda ("USD" | "VES"). Varios objetos tienen monto dual:
// `amount` (USD-cents) y `amountVES` (VES-cents) porque los pagos
// reales llegan en bolívares con referenceNumber.

export const Money = z.number().int().nonnegative();
export type Money = z.infer<typeof Money>;

export const Currency = z.enum(["USD", "VES"]);
export type Currency = z.infer<typeof Currency>;

// ── Timestamps ─────────────────────────────────────────────────────
// ISO 8601 con zona horaria.

export const IsoDate = z.string().datetime();
export type IsoDate = z.infer<typeof IsoDate>;

// ── Paginación ─────────────────────────────────────────────────────

export const PaginatedMeta = z.object({
  page: z.number().int(),
  limit: z.number().int(),
  total: z.number().int(),
  totalPages: z.number().int(),
});
export type PaginatedMeta = z.infer<typeof PaginatedMeta>;

// ── Enums del dominio merchant ─────────────────────────────────────

// Modelo de merchant (BASE = tradicional, EXPRESS = factoraje)
export const MerchantModel = z.enum(["BASE", "EXPRESS"]);
export type MerchantModel = z.infer<typeof MerchantModel>;

// Período de FCB (Fondo de Compensación de Beneficios)
export const FcbPeriod = z.enum(["WEEKLY", "BI_WEEKLY", "DAILY"]);
export type FcbPeriod = z.infer<typeof FcbPeriod>;

// Estado de merchant
export const MerchantStatus = z.enum(["ACTIVE", "INACTIVE", "SUSPENDED"]);
export type MerchantStatus = z.infer<typeof MerchantStatus>;

// Estado de tienda (1=INACTIVE, 2=ACTIVE)
export const StoreStatusId = z.union([z.literal(1), z.literal(2)]);
export type StoreStatusId = z.infer<typeof StoreStatusId>;

// Canales de tienda
export const StoreChannel = z.enum([
  "IN_APP",
  "IN_STORE",
  "DELIVERY",
  "REMOTE",
  "OFFLINE",
]);
export type StoreChannel = z.infer<typeof StoreChannel>;

// Roles de empleado
export const EmployeeRole = z.enum(["ADMIN", "MANAGER", "CASHIER"]);
export type EmployeeRole = z.infer<typeof EmployeeRole>;

// Estado de onboarding de empleado
export const EmployeeOnboardingStatus = z.enum([
  "IN_PROGRESS",
  "IN_PROGRESS_RTG",
  "FINISHED",
  "INACTIVE",
]);
export type EmployeeOnboardingStatus = z.infer<typeof EmployeeOnboardingStatus>;

// Estado de orden (ids: 1=IN_PROGRESS, 2=CLOSED, 3=OPEN, 4=CANCELLED, 7=PENDING)
export const OrderStatus = z.enum([
  "IN_PROGRESS",
  "CLOSED",
  "OPEN",
  "CANCELLED",
  "PENDING",
]);
export type OrderStatus = z.infer<typeof OrderStatus>;

// Canal de orden
export const OrderChannel = z.enum([
  "IN_STORE", // QR
  "REMOTE", // Link
  "OFFLINE", // Sin conexión
  "IN_APP", // Online
]);
export type OrderChannel = z.infer<typeof OrderChannel>;

// Tipo de entrega
export const DeliveryType = z.enum([
  "IN_STORE",
  "AGREE_WITH_STORE",
  "MMC_IN_STORE",
  "SHIPMENT",
]);
export type DeliveryType = z.infer<typeof DeliveryType>;

// Estado de entrega
export const DeliveryStatus = z.enum([
  "TO_DELIVER",
  "DELIVERED",
  "PENDING",
  "IN_TRANSIT",
  "RETURNED",
  "CANCELLED",
  "NOT_APPLICABLE",
]);
export type DeliveryStatus = z.infer<typeof DeliveryStatus>;

// Estado de envío (shipment)
export const ShipmentStatus = z.enum([
  "WAITING_CONFIRMATION",
  "READY_FOR_PICKUP",
  "PICKED_UP",
  "READY_FOR_DISPATCH",
  "DELIVERED",
  "IN_TRANSIT",
  "RETURNED_TO_STORE",
  "RETURNED_TO_AGENCY",
  "LOST_OR_STOLEN", // ← "Perdido/incidencia" en soporte
  "PROGRAMMED",
  "COMPLETED",
]);
export type ShipmentStatus = z.infer<typeof ShipmentStatus>;

// Estado de cuota
export const InstallmentStatus = z.enum([
  "SCHEDULED",
  "DONE",
  "GRACED",
  "PENDING",
  "DELAYED",
  "RENEGOTIATED",
  "CANCELLED",
]);
export type InstallmentStatus = z.infer<typeof InstallmentStatus>;

// Estado de pago de cuota
export const InstallmentPaymentStatus = z.enum([
  "VERIFIED",
  "CANCELLED",
  "PENDING",
  "RETURNED",
]);
export type InstallmentPaymentStatus = z.infer<typeof InstallmentPaymentStatus>;

// Método de pago
export const PaymentMethodName = z.enum([
  "PAGO_MOVIL",
  "TRANSFERENCIA",
  "EFECTIVO",
  "TARJETA",
]);
export type PaymentMethodName = z.infer<typeof PaymentMethodName>;

// Estado de payout (transferencia de Cashea al merchant)
export const PayoutStatus = z.enum(["PENDING", "SENT", "FAILED"]);
export type PayoutStatus = z.infer<typeof PayoutStatus>;

// Estado de factura
export const InvoiceStatus = z.enum(["ISSUED", "SENT", "NOT_SENT"]);
export type InvoiceStatus = z.infer<typeof InvoiceStatus>;

// Timeline steps del reporte mensual
export const TimelineStepKey = z.enum([
  "reportSent",
  "calculationConfirmed",
  "invoiceGenerated",
  "bankDeposit",
]);
export type TimelineStepKey = z.infer<typeof TimelineStepKey>;

export const TimelineStepStatus = z.enum(["completed", "in-progress", "pending"]);
export type TimelineStepStatus = z.infer<typeof TimelineStepStatus>;

// Promociones
export const PromotionStatus = z.enum(["ACTIVE", "INACTIVE"]);
export type PromotionStatus = z.infer<typeof PromotionStatus>;

export const PromotionScheduleState = z.enum(["NOT_STARTED", "ACTIVE"]);
export type PromotionScheduleState = z.infer<typeof PromotionScheduleState>;

export const PromotionEnrollmentStatus = z.enum(["AVAILABLE", "JOINED", "NONE"]);
export type PromotionEnrollmentStatus = z.infer<typeof PromotionEnrollmentStatus>;

export const PromotionMechanicKind = z.enum([
  "DISCOUNT",
  "DP_REDUCTION",
  "EXTRA_INSTALLMENT_PLAN",
]);
export type PromotionMechanicKind = z.infer<typeof PromotionMechanicKind>;

export const PromotionConditionKind = z.enum(["USER_LEVEL", "INCLUDED_MERCHANTS"]);
export type PromotionConditionKind = z.infer<typeof PromotionConditionKind>;

// Producto / inventario
export const ProductStatus = z.enum(["ACTIVE", "PAUSED"]);
export type ProductStatus = z.infer<typeof ProductStatus>;

export const ProductType = z.enum(["PHYSICAL", "DIGITAL"]);
export type ProductType = z.infer<typeof ProductType>;

export const JobStatus = z.enum([
  "PENDING",
  "PROCESSING",
  "COMPLETED",
  "FAILED",
  "COMPLETED_WITH_ERRORS",
]);
export type JobStatus = z.infer<typeof JobStatus>;

// QR
export const QrCodeStatus = z.enum(["AVAILABLE", "LINKED", "DELETED", "DISABLED"]);
export type QrCodeStatus = z.infer<typeof QrCodeStatus>;

// Onboarding
export const OnboardingStep = z.enum([
  "BASIC_INFO",
  "LEGAL_DOCUMENTS",
  "BANK_VERIFICATION",
  "PLAN_SELECTION",
  "CHANNEL_SETUP",
  "REVIEW",
  "COMPLETED",
]);
export type OnboardingStep = z.infer<typeof OnboardingStep>;

export const OnboardingStatus = z.enum([
  "IN_PROGRESS",
  "SUBMITTED",
  "APPROVED",
  "REJECTED",
]);
export type OnboardingStatus = z.infer<typeof OnboardingStatus>;

export const LegalDocumentStatus = z.enum(["PENDING", "SIGNED"]);
export type LegalDocumentStatus = z.infer<typeof LegalDocumentStatus>;

// Tags de escenario
export const ScenarioTag = z.enum([
  // Auth / 2FA
  "2fa_phone_not_registered",
  "2fa_phone_already_registered",
  "2fa_otp_never_arrives",
  "credentials_invite_not_delivered",
  "password_change_required",
  // Órdenes
  "security_code_not_set",
  "cashier_cannot_cancel",
  "cancel_out_of_day_window",
  "order_create_connection_error",
  "invoice_registration_failing",
  "order_incident_lost_shipment",
  "down_payment_not_reflected",
  // Financiero
  "payout_missing_for_period",
  "payout_amount_mismatch",
  "invoices_not_sent_multi_month",
  "isrl_retention_disputed",
  "daily_conciliation_mismatch",
  // Catálogo / configuración
  "pos_qr_not_linked",
  "promotion_not_eligible",
  "model_migration_pending",
  "onboarding_stuck_documents",
  "inventory_bulk_job_failed",
]);
export type ScenarioTag = z.infer<typeof ScenarioTag>;

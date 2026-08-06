import type { Scenario } from "./types.js";

// ── Auth / 2FA ─────────────────────────────────────────────────────
import {
  phoneNotRegistered,
  phoneAlreadyRegistered,
  otpNeverArrives,
  credentialsInviteNotDelivered,
  passwordChangeRequired,
} from "./auth-scenarios.js";

// ── Órdenes ────────────────────────────────────────────────────────
import {
  securityCodeNotSet,
  cashierCannotCancel,
  cancelOutOfDayWindow,
  orderCreateConnectionError,
  invoiceRegistrationFailing,
  orderIncidentLostShipment,
  downPaymentNotReflected,
} from "./order-scenarios.js";

// ── Financiero ─────────────────────────────────────────────────────
import {
  payoutMissingForPeriod,
  payoutAmountMismatch,
  invoicesNotSentMultiMonth,
  isrlRetentionDisputed,
  dailyConciliationMismatch,
} from "./financial-scenarios.js";

// ── Catálogo / configuración ───────────────────────────────────────
import {
  posQrNotLinked,
  promotionNotEligible,
  modelMigrationPending,
  onboardingStuckDocuments,
  inventoryBulkJobFailed,
} from "./catalog-scenarios.js";

// ── Catálogo completo de escenarios ────────────────────────────────
export const ALL_SCENARIOS: Scenario[] = [
  // Auth
  phoneNotRegistered,
  phoneAlreadyRegistered,
  otpNeverArrives,
  credentialsInviteNotDelivered,
  passwordChangeRequired,
  // Órdenes
  securityCodeNotSet,
  cashierCannotCancel,
  cancelOutOfDayWindow,
  orderCreateConnectionError,
  invoiceRegistrationFailing,
  orderIncidentLostShipment,
  downPaymentNotReflected,
  // Financiero
  payoutMissingForPeriod,
  payoutAmountMismatch,
  invoicesNotSentMultiMonth,
  isrlRetentionDisputed,
  dailyConciliationMismatch,
  // Catálogo
  posQrNotLinked,
  promotionNotEligible,
  modelMigrationPending,
  onboardingStuckDocuments,
  inventoryBulkJobFailed,
];

export const SCENARIO_DESCRIPTIONS: Record<string, string> = Object.fromEntries(
  ALL_SCENARIOS.map((s) => [s.tag, s.description]),
);

// ── Aplicar todos los escenarios al DB ─────────────────────────────
export function applyScenarios(db: import("../../db.js").Database): void {
  for (const scenario of ALL_SCENARIOS) {
    scenario.apply(db);
  }
}

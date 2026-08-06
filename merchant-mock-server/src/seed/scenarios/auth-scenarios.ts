import type { Scenario } from "./types.js";
import { scenarioHelpers as h } from "./types.js";

// ── Escenarios de autenticación / 2FA ──────────────────────────────

export const phoneNotRegistered: Scenario = {
  tag: "2fa_phone_not_registered",
  description:
    "Empleado admin con phoneRegistered=false — Reportes bloqueado por falta de 2FA",
  apply(db) {
    // Encontrar un ADMIN y forzar phoneRegistered=false
    const admins = h.employeesByRole(db, "ADMIN");
    for (const emp of admins) {
      emp.phoneRegistered = false;
      h.tagEmployee(db, emp.id, "2fa_phone_not_registered");
      return;
    }
  },
};

export const phoneAlreadyRegistered: Scenario = {
  tag: "2fa_phone_already_registered",
  description:
    "El teléfono que el aliado pide registrar ya es el suyo — no hay nada que cambiar",
  apply(db) {
    const admins = h.employeesByRole(db, "ADMIN");
    for (const emp of admins) {
      if (emp.phoneRegistered && emp.phoneNumber) {
        // Asegurar que el teléfono esté visible para que el agente lo compare
        h.tagEmployee(db, emp.id, "2fa_phone_already_registered");
        return;
      }
    }
  },
};

export const otpNeverArrives: Scenario = {
  tag: "2fa_otp_never_arrives",
  description:
    "send-code responde 200 pero verify-code siempre devuelve 409 code_expired",
  apply(db) {
    const admins = h.employeesByRole(db, "ADMIN");
    for (const emp of admins) {
      if (!emp.scenarioTags.includes("2fa_phone_not_registered")) {
        emp.otpNeverArrives = true;
        emp.phoneRegistered = true;
        h.tagEmployee(db, emp.id, "2fa_otp_never_arrives");
        return;
      }
    }
  },
};

export const credentialsInviteNotDelivered: Scenario = {
  tag: "credentials_invite_not_delivered",
  description:
    "Empleado IN_PROGRESS, lastLoginAt=null — invitación no entregada al email",
  apply(db) {
    const employees = [...db.employees.values()].filter(
      (e) => e.scenarioTags.length === 0,
    );
    for (const emp of employees) {
      emp.onboardingStatus = "IN_PROGRESS";
      emp.lastLoginAt = null;
      h.tagEmployee(db, emp.id, "credentials_invite_not_delivered");
      return;
    }
  },
};

export const passwordChangeRequired: Scenario = {
  tag: "password_change_required",
  description: "Empleado con mustChangePassword=true — debe cambiar contraseña",
  apply(db) {
    const employees = [...db.employees.values()].filter(
      (e) => e.scenarioTags.length === 0,
    );
    for (const emp of employees) {
      emp.mustChangePassword = true;
      h.tagEmployee(db, emp.id, "password_change_required");
      return;
    }
  },
};

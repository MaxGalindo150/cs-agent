import type { Scenario } from "./types.js";
import { scenarioHelpers as h } from "./types.js";
import { SEED_NOW } from "../faker.js";

// ── Escenarios de órdenes ──────────────────────────────────────────

export const securityCodeNotSet: Scenario = {
  tag: "security_code_not_set",
  description:
    "Gerente con securityCodeSet=false — no puede cancelar órdenes (falta código de seguridad)",
  apply(db) {
    const managers = h.employeesByRole(db, "MANAGER");
    for (const emp of managers) {
      emp.securityCodeSet = false;
      h.tagEmployee(db, emp.id, "security_code_not_set");
      return;
    }
  },
};

export const cashierCannotCancel: Scenario = {
  tag: "cashier_cannot_cancel",
  description:
    "Orden cancelable (IN_PROGRESS/PENDING/OPEN), empleado CASHIER intenta cancelar — 403",
  apply(db) {
    for (const emp of [...db.employees.values()].filter(
      (e) => e.role === "CASHIER" && e.scenarioTags.length === 0,
    )) {
      // Asegurar que hay una orden cancelable en su store
      const orders = [...db.orders.values()].filter(
        (o) =>
          o.storeUuid === emp.storeUuid &&
          ["IN_PROGRESS", "PENDING", "OPEN"].includes(o.status),
      );
      if (orders.length > 0) {
        h.tagEmployee(db, emp.id, "cashier_cannot_cancel");
        h.tagOrder(db, orders[0].orderNumber, "cashier_cannot_cancel");
        return;
      }
    }
  },
};

export const cancelOutOfDayWindow: Scenario = {
  tag: "cancel_out_of_day_window",
  description:
    "Gerente + orden de ayer — 409 out_of_day_window (solo mismo día)",
  apply(db) {
    const managers = h.employeesByRole(db, "MANAGER").filter(
      (e) => !e.scenarioTags.includes("security_code_not_set"),
    );
    for (const emp of managers) {
      // Buscar orden cancelable de ayer o más antigua en su store
      const today = new Date(SEED_NOW).toISOString().slice(0, 10);
      const orders = [...db.orders.values()].filter(
        (o) =>
          o.storeUuid === emp.storeUuid &&
          ["IN_PROGRESS", "PENDING", "OPEN"].includes(o.status) &&
          o.createdAt.slice(0, 10) !== today,
      );
      if (orders.length > 0) {
        emp.securityCodeSet = true;
        h.tagEmployee(db, emp.id, "cancel_out_of_day_window");
        h.tagOrder(db, orders[0].orderNumber, "cancel_out_of_day_window");
        return;
      }
    }
  },
};

export const orderCreateConnectionError: Scenario = {
  tag: "order_create_connection_error",
  description:
    "Store con flag orderCreateConnectionError — POST de creación falla con connection_error en paso 2",
  apply(db) {
    for (const store of [...db.stores.values()]) {
      if (store.scenarioTags.length === 0) {
        store.orderCreateConnectionError = true;
        h.tagStore(db, store.uuid, "order_create_connection_error");
        return;
      }
    }
  },
};

export const invoiceRegistrationFailing: Scenario = {
  tag: "invoice_registration_failing",
  description:
    "Orden CLOSED con invoice.registered=false — POST /invoice devuelve 503",
  apply(db) {
    for (const store of [...db.stores.values()]) {
      if (store.scenarioTags.length > 0) continue;
      const orders = h.ordersByStatus(db, store.merchantId, "CLOSED").filter(
        (o) => o.storeUuid === store.uuid && !o.invoice.registered,
      );
      if (orders.length > 0) {
        store.invoiceRegistrationFailing = true;
        h.tagStore(db, store.uuid, "invoice_registration_failing");
        h.tagOrder(db, orders[0].orderNumber, "invoice_registration_failing");
        return;
      }
    }
  },
};

export const orderIncidentLostShipment: Scenario = {
  tag: "order_incident_lost_shipment",
  description:
    "Orden con shipmentStatus en LOST_OR_STOLEN — 'Perdido/incidencia'",
  apply(db) {
    const closedOrders = [...db.orders.values()].filter(
      (o) =>
        o.scenarioTags.length === 0 &&
        o.deliveryType === "SHIPMENT" &&
        o.status !== "CANCELLED",
    );
    for (const order of closedOrders) {
      order.shipmentStatus = "LOST_OR_STOLEN";
      h.tagOrder(db, order.orderNumber, "order_incident_lost_shipment");
      return;
    }
  },
};

export const downPaymentNotReflected: Scenario = {
  tag: "down_payment_not_reflected",
  description:
    "Orden por LINK/REMOTE con pago móvil PENDING, referenceNumber + amountVES presentes, no conciliado",
  apply(db) {
    const remoteOrders = [...db.orders.values()].filter(
      (o) =>
        o.scenarioTags.length === 0 &&
        (o.channel === "REMOTE" || o.channel === "IN_APP") &&
        o.status !== "CANCELLED",
    );
    for (const order of remoteOrders) {
      // Encontrar la cuota 1 y marcar su pago como PENDING
      const insts = db.installments.filter(
        (i) => i.orderUuid === order.uuid && i.installmentNumber === 1,
      );
      for (const inst of insts) {
        if (inst.payments.length > 0) {
          // Cambiar el primer pago a PENDING
          inst.payments[0].paymentStatus = "PENDING";
          inst.payments[0].referenceNumber = "10234567890";
          inst.payments[0].amountVES = 58000; // ~$400 VES
          inst.payments[0].paymentValidationDate = null;
          inst.status = "PENDING";
          h.tagOrder(db, order.orderNumber, "down_payment_not_reflected");
          return;
        }
      }
    }
  },
};

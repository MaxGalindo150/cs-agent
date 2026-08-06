import { Hono } from "hono";
import { getDB } from "../db.js";
import { simulatedDelay } from "../utils/delay.js";

export const scenarioRoutes = new Hono();

// ── Catálogo de escenarios ─────────────────────────────────────────
// Devuelve todos los escenarios aplicados con los IDs reales de las
// entidades afectadas (merchants, stores, orders, employees, etc.)

scenarioRoutes.get("/", async (c) => {
  await simulatedDelay();
  const db = getDB();

  // Recolectar todas las tags presentes en el dataset
  const tagMap = new Map<string, {
    tag: string;
    description: string;
    affected: {
      merchants: number[];
      stores: string[];
      orders: string[];
      employees: string[];
      payouts: string[];
      invoices: string[];
      pos: string[];
      onboardings: string[];
    };
  }>();

  function collect(
    items: Iterable<{ scenarioTags?: string[] }>,
    kind: "merchants" | "stores" | "orders" | "employees" | "payouts" | "invoices" | "pos" | "onboardings",
    idFn: (item: any) => string | number,
  ) {
    for (const item of items as any) {
      if (!item.scenarioTags || item.scenarioTags.length === 0) continue;
      for (const tag of item.scenarioTags) {
        if (!tagMap.has(tag)) {
          tagMap.set(tag, {
            tag,
            description: SCENARIO_DESCRIPTIONS[tag] ?? "(sin descripción)",
            affected: {
              merchants: [],
              stores: [],
              orders: [],
              employees: [],
              payouts: [],
              invoices: [],
              pos: [],
              onboardings: [],
            },
          });
        }
        const entry = tagMap.get(tag)!;
        (entry.affected[kind] as (string | number)[]).push(idFn(item));
      }
    }
  }

  collect(db.merchants.values(), "merchants", (m) => m.id);
  collect(db.stores.values(), "stores", (s) => s.uuid);
  collect(db.orders.values(), "orders", (o) => o.orderNumber);
  collect(db.employees.values(), "employees", (e) => e.id);
  collect(db.payouts, "payouts", (p) => p.id);
  collect(db.invoices, "invoices", (i) => i.id);
  collect(db.pos, "pos", (p) => p.posUuid);
  collect(db.onboardings.values(), "onboardings", (o) => o.onboardingId);

  const scenarios = [...tagMap.values()].sort((a, b) =>
    a.tag.localeCompare(b.tag),
  );

  return c.json({ data: scenarios });
});

// ── Detalle de un escenario específico ─────────────────────────────
scenarioRoutes.get("/:tag", async (c) => {
  await simulatedDelay();
  const tag = c.req.param("tag");
  const db = getDB();

  const result: {
    tag: string;
    description: string;
    merchants: unknown[];
    stores: unknown[];
    orders: unknown[];
    employees: unknown[];
    payouts: unknown[];
    invoices: unknown[];
    pos: unknown[];
    onboardings: unknown[];
  } = {
    tag,
    description: SCENARIO_DESCRIPTIONS[tag] ?? "(sin descripción)",
    merchants: [],
    stores: [],
    orders: [],
    employees: [],
    payouts: [],
    invoices: [],
    pos: [],
    onboardings: [],
  };

  for (const m of db.merchants.values()) {
    if (m.scenarioTags.includes(tag)) result.merchants.push(m);
  }
  for (const s of db.stores.values()) {
    if (s.scenarioTags.includes(tag)) result.stores.push(s);
  }
  for (const o of db.orders.values()) {
    if (o.scenarioTags.includes(tag)) result.orders.push(o);
  }
  for (const e of db.employees.values()) {
    if (e.scenarioTags.includes(tag)) result.employees.push(e);
  }
  for (const p of db.payouts) {
    if (p.scenarioTags.includes(tag)) result.payouts.push(p);
  }
  for (const inv of db.invoices) {
    if (inv.scenarioTags.includes(tag)) result.invoices.push(inv);
  }
  for (const pos of db.pos) {
    if (pos.scenarioTags.includes(tag)) result.pos.push(pos);
  }
  for (const o of db.onboardings.values()) {
    if (o.scenarioTags.includes(tag)) result.onboardings.push(o);
  }

  const totalAffected =
    result.merchants.length +
    result.stores.length +
    result.orders.length +
    result.employees.length +
    result.payouts.length +
    result.invoices.length +
    result.pos.length +
    result.onboardings.length;

  if (totalAffected === 0) {
    return c.json({ error: `No hay entidades con el escenario ${tag}` }, 404);
  }

  return c.json(result);
});

// ── Descripciones de escenarios ────────────────────────────────────
const SCENARIO_DESCRIPTIONS: Record<string, string> = {
  // Auth / 2FA
  "2fa_phone_not_registered": "Empleado admin con phoneRegistered=false, reportes bloqueados",
  "2fa_phone_already_registered": "El teléfono que el aliado pide registrar ya es el suyo",
  "2fa_otp_never_arrives": "send-code responde 200 pero verify-code siempre devuelve 409 code_expired",
  "credentials_invite_not_delivered": "Empleado IN_PROGRESS con lastLoginAt=null, invitación no entregada",
  "password_change_required": "Empleado con mustChangePassword=true",
  // Órdenes
  "security_code_not_set": "Gerente con securityCodeSet=false, no puede cancelar órdenes",
  "cashier_cannot_cancel": "Orden cancelable, empleado CASHIER intenta cancelar",
  "cancel_out_of_day_window": "Gerente intenta cancelar orden de ayer, fuera de ventana del mismo día",
  "order_create_connection_error": "Store con flag que hace fallar la creación de orden con connection_error",
  "invoice_registration_failing": "Orden CLOSED con invoice.registered=false, POST /invoice devuelve 503",
  "order_incident_lost_shipment": "Orden con shipmentStatus en LOST_OR_STOLEN (Perdido/incidencia)",
  "down_payment_not_reflected": "Orden por LINK con pago móvil PENDING, referenceNumber + amountVES presentes, no conciliado",
  // Financiero
  "payout_missing_for_period": "Periodo cerrado, monthlyReport emitido, payout.status=PENDING sin sentAt",
  "payout_amount_mismatch": "payout.netAmount ≠ monthlyReport.compensation.totalAmount por un ajuste no explicado",
  "invoices_not_sent_multi_month": "5 meses consecutivos con invoice.status=NOT_SENT",
  "isrl_retention_disputed": "serviceFee.isrlRetainedAmount alto en un periodo, aliado lo reclama",
  "daily_conciliation_mismatch": "ordersCount no cuadra con las órdenes del día / un POS sin conciliar",
  // Catálogo
  "pos_qr_not_linked": "Caja creada sin QR vinculado",
  "promotion_not_eligible": "Promo ACTIVE con enrollmentStatus=NONE y condición INCLUDED_MERCHANTS que no incluye al merchant",
  "model_migration_pending": "Merchant BASE con solicitud a EXPRESS y contrato de cesión sin firmar",
  "onboarding_stuck_documents": "Onboarding con legalDocuments en PENDING y failedRules",
  "inventory_bulk_job_failed": "Job de carga masiva en FAILED con errores por fila",
};

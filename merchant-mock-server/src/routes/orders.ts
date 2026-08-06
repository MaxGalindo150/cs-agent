import { Hono } from "hono";
import { getDB, findOrder, findEmployee, orderInstallments } from "../db.js";
import { paginate, defaultPage, defaultLimit } from "../utils/response.js";
import { simulatedDelay } from "../utils/delay.js";
import { CANCELLATION_REASONS } from "../seed/catalogs.js";

export const orderRoutes = new Hono();

// ── Lista de órdenes con filtros ────────────────────────────────────
orderRoutes.get("/", async (c) => {
  await simulatedDelay();
  const query = c.req.query();
  const db = getDB();
  let items = [...db.orders.values()];

  if (query["storeUuid"]) {
    items = items.filter((o) => o.storeUuid === query["storeUuid"]);
  }
  if (query["merchantId"]) {
    const mid = parseInt(query["merchantId"], 10);
    items = items.filter((o) => o.merchantId === mid);
  }
  if (query["status"]) {
    items = items.filter((o) => o.status === query["status"]);
  }
  if (query["channel"]) {
    items = items.filter((o) => o.channel === query["channel"]);
  }
  if (query["from"]) {
    items = items.filter((o) => o.createdAt >= query["from"]!);
  }
  if (query["to"]) {
    items = items.filter((o) => o.createdAt <= query["to"]!);
  }
  if (query["scenario"]) {
    items = items.filter((o) => o.scenarioTags.includes(query["scenario"]!));
  }

  items.sort((a, b) => b.createdAt.localeCompare(a.createdAt));

  const page = defaultPage(query);
  const limit = defaultLimit(query);
  return c.json(paginate(items, page, limit));
});

// ── Motivos de cancelación ─────────────────────────────────────────
orderRoutes.get("/cancellation-reasons", async (c) => {
  await simulatedDelay();
  const query = c.req.query();
  let reasons = [...CANCELLATION_REASONS];
  // CASHIER no puede cancelar → no recibe motivos
  if (query["role"] === "CASHIER") {
    return c.json({ data: [] });
  }
  return c.json({ data: reasons });
});

// ── Detalle de orden por orderNumber ───────────────────────────────
orderRoutes.get("/:orderNumber", async (c) => {
  await simulatedDelay();
  const order = findOrder(c.req.param("orderNumber"));
  if (!order) {
    return c.json({ error: `No se encontró orden ${c.req.param("orderNumber")}` }, 404);
  }
  return c.json(order);
});

// ── Cuotas de una orden ────────────────────────────────────────────
orderRoutes.get("/:orderNumber/installments", async (c) => {
  await simulatedDelay();
  const order = findOrder(c.req.param("orderNumber"));
  if (!order) {
    return c.json({ error: `No se encontró orden ${c.req.param("orderNumber")}` }, 404);
  }
  const installments = orderInstallments(order.uuid);
  return c.json({ data: installments });
});

// ── Pagos de una orden ─────────────────────────────────────────────
orderRoutes.get("/:orderNumber/payments", async (c) => {
  await simulatedDelay();
  const order = findOrder(c.req.param("orderNumber"));
  if (!order) {
    return c.json({ error: `No se encontró orden ${c.req.param("orderNumber")}` }, 404);
  }
  const installments = orderInstallments(order.uuid);
  const payments = installments.flatMap((inst) =>
    inst.payments.map((pmt) => ({
      ...pmt,
      installmentNumber: inst.installmentNumber,
    })),
  );
  return c.json({ data: payments });
});

// ── POST: Cancelar orden ────────────────────────────────────────────
// Body: { employeeId, reasonId, securityCode? }
// Reglas de rol:
//   ADMIN    → sin restricción de fecha, sin código de seguridad
//   MANAGER  → requiere securityCode (6 dígitos), solo órdenes del mismo día
//   CASHIER  → no puede cancelar (403)

orderRoutes.post("/:orderNumber/cancel", async (c) => {
  await simulatedDelay();
  const order = findOrder(c.req.param("orderNumber"));
  if (!order) {
    return c.json({ error: `No se encontró orden ${c.req.param("orderNumber")}` }, 404);
  }

  let body: { employeeId?: string; reasonId?: number; securityCode?: string };
  try {
    body = await c.req.json();
  } catch {
    return c.json({ error: "Body inválido" }, 400);
  }

  if (!body || typeof body !== "object" || !body.employeeId) {
    return c.json({ error: "employeeId es obligatorio" }, 400);
  }

  const employee = findEmployee(body.employeeId);
  if (!employee) {
    return c.json({ error: `No se encontró empleado ${body.employeeId}` }, 404);
  }

  // El empleado debe pertenecer al mismo merchant de la orden
  if (employee.merchantId !== order.merchantId) {
    return c.json({ error: "El empleado no pertenece al merchant de la orden" }, 403);
  }
  if (employee.role !== "ADMIN" && employee.storeUuid !== order.storeUuid) {
    return c.json({ error: "El empleado no pertenece a la tienda de la orden" }, 403);
  }

  // Estado de la orden
  const cancellableStatuses = ["IN_PROGRESS", "PENDING", "OPEN"];
  if (order.status === "CANCELLED") {
    return c.json({ error: "order_already_cancelled", message: "La orden ya está cancelada" }, 409);
  }
  if (!cancellableStatuses.includes(order.status)) {
    return c.json({ error: "order_not_cancellable", message: `La orden en estado ${order.status} no se puede cancelar` }, 409);
  }

  // Reglas por rol
  if (employee.role === "CASHIER") {
    return c.json(
      { error: "role_not_allowed_to_cancel", message: "Los cajeros no tienen permiso para cancelar órdenes" },
      403,
    );
  }

  if (employee.role === "MANAGER") {
    // Verificar que tenga código de seguridad configurado
    if (!employee.securityCodeSet) {
      return c.json(
        { error: "security_code_not_set", message: "El gerente no tiene configurado el código de seguridad" },
        403,
      );
    }
    // Verificar código de seguridad
    if (!body.securityCode || !/^\d{6}$/.test(body.securityCode)) {
      return c.json(
        { error: "security_code_required", message: "Se requiere el código de seguridad de 6 dígitos" },
        403,
      );
    }
    if (body.securityCode !== "123456") {
      return c.json(
        { error: "invalid_security_code", message: "El código de seguridad es incorrecto" },
        409,
      );
    }
    // Verificar que la orden es del mismo día
    const today = new Date().toISOString().slice(0, 10);
    const orderDate = order.createdAt.slice(0, 10);
    if (orderDate !== today) {
      return c.json(
        { error: "out_of_day_window", message: "Los gerentes solo pueden cancelar órdenes del mismo día" },
        409,
      );
    }
  }

  // ADMIN: sin restricciones adicionales

  // Buscar el motivo
  const reason = CANCELLATION_REASONS.find((r) => r.id === body.reasonId);
  if (!reason) {
    return c.json(
      { error: "invalid_reason", message: "Debe indicar un reasonId válido" },
      400,
    );
  }

  // Aplicar la cancelación
  order.status = "CANCELLED";
  order.statusId = 4;
  order.deliveryStatus = "CANCELLED";
  order.cancellationData = {
    cancelledBy: employee.name,
    reason: reason.reason,
    cancelledAt: new Date().toISOString(),
  };
  order.scenarioTags = [...new Set([...order.scenarioTags])];

  // Cancelar cuotas
  const db = getDB();
  for (const inst of db.installments) {
    if (inst.orderUuid === order.uuid && inst.status !== "DONE") {
      inst.status = "CANCELLED";
    }
  }

  return c.json({
    status: "cancelled",
    orderNumber: order.orderNumber,
    cancelledBy: employee.name,
    reason: reason.reason,
  });
});

// ── POST: Registrar factura en orden ────────────────────────────────
// Body: { employeeId, invoiceNumber }

orderRoutes.post("/:orderNumber/invoice", async (c) => {
  await simulatedDelay();
  const order = findOrder(c.req.param("orderNumber"));
  if (!order) {
    return c.json({ error: `No se encontró orden ${c.req.param("orderNumber")}` }, 404);
  }

  let body: { employeeId?: string; invoiceNumber?: string };
  try {
    body = await c.req.json();
  } catch {
    return c.json({ error: "Body inválido" }, 400);
  }

  if (!body || typeof body !== "object" || !body.employeeId || !body.invoiceNumber) {
    return c.json({ error: "employeeId e invoiceNumber son obligatorios" }, 400);
  }

  const employee = findEmployee(body.employeeId);
  if (!employee) {
    return c.json({ error: `No se encontró empleado ${body.employeeId}` }, 404);
  }
  if (employee.merchantId !== order.merchantId) {
    return c.json({ error: "El empleado no pertenece al merchant de la orden" }, 403);
  }
  if (employee.role !== "ADMIN" && employee.storeUuid !== order.storeUuid) {
    return c.json({ error: "El empleado no pertenece a la tienda de la orden" }, 403);
  }
  if (employee.role === "CASHIER") {
    return c.json({ error: "role_not_allowed_to_register_invoice" }, 403);
  }
  if (order.status !== "CLOSED") {
    return c.json(
      { error: "order_not_closed", message: "Solo se facturan órdenes cerradas" },
      409,
    );
  }
  if (!/^[A-Za-z0-9-]{1,50}$/.test(body.invoiceNumber)) {
    return c.json({ error: "invoiceNumber inválido" }, 400);
  }

  // Verificar si la store tiene flag de fallo de registro de factura
  const db = getDB();
  const store = db.stores.get(order.storeUuid);
  if (store?.invoiceRegistrationFailing) {
    return c.json(
      { error: "invoice_registration_error", message: "Error al registrar la factura en el sistema. Intente más tarde." },
      503,
    );
  }

  if (order.invoice.registered) {
    return c.json(
      { error: "invoice_already_registered", message: "La orden ya tiene factura registrada" },
      409,
    );
  }

  order.invoice = {
    registered: true,
    number: body.invoiceNumber,
    registeredAt: new Date().toISOString(),
  };

  return c.json({
    status: "registered",
    orderNumber: order.orderNumber,
    invoiceNumber: body.invoiceNumber,
  });
});

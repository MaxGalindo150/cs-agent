import { Hono } from "hono";
import { getDB } from "../db.js";
import { paginate, defaultPage, defaultLimit } from "../utils/response.js";
import { simulatedDelay } from "../utils/delay.js";
import { orderInstallments, orderShipment } from "../db.js";

export const orderRoutes = new Hono();

// ── GET /api/v1/orders ──────────────────────────────────────────────
orderRoutes.get("/orders", async (c) => {
  await simulatedDelay();
  const db = getDB();
  const query = c.req.query();

  let orders = [...db.orders.values()];

  if (query["userId"]) {
    orders = orders.filter((o) => o.userId === query["userId"]);
  }
  if (query["status"]) {
    orders = orders.filter((o) => o.status === query["status"]);
  }
  if (query["merchantId"]) {
    orders = orders.filter((o) => o.merchantId === query["merchantId"]);
  }

  orders.sort((a, b) => b.createdAt.localeCompare(a.createdAt));

  const page = defaultPage(query);
  const limit = defaultLimit(query);
  return c.json(paginate(orders, page, limit));
});

// ── GET /api/v1/orders/:id ──────────────────────────────────────────
orderRoutes.get("/orders/:id", async (c) => {
  await simulatedDelay();
  const db = getDB();
  const order = db.orders.get(c.req.param("id"));
  if (!order) return c.json({ error: "Order not found" }, 404);
  return c.json(order);
});

// ── GET /api/v1/orders/:id/installments ─────────────────────────────
orderRoutes.get("/orders/:id/installments", async (c) => {
  await simulatedDelay();
  const db = getDB();
  const order = db.orders.get(c.req.param("id"));
  if (!order) return c.json({ error: "Order not found" }, 404);

  return c.json({ data: orderInstallments(order.id) });
});

// ── GET /api/v1/orders/:id/shipment ─────────────────────────────────
orderRoutes.get("/orders/:id/shipment", async (c) => {
  await simulatedDelay();
  const db = getDB();
  const order = db.orders.get(c.req.param("id"));
  if (!order) return c.json({ error: "Order not found" }, 404);

  const shipment = orderShipment(order.id);
  if (!shipment) return c.json({ error: "Shipment not found" }, 404);
  return c.json(shipment);
});

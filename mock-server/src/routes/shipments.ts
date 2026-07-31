import { Hono } from "hono";
import { getDB } from "../db.js";
import { simulatedDelay } from "../utils/delay.js";
import { isoDaysFromNow } from "../seed/generators.js";

export const shipmentRoutes = new Hono();

// ── GET /api/v1/shipments/:id ───────────────────────────────────────
shipmentRoutes.get("/shipments/:id", async (c) => {
  await simulatedDelay();
  const db = getDB();
  const shipment = db.shipments.get(c.req.param("id"));
  if (!shipment) return c.json({ error: "Shipment not found" }, 404);
  return c.json(shipment);
});

// ── PATCH /api/v1/shipments/:id ─────────────────────────────────────
/**
 * Avanza el estado del envío. Body opcional: { status?: string }
 * Si no se pasa status, avanza al siguiente estado lógico.
 */
const STATUS_FLOW: Record<string, string> = {
  preparing: "shipped",
  shipped: "in_transit",
  in_transit: "out_for_delivery",
  out_for_delivery: "delivered",
  delivered: "delivered",
};

shipmentRoutes.patch("/shipments/:id", async (c) => {
  await simulatedDelay();
  const db = getDB();
  const shipment = db.shipments.get(c.req.param("id"));
  if (!shipment) return c.json({ error: "Shipment not found" }, 404);

  let body: { status?: string } = {};
  try {
    body = await c.req.json();
  } catch {
    // vacío es válido
  }

  const newStatus = body.status ?? STATUS_FLOW[shipment.status] ?? shipment.status;
  const now = new Date().toISOString();

  if (newStatus !== shipment.status) {
    shipment.status = newStatus as typeof shipment.status;
    shipment.updatedAt = now;

    // Transiciones de fechas
    if (newStatus === "shipped" && !shipment.shippedAt) {
      shipment.shippedAt = now;
    }
    if (newStatus === "delivered" && !shipment.deliveredAt) {
      shipment.deliveredAt = now;
    }

    // Agregar evento de tracking
    const eventDescriptions: Record<string, string> = {
      shipped: `Package handed to ${shipment.carrier.toUpperCase()}`,
      in_transit: "In transit to destination",
      out_for_delivery: "Out for delivery",
      delivered: "Package delivered successfully",
      returned: "Package returned to sender",
      failed: "Delivery attempt failed",
    };

    shipment.events.push({
      status: newStatus,
      description: eventDescriptions[newStatus] ?? `Status updated to ${newStatus}`,
      location: "Distribution Hub",
      timestamp: now,
    });
  }

  return c.json(shipment);
});

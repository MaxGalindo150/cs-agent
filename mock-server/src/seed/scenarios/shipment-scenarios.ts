/**
 * Escenarios de anomalías de ENVÍOS.
 */

import { id } from "../../utils/id.js";
import { isoDaysAgo, isoDaysFromNow, nowISO } from "../generators.js";
import type { Database } from "../../db.js";
import type { Scenario } from "./types.js";
import { tagUser, usersWithFewestTags, activeOrders } from "./types.js";

// ── shipment_stuck ──────────────────────────────────────────────────
export const shipmentStuck: Scenario = {
  tag: "shipment_stuck",
  description: "Shipment has been in transit for 15+ days with no tracking updates",
  apply(db: Database): void {
    for (const userId of usersWithFewestTags(db, ["shipment_stuck"])) {
      const orders = activeOrders(db, userId);
      const shipment = findShipment(db, userId, orders);
      if (!shipment) continue;

      shipment.status = "in_transit";
      shipment.shippedAt = isoDaysAgo(18);
      shipment.estimatedDelivery = isoDaysAgo(5); // fecha ya pasada
      shipment.events = [
        {
          status: "preparing",
          description: "Order received and being prepared",
          location: "Fulfillment Center",
          timestamp: isoDaysAgo(20),
        },
        {
          status: "shipped",
          description: `Package handed to ${shipment.carrier.toUpperCase()}`,
          location: "Fulfillment Center",
          timestamp: isoDaysAgo(18),
        },
        {
          status: "in_transit",
          description: "In transit to destination",
          location: "Distribution Hub",
          timestamp: isoDaysAgo(17),
        },
      ];
      shipment.updatedAt = isoDaysAgo(17);

      tagUser(db, userId, "shipment_stuck");
      return;
    }
  },
};

// ── shipment_lost ───────────────────────────────────────────────────
export const shipmentLost: Scenario = {
  tag: "shipment_lost",
  description: "Shipment was shipped but tracking shows no events after initial scan",
  apply(db: Database): void {
    for (const userId of usersWithFewestTags(db, ["shipment_lost"])) {
      const orders = activeOrders(db, userId);
      const shipment = findShipment(db, userId, orders);
      if (!shipment) continue;

      shipment.status = "shipped";
      shipment.shippedAt = isoDaysAgo(10);
      shipment.estimatedDelivery = isoDaysAgo(3);
      shipment.events = [
        {
          status: "preparing",
          description: "Order received and being prepared",
          location: "Fulfillment Center",
          timestamp: isoDaysAgo(12),
        },
        {
          status: "shipped",
          description: `Package handed to ${shipment.carrier.toUpperCase()}`,
          location: "Fulfillment Center",
          timestamp: isoDaysAgo(10),
        },
        // Sin eventos de tránsito — se perdió
      ];
      shipment.updatedAt = isoDaysAgo(10);

      tagUser(db, userId, "shipment_lost");
      return;
    }
  },
};

// ── shipment_never_shipped ───────────────────────────────────────────
export const shipmentNeverShipped: Scenario = {
  tag: "shipment_never_shipped",
  description: "Order is active/approved but shipment is stuck in 'preparing' for 10+ days",
  apply(db: Database): void {
    for (const userId of usersWithFewestTags(db, ["shipment_never_shipped"])) {
      const orders = activeOrders(db, userId);
      if (orders.length === 0) continue;

      const order = orders[0]!;
      const shipment = [...db.shipments.values()].find((s) => s.orderId === order.id);
      if (!shipment) continue;

      shipment.status = "preparing";
      shipment.shippedAt = null;
      shipment.estimatedDelivery = isoDaysFromNow(7);
      shipment.events = [
        {
          status: "preparing",
          description: "Order received and being prepared",
          location: "Fulfillment Center",
          timestamp: isoDaysAgo(12),
        },
        // Estancado en preparación por 12 días
      ];
      shipment.updatedAt = isoDaysAgo(12);

      tagUser(db, userId, "shipment_never_shipped");
      return;
    }
  },
};

function findShipment(db: Database, userId: string, orders: ReturnType<typeof activeOrders>) {
  for (const order of orders) {
    const shp = [...db.shipments.values()].find((s) => s.orderId === order.id);
    if (shp) return shp;
  }
  return null;
}

import { Hono } from "hono";
import { cors } from "hono/cors";
import { serve } from "@hono/node-server";

import { runSeed } from "./seed/seed.js";
import { healthRoutes } from "./routes/health.js";
import { userRoutes } from "./routes/users.js";
import { orderRoutes } from "./routes/orders.js";
import { installmentRoutes } from "./routes/installments.js";
import { shipmentRoutes } from "./routes/shipments.js";
import { merchantRoutes } from "./routes/merchants.js";
import { transactionRoutes } from "./routes/transactions.js";
import { membershipRoutes } from "./routes/membership.js";
import { scenarioRoutes } from "./routes/scenarios.js";
import { paymentRoutes } from "./routes/payments.js";

const PORT = 3001;

// ── Seed al arrancar ────────────────────────────────────────────────
console.log("🌱 Seeding database...");
const db = runSeed();
const userCount = db.users.size;
const orderCount = db.orders.size;
const scenarioUsers = [...db.users.values()].filter((u) => u.scenarioTags.length > 0).length;
console.log(`✅ Seed complete: ${userCount} users, ${orderCount} orders, ${scenarioUsers} users with anomalies`);

// ── Hono app ────────────────────────────────────────────────────────
const app = new Hono();

app.use("*", cors());

// Routes under /api/v1
app.route("/api/v1", userRoutes);
app.route("/api/v1", orderRoutes);
app.route("/api/v1", installmentRoutes);
app.route("/api/v1", shipmentRoutes);
app.route("/api/v1", merchantRoutes);
app.route("/api/v1", transactionRoutes);
app.route("/api/v1", membershipRoutes);
app.route("/api/v1", scenarioRoutes);
app.route("/api/v1", paymentRoutes);

// Health (no prefix)
app.route("/", healthRoutes);

// Root info
app.get("/", (c) => c.json({
  name: "BNPL Mock Server",
  version: "0.1.0",
  endpoints: {
    health: "/healthz",
    users: "/api/v1/users",
    orders: "/api/v1/orders",
    installments: "/api/v1/installments/:id/pay",
    shipments: "/api/v1/shipments/:id",
    merchants: "/api/v1/merchants",
    transactions: "/api/v1/transactions",
    membership: "/api/v1/memberships/:id/redeem",
    scenarios: "/api/v1/scenarios",
  },
}));

// ── Start ───────────────────────────────────────────────────────────
serve({ fetch: app.fetch, port: PORT }, (info) => {
  console.log(`🚀 BNPL Mock Server running at http://localhost:${info.port}`);
});

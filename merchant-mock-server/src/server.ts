import { Hono } from "hono";
import { cors } from "hono/cors";
import { serve } from "@hono/node-server";
import { healthRoutes } from "./routes/health.js";
import { merchantRoutes } from "./routes/merchants.js";
import { storeRoutes } from "./routes/stores.js";
import { orderRoutes } from "./routes/orders.js";
import { employeeRoutes, posRoutes } from "./routes/employees.js";
import { onboardingRoutes } from "./routes/onboarding.js";
import { reportRoutes } from "./routes/reports.js";
import { scenarioRoutes } from "./routes/scenarios.js";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { basename, dirname, join } from "node:path";

// ── Frontend HTML (servido en /dashboard) ──────────────────────────
const __dirname = dirname(fileURLToPath(import.meta.url));
const PUBLIC_DIR = join(__dirname, "..", "public");
const dashboardHtml = readFileSync(join(PUBLIC_DIR, "index.html"), "utf-8");

// Assets estáticos del dashboard (logos de Cashea).
const ASSET_CONTENT_TYPES: Record<string, string> = {
  ".svg": "image/svg+xml",
  ".png": "image/png",
};

// ── Seed se ejecuta al arrancar ────────────────────────────────────
import { runSeed } from "./seed/seed.js";

console.log("🌱 Seeding database...");
runSeed();

// 3002 por defecto (lo que espera docker-compose y el agent-service); PORT
// permite una segunda instancia o esquivar un choque de puertos local.
const PORT = Number.parseInt(process.env.PORT ?? "", 10) || 3002;

const app = new Hono();

// ── Middleware global ──────────────────────────────────────────────
app.use("*", cors());

// ── Health (sin prefijo, igual que el mock BNPL) ───────────────────
app.route("/", healthRoutes);

// ── Routers de dominio ─────────────────────────────────────────────
app.route("/api/v1/merchants", merchantRoutes);
app.route("/api/v1/stores", storeRoutes);
app.route("/api/v1/orders", orderRoutes);
app.route("/api/v1/employees", employeeRoutes);
app.route("/api/v1/pos", posRoutes);
app.route("/api/v1/onboarding", onboardingRoutes);
app.route("/api/v1", reportRoutes);
app.route("/api/v1/scenarios", scenarioRoutes);

// ── Frontend dashboard ─────────────────────────────────────────────
app.get("/dashboard", (c) => c.html(dashboardHtml));

// basename() descarta cualquier segmento de ruta, así que un pedido a
// ../../etc/passwd nunca sale de public/assets.
app.get("/assets/:file", (c) => {
  const file = basename(c.req.param("file"));
  const contentType = ASSET_CONTENT_TYPES[file.slice(file.lastIndexOf("."))];
  if (!contentType) return c.text("Not found", 404);

  try {
    const body = readFileSync(join(PUBLIC_DIR, "assets", file));
    return c.body(body, 200, {
      "Content-Type": contentType,
      "Cache-Control": "public, max-age=3600",
    });
  } catch {
    return c.text("Not found", 404);
  }
});

// ── Discovery index ────────────────────────────────────────────────
app.get("/", (c) =>
  c.json({
    name: "merchant-mock-server",
    version: "0.1.0",
    description: "Mock server orientado al aliado (merchant) de Cashea",
    port: PORT,
    endpoints: {
      health: ["/healthz", "/readyz"],
      merchants: [
        "GET /api/v1/merchants",
        "GET /api/v1/merchants/by-rif/:rif",
        "GET /api/v1/merchants/:id",
        "GET /api/v1/merchants/:id/stores",
        "GET /api/v1/merchants/:id/employees",
        "GET /api/v1/merchants/:id/payouts",
        "GET /api/v1/merchants/:id/payouts/:payoutId",
        "GET /api/v1/merchants/:id/invoices",
        "GET /api/v1/merchants/:id/monthly-reports",
        "GET /api/v1/merchants/:id/monthly-reports/:period",
        "GET /api/v1/merchants/:id/monthly-reports/:period/service-fee",
        "GET /api/v1/merchants/:id/monthly-reports/:period/missed-installments",
        "GET /api/v1/merchants/:id/monthly-reports/:period/errors-and-adjustments",
        "GET /api/v1/merchants/:id/promotions",
        "POST /api/v1/merchants/:id/promotions/:promotionId/join",
        "POST /api/v1/merchants/:id/promotions/:promotionId/leave",
      ],
      stores: [
        "GET /api/v1/stores/:uuid",
        "GET /api/v1/stores/:uuid/daily-conciliation",
        "GET /api/v1/stores/:uuid/daily-conciliation/last",
        "GET /api/v1/stores/:uuid/daily-conciliation/history",
        "GET /api/v1/stores/:uuid/payment-methods",
        "GET /api/v1/stores/:uuid/pos",
        "GET /api/v1/stores/:uuid/pos/qr-summary",
        "GET /api/v1/stores/:uuid/products",
        "GET /api/v1/stores/:uuid/inventory/jobs",
        "GET /api/v1/stores/:uuid/inventory/jobs/:jobUuid",
      ],
      orders: [
        "GET /api/v1/orders",
        "GET /api/v1/orders/:orderNumber",
        "GET /api/v1/orders/:orderNumber/installments",
        "POST /api/v1/orders/:orderNumber/cancel",
        "POST /api/v1/orders/:orderNumber/invoice",
      ],
      employees: [
        "GET /api/v1/employees/:id",
        "POST /api/v1/employees/:id/2fa/register-phone",
        "POST /api/v1/employees/:id/2fa/send-code",
        "POST /api/v1/employees/:id/2fa/verify-code",
      ],
      pos: [
        "GET /api/v1/pos/:uuid",
        "POST /api/v1/pos/:uuid/link-qr",
      ],
      reports: [
        "GET /api/v1/reports",
        "GET /api/v1/movements",
      ],
      onboarding: [
        "GET /api/v1/onboarding/:onboardingId",
      ],
      scenarios: [
        "GET /api/v1/scenarios",
        "GET /api/v1/scenarios/:tag",
      ],
      dashboard: ["GET /dashboard", "GET /assets/:file"],
    },
  }),
);

// ── Boot ───────────────────────────────────────────────────────────
console.log("🚀 Merchant mock server starting on port", PORT);

serve({ fetch: app.fetch, port: PORT }, (info) => {
  console.log(`✅ Listening on http://localhost:${info.port}`);
});

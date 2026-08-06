import { Hono } from "hono";

// ── Health routes ──────────────────────────────────────────────────
// Sin delay, sin DB. Igual que el mock BNPL.

export const healthRoutes = new Hono();

healthRoutes.get("/healthz", (c) => c.json({ status: "ok" }));
healthRoutes.get("/readyz", (c) => c.json({ status: "ok", seeded: true }));

import { Hono } from "hono";

export const healthRoutes = new Hono();

healthRoutes.get("/healthz", (c) => c.json({ status: "ok" }));

healthRoutes.get("/readyz", (c) => c.json({ status: "ok", seeded: true }));

import { Hono } from "hono";
import { getDB } from "../db.js";
import { simulatedDelay } from "../utils/delay.js";

export const reportRoutes = new Hono();

// ── Reports hub ────────────────────────────────────────────────────
reportRoutes.get("/reports", async (c) => {
  await simulatedDelay();
  const db = getDB();
  return c.json({ data: db.reports });
});

// ── Movements ──────────────────────────────────────────────────────
reportRoutes.get("/movements", async (c) => {
  await simulatedDelay();
  const db = getDB();
  const movements = [...db.movements].sort((a, b) =>
    b.date.localeCompare(a.date),
  );
  return c.json({ data: movements });
});

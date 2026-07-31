import { Hono } from "hono";
import { getDB } from "../db.js";
import { paginate, defaultPage, defaultLimit } from "../utils/response.js";
import { simulatedDelay } from "../utils/delay.js";

export const merchantRoutes = new Hono();

// ── GET /api/v1/merchants ───────────────────────────────────────────
merchantRoutes.get("/merchants", async (c) => {
  await simulatedDelay();
  const db = getDB();
  const query = c.req.query();

  let merchants = [...db.merchants.values()];

  if (query["category"]) {
    merchants = merchants.filter((m) => m.category === query["category"]);
  }

  merchants.sort((a, b) => a.name.localeCompare(b.name));

  const page = defaultPage(query);
  const limit = defaultLimit(query);
  return c.json(paginate(merchants, page, limit));
});

// ── GET /api/v1/merchants/:id ───────────────────────────────────────
merchantRoutes.get("/merchants/:id", async (c) => {
  await simulatedDelay();
  const db = getDB();
  const merchant = db.merchants.get(c.req.param("id"));
  if (!merchant) return c.json({ error: "Merchant not found" }, 404);
  return c.json(merchant);
});

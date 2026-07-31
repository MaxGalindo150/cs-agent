import { Hono } from "hono";
import { getDB } from "../db.js";
import { paginate, defaultPage, defaultLimit } from "../utils/response.js";
import { simulatedDelay } from "../utils/delay.js";

export const transactionRoutes = new Hono();

// ── GET /api/v1/transactions ────────────────────────────────────────
transactionRoutes.get("/transactions", async (c) => {
  await simulatedDelay();
  const db = getDB();
  const query = c.req.query();

  let txns = [...db.transactions];

  if (query["userId"]) {
    txns = txns.filter((t) => t.userId === query["userId"]);
  }
  if (query["type"]) {
    txns = txns.filter((t) => t.type === query["type"]);
  }

  txns.sort((a, b) => b.createdAt.localeCompare(a.createdAt));

  const page = defaultPage(query);
  const limit = defaultLimit(query);
  return c.json(paginate(txns, page, limit));
});

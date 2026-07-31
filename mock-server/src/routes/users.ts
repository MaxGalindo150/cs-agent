import { Hono } from "hono";
import { getDB } from "../db.js";
import { paginate, defaultPage, defaultLimit } from "../utils/response.js";
import { simulatedDelay } from "../utils/delay.js";
import {
  findUser, userOrders, userTransactions, userPointsTransactions,
  userCreditAccount, userMembership, userPaymentMethods, userAddresses,
} from "../db.js";

export const userRoutes = new Hono();

// ── GET /api/v1/users ───────────────────────────────────────────────
userRoutes.get("/users", async (c) => {
  await simulatedDelay();
  const db = getDB();
  const query = c.req.query();

  let users = [...db.users.values()];

  // Filtros
  const search = query["search"]?.toLowerCase();
  if (search) {
    users = users.filter((u) =>
      u.email.toLowerCase().includes(search) ||
      u.firstName.toLowerCase().includes(search) ||
      u.lastName.toLowerCase().includes(search) ||
      u.id.includes(search),
    );
  }
  if (query["status"]) {
    users = users.filter((u) => u.status === query["status"]);
  }
  if (query["tier"]) {
    users = users.filter((u) => {
      const membership = userMembership(u.id);
      return membership?.tier === query["tier"];
    });
  }
  if (query["scenario"] === "true") {
    users = users.filter((u) => u.scenarioTags.length > 0);
  }

  // Ordenar por createdAt desc
  users.sort((a, b) => b.createdAt.localeCompare(a.createdAt));

  const page = defaultPage(query);
  const limit = defaultLimit(query);
  const include = query["include"];

  let result = paginate(users, page, limit);
  if (include?.includes("flags")) {
    // scenarioTags ya vienen en el User
  }

  return c.json(result);
});

// ── GET /api/v1/users/:id ───────────────────────────────────────────
userRoutes.get("/users/:id", async (c) => {
  await simulatedDelay();
  const user = findUser(c.req.param("id"));
  if (!user) return c.json({ error: "User not found" }, 404);
  return c.json(user);
});

// ── GET /api/v1/users/:id/credit ────────────────────────────────────
userRoutes.get("/users/:id/credit", async (c) => {
  await simulatedDelay();
  const user = findUser(c.req.param("id"));
  if (!user) return c.json({ error: "User not found" }, 404);

  const account = userCreditAccount(user.id);
  if (!account) return c.json({ error: "Credit account not found" }, 404);
  return c.json(account);
});

// ── GET /api/v1/users/:id/membership ────────────────────────────────
userRoutes.get("/users/:id/membership", async (c) => {
  await simulatedDelay();
  const user = findUser(c.req.param("id"));
  if (!user) return c.json({ error: "User not found" }, 404);

  const membership = userMembership(user.id);
  if (!membership) return c.json({ error: "Membership not found" }, 404);
  return c.json(membership);
});

// ── GET /api/v1/users/:id/orders ────────────────────────────────────
userRoutes.get("/users/:id/orders", async (c) => {
  await simulatedDelay();
  const user = findUser(c.req.param("id"));
  if (!user) return c.json({ error: "User not found" }, 404);

  let orders = userOrders(user.id);
  if (c.req.query("status")) {
    orders = orders.filter((o) => o.status === c.req.query("status"));
  }
  orders.sort((a, b) => b.createdAt.localeCompare(a.createdAt));

  const page = defaultPage(c.req.query());
  const limit = defaultLimit(c.req.query());
  return c.json(paginate(orders, page, limit));
});

// ── GET /api/v1/users/:id/transactions ──────────────────────────────
userRoutes.get("/users/:id/transactions", async (c) => {
  await simulatedDelay();
  const user = findUser(c.req.param("id"));
  if (!user) return c.json({ error: "User not found" }, 404);

  let txns = userTransactions(user.id);
  if (c.req.query("type")) {
    txns = txns.filter((t) => t.type === c.req.query("type"));
  }
  txns.sort((a, b) => b.createdAt.localeCompare(a.createdAt));

  const page = defaultPage(c.req.query());
  const limit = defaultLimit(c.req.query());
  return c.json(paginate(txns, page, limit));
});

// ── GET /api/v1/users/:id/points-history ────────────────────────────
userRoutes.get("/users/:id/points-history", async (c) => {
  await simulatedDelay();
  const user = findUser(c.req.param("id"));
  if (!user) return c.json({ error: "User not found" }, 404);

  const points = userPointsTransactions(user.id);
  points.sort((a, b) => b.createdAt.localeCompare(a.createdAt));

  const page = defaultPage(c.req.query());
  const limit = defaultLimit(c.req.query());
  return c.json(paginate(points, page, limit));
});

// ── GET /api/v1/users/:id/payment-methods ───────────────────────────
userRoutes.get("/users/:id/payment-methods", async (c) => {
  await simulatedDelay();
  const user = findUser(c.req.param("id"));
  if (!user) return c.json({ error: "User not found" }, 404);

  return c.json({ data: userPaymentMethods(user.id) });
});

// ── GET /api/v1/users/:id/addresses ─────────────────────────────────
userRoutes.get("/users/:id/addresses", async (c) => {
  await simulatedDelay();
  const user = findUser(c.req.param("id"));
  if (!user) return c.json({ error: "User not found" }, 404);

  return c.json({ data: userAddresses(user.id) });
});

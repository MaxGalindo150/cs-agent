import { Hono } from "hono";
import {
  getDB,
  findStore,
  storeConciliations,
  storePOS,
  storePaymentMethods,
  storeProducts,
} from "../db.js";
import { paginate, defaultPage, defaultLimit } from "../utils/response.js";
import { simulatedDelay } from "../utils/delay.js";

export const storeRoutes = new Hono();

// ── Detalle de store por UUID ──────────────────────────────────────
storeRoutes.get("/:uuid", async (c) => {
  await simulatedDelay();
  const store = findStore(c.req.param("uuid"));
  if (!store) {
    return c.json({ error: `No se encontró store ${c.req.param("uuid")}` }, 404);
  }
  return c.json(store);
});

// ── Conciliación diaria por fecha ──────────────────────────────────
storeRoutes.get("/:uuid/daily-conciliation", async (c) => {
  await simulatedDelay();
  const store = findStore(c.req.param("uuid"));
  if (!store) {
    return c.json({ error: `No se encontró store ${c.req.param("uuid")}` }, 404);
  }
  const query = c.req.query();
  const date = query["date"] ?? new Date().toISOString().slice(0, 10);
  const conciliations = storeConciliations(store.uuid);
  const conc = conciliations.find((c2) => c2.date === date);
  if (!conc) {
    return c.json({ error: `No hay conciliación para la fecha ${date}` }, 404);
  }
  return c.json(conc);
});

// ── Última conciliación ────────────────────────────────────────────
storeRoutes.get("/:uuid/daily-conciliation/last", async (c) => {
  await simulatedDelay();
  const store = findStore(c.req.param("uuid"));
  if (!store) {
    return c.json({ error: `No se encontró store ${c.req.param("uuid")}` }, 404);
  }
  const conciliations = storeConciliations(store.uuid);
  if (conciliations.length === 0) {
    return c.json({ error: "No hay conciliaciones registradas" }, 404);
  }
  conciliations.sort((a, b) => b.date.localeCompare(a.date));
  return c.json(conciliations[0]);
});

// ── Historial de conciliaciones ────────────────────────────────────
storeRoutes.get("/:uuid/daily-conciliation/history", async (c) => {
  await simulatedDelay();
  const store = findStore(c.req.param("uuid"));
  if (!store) {
    return c.json({ error: `No se encontró store ${c.req.param("uuid")}` }, 404);
  }
  const query = c.req.query();
  let conciliations = storeConciliations(store.uuid);
  conciliations.sort((a, b) => b.date.localeCompare(a.date));

  const limit = query["limit"] ? parseInt(query["limit"], 10) : 30;
  const offset = query["offset"] ? parseInt(query["offset"], 10) : 0;
  const total = conciliations.length;
  const data = conciliations.slice(offset, offset + limit);

  return c.json({ data, total, limit, offset });
});

// ── Métodos de pago de la tienda ───────────────────────────────────
storeRoutes.get("/:uuid/payment-methods", async (c) => {
  await simulatedDelay();
  const store = findStore(c.req.param("uuid"));
  if (!store) {
    return c.json({ error: `No se encontró store ${c.req.param("uuid")}` }, 404);
  }
  const query = c.req.query();
  let methods = storePaymentMethods(store.uuid);
  if (query["category"]) {
    methods = methods.filter((pm) => pm.category === query["category"]);
  }
  return c.json({ data: methods });
});

// ── POS de la tienda ───────────────────────────────────────────────
storeRoutes.get("/:uuid/pos", async (c) => {
  await simulatedDelay();
  const store = findStore(c.req.param("uuid"));
  if (!store) {
    return c.json({ error: `No se encontró store ${c.req.param("uuid")}` }, 404);
  }
  const pos = storePOS(store.uuid);
  return c.json({ data: pos });
});

// ── Resumen QR de la tienda ────────────────────────────────────────
storeRoutes.get("/:uuid/pos/qr-summary", async (c) => {
  await simulatedDelay();
  const store = findStore(c.req.param("uuid"));
  if (!store) {
    return c.json({ error: `No se encontró store ${c.req.param("uuid")}` }, 404);
  }
  const pos = storePOS(store.uuid);
  const withoutQr = pos.filter((p) => !p.qrLinked);
  return c.json({
    storeUuid: store.uuid,
    storeName: store.name,
    totalPos: pos.length,
    posWithoutQr: withoutQr.length,
  });
});

// ── Productos de la tienda ─────────────────────────────────────────
storeRoutes.get("/:uuid/products", async (c) => {
  await simulatedDelay();
  const store = findStore(c.req.param("uuid"));
  if (!store) {
    return c.json({ error: `No se encontró store ${c.req.param("uuid")}` }, 404);
  }
  const query = c.req.query();
  let products = storeProducts(store.uuid);

  if (query["search"]) {
    const q = query["search"].toLowerCase();
    products = products.filter(
      (p) => p.name.toLowerCase().includes(q) || p.sku.toLowerCase().includes(q),
    );
  }
  if (query["sku"]) {
    products = products.filter((p) => p.sku === query["sku"]);
  }

  products.sort((a, b) => a.name.localeCompare(b.name));

  const page = defaultPage(query);
  const limit = defaultLimit(query);
  return c.json(paginate(products, page, limit));
});

// ── Estado de jobs de inventario masivo ────────────────────────────
storeRoutes.get("/:uuid/inventory/jobs", async (c) => {
  await simulatedDelay();
  const store = findStore(c.req.param("uuid"));
  if (!store) {
    return c.json({ error: `No se encontró store ${c.req.param("uuid")}` }, 404);
  }
  const db = getDB();
  const jobs = db.inventoryJobs.filter((j) => j.storeUuid === store.uuid);
  return c.json({ data: jobs });
});

storeRoutes.get("/:uuid/inventory/jobs/:jobUuid", async (c) => {
  await simulatedDelay();
  const db = getDB();
  const job = db.inventoryJobs.find(
    (j) =>
      j.jobUuid === c.req.param("jobUuid") &&
      j.storeUuid === c.req.param("uuid"),
  );
  if (!job) {
    return c.json({ error: `No se encontró job ${c.req.param("jobUuid")}` }, 404);
  }
  return c.json(job);
});

import { Hono } from "hono";
import { getDB, findMerchant, findMerchantByRif, merchantStores, merchantEmployees, merchantPayouts, merchantInvoices, merchantMonthlyReports, merchantPromotions, setMerchantPromotionEnrollment } from "../db.js";
import { paginate, defaultPage, defaultLimit } from "../utils/response.js";
import { simulatedDelay } from "../utils/delay.js";
import { normalizeRif, rifMatches } from "../utils/rif.js";

export const merchantRoutes = new Hono();

// ── Lista de merchants ─────────────────────────────────────────────
merchantRoutes.get("/", async (c) => {
  await simulatedDelay();
  const query = c.req.query();
  const db = getDB();
  let items = [...db.merchants.values()];

  if (query["search"]) {
    const q = query["search"].toLowerCase();
    items = items.filter(
      (m) =>
        m.legalName.toLowerCase().includes(q) ||
        m.tradeName.toLowerCase().includes(q) ||
        normalizeRif(m.rif).toLowerCase().includes(normalizeRif(q)),
    );
  }

  if (query["rif"]) {
    items = items.filter((m) => rifMatches(query["rif"]!, m.rif));
  }

  if (query["model"]) {
    items = items.filter((m) => m.model === query["model"]);
  }

  if (query["status"]) {
    items = items.filter((m) => m.status === query["status"]);
  }

  if (query["scenario"]) {
    items = items.filter((m) => m.scenarioTags.includes(query["scenario"]!));
  }

  items.sort((a, b) => b.createdAt.localeCompare(a.createdAt));

  const page = defaultPage(query);
  const limit = defaultLimit(query);
  return c.json(paginate(items, page, limit));
});

// ── Lookup por RIF (normaliza el RIF del path) ─────────────────────
merchantRoutes.get("/by-rif/:rif", async (c) => {
  await simulatedDelay();
  const rif = c.req.param("rif");
  const merchant = findMerchantByRif(rif);
  if (!merchant) {
    return c.json({ error: `No se encontró merchant con RIF ${rif}` }, 404);
  }
  return c.json(merchant);
});

// ── Detalle de merchant por ID o UUID ──────────────────────────────
merchantRoutes.get("/:id", async (c) => {
  await simulatedDelay();
  const idParam = c.req.param("id");
  const merchant = findMerchant(idParam);
  if (!merchant) {
    return c.json({ error: `No se encontró merchant ${idParam}` }, 404);
  }
  return c.json(merchant);
});

// ── Stores de un merchant ──────────────────────────────────────────
merchantRoutes.get("/:id/stores", async (c) => {
  await simulatedDelay();
  const merchant = findMerchant(c.req.param("id"));
  if (!merchant) {
    return c.json({ error: `No se encontró merchant ${c.req.param("id")}` }, 404);
  }
  const stores = merchantStores(merchant.id);
  return c.json({ data: stores });
});

// ── Empleados de un merchant ───────────────────────────────────────
merchantRoutes.get("/:id/employees", async (c) => {
  await simulatedDelay();
  const merchant = findMerchant(c.req.param("id"));
  if (!merchant) {
    return c.json({ error: `No se encontró merchant ${c.req.param("id")}` }, 404);
  }
  const query = c.req.query();
  let employees = merchantEmployees(merchant.id);

  if (query["role"]) {
    employees = employees.filter((e) => e.role === query["role"]);
  }

  return c.json({ data: employees });
});

// ── Payouts de un merchant ─────────────────────────────────────────
merchantRoutes.get("/:id/payouts", async (c) => {
  await simulatedDelay();
  const merchant = findMerchant(c.req.param("id"));
  if (!merchant) {
    return c.json({ error: `No se encontró merchant ${c.req.param("id")}` }, 404);
  }
  const query = c.req.query();
  let payouts = merchantPayouts(merchant.id);

  if (query["from"]) {
    payouts = payouts.filter((p) => p.periodFrom >= query["from"]!);
  }
  if (query["to"]) {
    payouts = payouts.filter((p) => p.periodTo <= query["to"]!);
  }
  if (query["status"]) {
    payouts = payouts.filter((p) => p.status === query["status"]);
  }

  payouts.sort((a, b) => b.periodFrom.localeCompare(a.periodFrom));
  return c.json({ data: payouts });
});

// ── Detalle de un payout específico ────────────────────────────────
merchantRoutes.get("/:id/payouts/:payoutId", async (c) => {
  await simulatedDelay();
  const merchant = findMerchant(c.req.param("id"));
  if (!merchant) {
    return c.json({ error: `No se encontró merchant ${c.req.param("id")}` }, 404);
  }
  const payout = merchantPayouts(merchant.id).find(
    (p) => p.id === c.req.param("payoutId"),
  );
  if (!payout) {
    return c.json({ error: `No se encontró payout ${c.req.param("payoutId")}` }, 404);
  }
  return c.json(payout);
});

// ── Facturas de un merchant ────────────────────────────────────────
merchantRoutes.get("/:id/invoices", async (c) => {
  await simulatedDelay();
  const merchant = findMerchant(c.req.param("id"));
  if (!merchant) {
    return c.json({ error: `No se encontró merchant ${c.req.param("id")}` }, 404);
  }
  const query = c.req.query();
  let invoices = merchantInvoices(merchant.id);

  if (query["from"]) {
    invoices = invoices.filter((i) => i.period.from >= query["from"]!);
  }
  if (query["to"]) {
    invoices = invoices.filter((i) => i.period.to <= query["to"]!);
  }
  if (query["status"]) {
    invoices = invoices.filter((i) => i.status === query["status"]);
  }

  invoices.sort((a, b) => b.period.from.localeCompare(a.period.from));
  return c.json({ data: invoices });
});

// ── Reportes mensuales de un merchant ──────────────────────────────
merchantRoutes.get("/:id/monthly-reports", async (c) => {
  await simulatedDelay();
  const merchant = findMerchant(c.req.param("id"));
  if (!merchant) {
    return c.json({ error: `No se encontró merchant ${c.req.param("id")}` }, 404);
  }
  const reports = merchantMonthlyReports(merchant.id);
  const availablePeriods = reports.map((r) => ({
    period: r.periodLabel,
    from: r.period.from,
    to: r.period.to,
  }));
  // Devolver el reporte más reciente + periodos disponibles
  reports.sort((a, b) => b.periodLabel.localeCompare(a.periodLabel));
  return c.json({
    current: reports[0] ?? null,
    availablePeriods,
    data: reports,
  });
});

// ── Reporte mensual de un periodo específico ───────────────────────
merchantRoutes.get("/:id/monthly-reports/:period", async (c) => {
  await simulatedDelay();
  const merchant = findMerchant(c.req.param("id"));
  if (!merchant) {
    return c.json({ error: `No se encontró merchant ${c.req.param("id")}` }, 404);
  }
  const period = c.req.param("period");
  const report = merchantMonthlyReports(merchant.id).find(
    (r) => r.periodLabel === period,
  );
  if (!report) {
    return c.json({ error: `No hay reporte para el periodo ${period}` }, 404);
  }
  return c.json(report);
});

// ── Sub-endpoints de detalle del reporte mensual ───────────────────

merchantRoutes.get("/:id/monthly-reports/:period/service-fee", async (c) => {
  await simulatedDelay();
  const merchant = findMerchant(c.req.param("id"));
  if (!merchant) {
    return c.json({ error: `No se encontró merchant ${c.req.param("id")}` }, 404);
  }
  const period = c.req.param("period");
  const report = merchantMonthlyReports(merchant.id).find(
    (r) => r.periodLabel === period,
  );
  if (!report) {
    return c.json({ error: `No hay reporte para el periodo ${period}` }, 404);
  }
  return c.json({
    period: report.period,
    ...report.serviceFee,
  });
});

merchantRoutes.get("/:id/monthly-reports/:period/missed-installments", async (c) => {
  await simulatedDelay();
  const merchant = findMerchant(c.req.param("id"));
  if (!merchant) {
    return c.json({ error: `No se encontró merchant ${c.req.param("id")}` }, 404);
  }
  const period = c.req.param("period");
  const report = merchantMonthlyReports(merchant.id).find(
    (r) => r.periodLabel === period,
  );
  if (!report) {
    return c.json({ error: `No hay reporte para el periodo ${period}` }, 404);
  }
  return c.json({
    period: report.period,
    ...report.missedInstallments,
  });
});

merchantRoutes.get("/:id/monthly-reports/:period/errors-and-adjustments", async (c) => {
  await simulatedDelay();
  const merchant = findMerchant(c.req.param("id"));
  if (!merchant) {
    return c.json({ error: `No se encontró merchant ${c.req.param("id")}` }, 404);
  }
  const period = c.req.param("period");
  const report = merchantMonthlyReports(merchant.id).find(
    (r) => r.periodLabel === period,
  );
  if (!report) {
    return c.json({ error: `No hay reporte para el periodo ${period}` }, 404);
  }
  return c.json({
    period: report.period,
    ...report.errorsAndAdjustments,
  });
});

// ── Promociones de un merchant ─────────────────────────────────────
merchantRoutes.get("/:id/promotions", async (c) => {
  await simulatedDelay();
  const merchant = findMerchant(c.req.param("id"));
  if (!merchant) {
    return c.json({ error: `No se encontró merchant ${c.req.param("id")}` }, 404);
  }
  const promos = merchantPromotions(merchant.id);
  return c.json({ data: promos });
});

// ── POST: Unirse a promoción ───────────────────────────────────────
merchantRoutes.post("/:id/promotions/:promotionId/join", async (c) => {
  await simulatedDelay();
  const merchant = findMerchant(c.req.param("id"));
  if (!merchant) {
    return c.json({ error: `No se encontró merchant ${c.req.param("id")}` }, 404);
  }
  const promo = merchantPromotions(merchant.id).find(
    (p) => p.id === c.req.param("promotionId"),
  );
  if (!promo) {
    return c.json({ error: `No se encontró promoción ${c.req.param("promotionId")}` }, 404);
  }

  // Verificar elegibilidad
  if (promo.enrollmentStatus === "NONE") {
    return c.json(
      { error: "not_eligible", message: "El merchant no es elegible para esta promoción" },
      403,
    );
  }

  if (promo.enrollmentStatus === "JOINED") {
    return c.json(
      { error: "already_joined", message: "Ya está inscrito en esta promoción" },
      409,
    );
  }

  setMerchantPromotionEnrollment(merchant.id, promo.id, "JOINED");
  return c.json({
    enrollmentStatus: "JOINED",
    joinedAt: new Date().toISOString(),
  });
});

// ── POST: Salir de promoción ───────────────────────────────────────
merchantRoutes.post("/:id/promotions/:promotionId/leave", async (c) => {
  await simulatedDelay();
  const merchant = findMerchant(c.req.param("id"));
  if (!merchant) {
    return c.json({ error: `No se encontró merchant ${c.req.param("id")}` }, 404);
  }
  const promo = merchantPromotions(merchant.id).find(
    (p) => p.id === c.req.param("promotionId"),
  );
  if (!promo) {
    return c.json({ error: `No se encontró promoción ${c.req.param("promotionId")}` }, 404);
  }

  if (promo.enrollmentStatus !== "JOINED") {
    return c.json(
      { error: "not_joined", message: "No está inscrito en esta promoción" },
      409,
    );
  }

  setMerchantPromotionEnrollment(merchant.id, promo.id, "AVAILABLE");
  return c.json({
    enrollmentStatus: "AVAILABLE",
    leftAt: new Date().toISOString(),
  });
});

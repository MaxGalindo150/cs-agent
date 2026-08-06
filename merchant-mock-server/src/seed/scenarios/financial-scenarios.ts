import type { Scenario } from "./types.js";
import { scenarioHelpers as h } from "./types.js";

// ── Escenarios financieros ─────────────────────────────────────────

export const payoutMissingForPeriod: Scenario = {
  tag: "payout_missing_for_period",
  description:
    "Periodo cerrado, monthlyReport emitido, payout.status=PENDING sin sentAt",
  apply(db) {
    for (const payout of db.payouts) {
      if (payout.scenarioTags.length > 0) continue;
      if (payout.status === "PENDING") {
        h.tagPayout(db, payout.id, "payout_missing_for_period");
        return;
      }
    }
    // Si no hay PENDING, crear uno
    const merchants = h.merchantsByFewestTags(db);
    for (const mid of merchants) {
      const merchantPayouts = db.payouts.filter((p) => p.merchantId === mid);
      if (merchantPayouts.length > 0) {
        const p = merchantPayouts[0];
        p.status = "PENDING";
        p.sentAt = null;
        p.bankReference = null;
        h.tagPayout(db, p.id, "payout_missing_for_period");
        return;
      }
    }
  },
};

export const payoutAmountMismatch: Scenario = {
  tag: "payout_amount_mismatch",
  description:
    "payout.netAmount ≠ monthlyReport.compensation.totalAmount por un ajuste no explicado",
  apply(db) {
    for (const payout of db.payouts) {
      if (payout.scenarioTags.length > 0) continue;
      // Desajustar el netAmount sumándole una cantidad arbitraria
      payout.netAmount += 35000; // +$350 no explicado
      h.tagPayout(db, payout.id, "payout_amount_mismatch");
      return;
    }
  },
};

export const invoicesNotSentMultiMonth: Scenario = {
  tag: "invoices_not_sent_multi_month",
  description:
    "5 meses consecutivos con invoice.status=NOT_SENT — 'no me llegaron las facturas'",
  apply(db) {
    const merchants = h.merchantsByFewestTags(db);
    for (const mid of merchants) {
      const merchantInvoices = db.invoices.filter((i) => i.merchantId === mid);
      if (merchantInvoices.length >= 3) {
        // Marcar todas como NOT_SENT y añadir 2 más retroactivas
        for (const inv of merchantInvoices) {
          inv.status = "NOT_SENT";
          inv.sentToEmail = null;
          inv.sentAt = null;
          h.tagInvoice(db, inv.id, "invoices_not_sent_multi_month");
        }
        // Crear facturas retroactivas para simular 5 meses
        for (let m = 4; m <= 5; m++) {
          const periodFrom = new Date(
            Date.now() - m * 30 * 86_400_000,
          ).toISOString();
          const periodTo = new Date(
            Date.now() - (m - 1) * 30 * 86_400_000,
          ).toISOString();
          const periodLabel = `${new Date(periodFrom).getFullYear()}-${(
            new Date(periodFrom).getMonth() + 1
          )
            .toString()
            .padStart(2, "0")}`;
          db.invoices.push({
            id: `inv_${mid}_extra_${m}`,
            merchantId: mid,
            period: { from: periodFrom, to: periodTo },
            periodLabel,
            number: `F-${mid}-${periodLabel.replace("-", "")}`,
            amount: 5000,
            iva: 800,
            isrlRetained: 1000,
            status: "NOT_SENT",
            sentToEmail: null,
            sentAt: null,
            pdfUrl: `https://merchant-mock.local/invoices/${mid}/${periodLabel}.pdf`,
            scenarioTags: ["invoices_not_sent_multi_month"],
          });
        }
        return;
      }
    }
  },
};

export const isrlRetentionDisputed: Scenario = {
  tag: "isrl_retention_disputed",
  description:
    "serviceFee.isrlRetainedAmount alto en un periodo — aliado reclama la retención de ISRL",
  apply(db) {
    const merchants = h.merchantsByFewestTags(db, ["isrl_retention_disputed"]);
    for (const mid of merchants) {
      const reports = db.monthlyReports.filter((r) => r.merchantId === mid);
      for (const report of reports) {
        // Hacer el ISRL anormalmente alto (50% del tech services en vez de 2%)
        report.serviceFee.isrlRetainedAmount = Math.round(
          report.serviceFee.techServicesAmount * 0.5,
        );
        h.tagMerchant(db, mid, "isrl_retention_disputed");
        return;
      }
    }
  },
};

export const dailyConciliationMismatch: Scenario = {
  tag: "daily_conciliation_mismatch",
  description:
    "ordersCount no cuadra con las órdenes del día / un POS sin conciliar",
  apply(db) {
    for (const conc of db.dailyConciliations) {
      if (conc.ordersCount === 0) continue;
      // Desajustar el ordersCount sumándole 2
      conc.ordersCount += 2;
      conc.totalChargedAmount += 5000;
      const store = db.stores.get(conc.storeUuid);
      if (store) h.tagStore(db, store.uuid, "daily_conciliation_mismatch");
      return;
    }
  },
};

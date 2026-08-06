import type { Scenario } from "./types.js";
import { scenarioHelpers as h } from "./types.js";

// ── Escenarios de catálogo / configuración ─────────────────────────

export const posQrNotLinked: Scenario = {
  tag: "pos_qr_not_linked",
  description: "Caja (POS) creada sin QR vinculado — no puede recibir órdenes por QR",
  apply(db) {
    for (const pos of db.pos) {
      if (!pos.qrLinked) {
        h.tagPOS(db, pos.posUuid, "pos_qr_not_linked");
        return;
      }
    }
    // Si todas tienen QR, forzar una sin QR
    const pos = db.pos.find((p) => p.scenarioTags.length === 0);
    if (pos) {
      pos.qrLinked = false;
      pos.qrCode = null;
      h.tagPOS(db, pos.posUuid, "pos_qr_not_linked");
    }
  },
};

export const promotionNotEligible: Scenario = {
  tag: "promotion_not_eligible",
  description:
    "Promo ACTIVE con enrollmentStatus=NONE y condición INCLUDED_MERCHANTS que no incluye al merchant",
  apply(db) {
    // Asegurar que la promo 004 (Black Friday) esté visible como ineligible
    const promo = db.promotions.find((p) => p.id === "promo_004");
    if (promo) {
      promo.status = "ACTIVE"; // Activarla para que sea relevante
      promo.enrollmentStatus = "NONE";
      // Etiquetar al primer merchant para que sea navegable
      const merchants = h.merchantsByFewestTags(db);
      if (merchants.length > 0) {
        h.tagMerchant(db, merchants[0], "promotion_not_eligible");
      }
    }
  },
};

export const modelMigrationPending: Scenario = {
  tag: "model_migration_pending",
  description:
    "Merchant BASE con solicitud migrar a EXPRESS — contrato de cesión sin firmar",
  apply(db) {
    const baseMerchants = [...db.merchants.values()].filter(
      (m) => m.model === "BASE" && m.scenarioTags.length === 0,
    );
    for (const m of baseMerchants) {
      // Marcar que tiene una solicitud de migración pendiente
      h.tagMerchant(db, m.id, "model_migration_pending");
      // Crear un onboarding para el documento pendiente
      const onbId = `onb_migration_${m.id}`;
      db.onboardings.set(onbId, {
        onboardingId: onbId,
        merchantId: m.id,
        step: "LEGAL_DOCUMENTS",
        status: "IN_PROGRESS",
        failedRules: ["cession_contract_not_signed"],
        legalDocuments: [
          { name: "Contrato de cesión de facturas", status: "PENDING" },
        ],
        bankAccountVerified: true,
        readyToGo: false,
        plan: "EXPRESS",
        channelsSelected: [],
        createdAt: new Date().toISOString(),
        scenarioTags: ["model_migration_pending"],
      });
      return;
    }
  },
};

export const onboardingStuckDocuments: Scenario = {
  tag: "onboarding_stuck_documents",
  description:
    "Onboarding con legalDocuments en PENDING y failedRules — afiliación estancada",
  apply(db) {
    // El onboarding onb_0001 ya viene con documentos PENDING del seed base
    const onb = db.onboardings.get("onb_0001");
    if (onb) {
      h.tagOnboarding(db, "onb_0001", "onboarding_stuck_documents");
      return;
    }
    // Si no existe, crear uno
    const onbId = "onb_stuck_0001";
    db.onboardings.set(onbId, {
      onboardingId: onbId,
      step: "LEGAL_DOCUMENTS",
      status: "IN_PROGRESS",
      failedRules: ["contract_not_signed", "bank_data_missing"],
      legalDocuments: [
        { name: "Contrato de servicios Cashea", status: "PENDING" },
        { name: "Contrato de cesión de facturas", status: "PENDING" },
      ],
      bankAccountVerified: false,
      readyToGo: false,
      plan: null,
      channelsSelected: ["IN_STORE"],
      createdAt: new Date().toISOString(),
      scenarioTags: ["onboarding_stuck_documents"],
    });
  },
};

export const inventoryBulkJobFailed: Scenario = {
  tag: "inventory_bulk_job_failed",
  description:
    "Job de carga masiva de inventario en FAILED con errores por fila",
  apply(db) {
    for (const store of [...db.stores.values()]) {
      if (store.scenarioTags.length > 0) continue;
      const jobUuid = `job_bulk_${store.uuid.slice(0, 8)}`;
      db.inventoryJobs.push({
        jobUuid,
        storeUuid: store.uuid,
        fileName: "carga_productos.xlsx",
        status: "FAILED",
        createdAt: new Date(Date.now() - 2 * 86_400_000).toISOString(),
        finishedAt: new Date(Date.now() - 1 * 86_400_000).toISOString(),
        totalProducts: 50,
        processedProducts: 23,
        successCount: 18,
        errorCount: 5,
        errors: [
          { fileRow: 5, fileColumn: "price", error: "El precio debe ser mayor a 0", sku: "SKU-ERR-001" },
          { fileRow: 12, fileColumn: "stock", error: "El stock debe ser un número entero", sku: "SKU-ERR-002" },
          { fileRow: 18, fileColumn: "name", error: "El nombre es obligatorio" },
          { fileRow: 21, fileColumn: "sku", error: "SKU duplicado", sku: "SKU-1-0001" },
          { fileRow: 25, fileColumn: "categoryId", error: "Categoría no válida" },
        ],
      });
      h.tagStore(db, store.uuid, "inventory_bulk_job_failed");
      return;
    }
  },
};

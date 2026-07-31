/**
 * Orquestador de escenarios: aplica anomalías a usuarios del seed.
 * ~20 de 50 usuarios tendrán problemas; algunos tendrán 2 combinados.
 */

import type { Database } from "../../db.js";
import type { ScenarioTag } from "../../schema/index.js";
import type { Scenario } from "./types.js";

import { doublePayment, refundPending, paymentNotReflected, failedPayment, overcharged, cancelledButCharged } from "./payment-scenarios.js";
import { shipmentStuck, shipmentLost, shipmentNeverShipped } from "./shipment-scenarios.js";
import { missingPoints, partialPoints, staleTier, overdueUnnotified, phantomOrder } from "./points-scenarios.js";
import { paymentWrongOrder } from "./payment-scenarios-extra.js";

// Catálogo completo de escenarios
export const ALL_SCENARIOS: Scenario[] = [
  doublePayment,
  refundPending,
  paymentNotReflected,
  failedPayment,
  overcharged,
  cancelledButCharged,
  shipmentStuck,
  shipmentLost,
  shipmentNeverShipped,
  missingPoints,
  partialPoints,
  staleTier,
  overdueUnnotified,
  phantomOrder,
  paymentWrongOrder,
];

// Combinaciones realistas de escenarios
const COMBINATIONS: ScenarioTag[][] = [
  ["missing_points", "stale_tier"],            // sin puntos Y sin subida de nivel
  ["shipment_stuck", "overdue_unnotified"],    // envío perdido Y cuota vencida
  ["failed_payment", "double_payment"],        // pago falló + pago duplicado
  ["partial_points", "stale_tier"],            // puntos parciales + nivel no sube
  ["payment_not_reflected", "overdue_unnotified"], // pago no reflejado + cuota vencida
];

export function applyScenarios(db: Database): void {
  // Aplicar escenarios individuales (uno por usuario) hasta ~15 usuarios
  const individualScenarios = ALL_SCENARIOS.filter((s) =>
    // Excluir los que se usan en combinaciones para no duplicar
    !COMBINATIONS.flat().includes(s.tag),
  );

  for (const scenario of individualScenarios) {
    scenario.apply(db);
  }

  // Aplicar combinaciones (2 problemas en un mismo usuario)
  for (const combo of COMBINATIONS) {
    applyCombination(db, combo);
  }

  // Aplicar algunos escenarios individuales de los que están en combinaciones
  // pero a usuarios distintos, para tener variedad
  const comboTags = COMBINATIONS.flat();
  for (const scenario of ALL_SCENARIOS.filter((s) => comboTags.includes(s.tag))) {
    scenario.apply(db); // intentará asignar a otro usuario sin el tag
  }
}

function applyCombination(db: Database, tags: ScenarioTag[]): void {
  for (const tag of tags) {
    const scenario = ALL_SCENARIOS.find((s) => s.tag === tag);
    if (scenario) scenario.apply(db);
  }
}

export const SCENARIO_DESCRIPTIONS: Record<string, string> = Object.fromEntries(
  ALL_SCENARIOS.map((s) => [s.tag, s.description]),
);

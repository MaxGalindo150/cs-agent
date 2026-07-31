import type { Tier, TierProgress } from "../schema/index.js";

interface TierDef {
  tier: Tier;
  minPoints: number;
  maxPoints: number;
  cashbackMultiplier: number;
}

export const TIER_DEFS: TierDef[] = [
  { tier: "bronze",   minPoints: 0,      maxPoints: 999,     cashbackMultiplier: 1 },
  { tier: "silver",   minPoints: 1000,   maxPoints: 4999,    cashbackMultiplier: 1.5 },
  { tier: "gold",     minPoints: 5000,   maxPoints: 19999,   cashbackMultiplier: 2 },
  { tier: "platinum", minPoints: 20000,  maxPoints: 999999,  cashbackMultiplier: 3 },
];

export function tierForPoints(points: number): Tier {
  for (const def of TIER_DEFS) {
    if (points >= def.minPoints && points <= def.maxPoints) return def.tier;
  }
  return "bronze";
}

export function tierProgressForPoints(points: number): TierProgress {
  const idx = TIER_DEFS.findIndex((d) => points >= d.minPoints && points <= d.maxPoints);
  const def = TIER_DEFS[idx];
  const next = TIER_DEFS[idx + 1];

  if (!next) {
    return { current: points, needed: def.minPoints, pct: 100 };
  }
  const range = next.minPoints - def.minPoints;
  const intoRange = points - def.minPoints;
  return {
    current: points,
    needed: next.minPoints,
    pct: Math.round((intoRange / range) * 1000) / 10,
  };
}

/** Puntos ganados por pagar una cantidad (en centavos). ~1 punto por $1 USD. */
export function pointsForPayment(cents: number): number {
  return Math.floor(cents / 100);
}

/** Distribución target: bronze 50%, silver 25%, gold 15%, platinum 10%. */
export function pickWeightedTier(): Tier {
  const roll = f.number.float({ min: 0, max: 1 });
  if (roll < 0.5) {
    return "bronze";
  } else if (roll < 0.75) {
    return "silver";
  } else if (roll < 0.9) {
    return "gold";
  }
  return "platinum";
}

export function pointsRangeForTier(tier: Tier): { min: number; max: number } {
  const def = TIER_DEFS.find((d) => d.tier === tier)!;
  return { min: def.minPoints, max: def.maxPoints };
}

// Import faker dentro del módulo para pickWeightedTier
import { f } from "./faker.js";

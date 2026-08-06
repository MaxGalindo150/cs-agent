import { faker } from "@faker-js/faker";

// ── Faker determinista ─────────────────────────────────────────────
// Seed fija para reproducibilidad. Override por SEED env.

const envSeed = process.env.SEED;
export const SEED = envSeed !== undefined ? parseInt(envSeed, 10) : 42;

export const f = faker;

export function initFaker(): void {
  f.seed(SEED);
}

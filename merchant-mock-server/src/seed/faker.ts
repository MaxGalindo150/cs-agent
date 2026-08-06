import { faker } from "@faker-js/faker";

// ── Faker determinista ─────────────────────────────────────────────
// Seed fija para reproducibilidad. Override por SEED env.

const DEFAULT_SEED = 42;
const envSeed = process.env.SEED;
const parsedSeed = envSeed !== undefined ? Number.parseInt(envSeed, 10) : Number.NaN;

// Un SEED no numérico daba NaN y faker.seed(NaN) rompe la reproducibilidad en
// silencio: mejor avisar y caer a la seed por defecto.
if (envSeed !== undefined && !Number.isFinite(parsedSeed)) {
  console.warn(`⚠️  SEED="${envSeed}" no es un número; usando ${DEFAULT_SEED}`);
}

export const SEED = Number.isFinite(parsedSeed) ? parsedSeed : DEFAULT_SEED;

// ── Reloj del seed ─────────────────────────────────────────────────
// Un único instante de referencia para *todo* timestamp sembrado. Se toma una
// sola vez al importar, así que dentro de una corrida las fechas son
// coherentes entre sí (una orden de "hace 3 días" y su cuota no se cruzan a
// medianoche). Fijar SEED_NOW a un ISO reproduce una corrida completa; sin él,
// los datos siempre se leen como recientes.
const envNow = process.env.SEED_NOW;
const parsedNow = envNow !== undefined ? Date.parse(envNow) : Number.NaN;

if (envNow !== undefined && !Number.isFinite(parsedNow)) {
  console.warn(`⚠️  SEED_NOW="${envNow}" no es una fecha ISO válida; usando la hora actual`);
}

export const SEED_NOW = Number.isFinite(parsedNow) ? parsedNow : Date.now();

export const f = faker;

export function initFaker(): void {
  f.seed(SEED);
}

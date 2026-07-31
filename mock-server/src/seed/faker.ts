import { faker } from "@faker-js/faker";

/**
 * Faker configurado con seed fijo → dataset determinista.
 * Cada run produce exactamente los mismos datos.
 */
export const f = faker;
export const SEED = 42;

export function initFaker(): void {
  f.seed(SEED);
}

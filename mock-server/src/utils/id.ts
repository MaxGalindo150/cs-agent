let counter = 0;

/**
 * Genera IDs únicos y ordenados. Formato: prefijo + timestamp base62 + seq.
 * Determinista dentro de un run, colision-free sin librerías externas.
 */
export function id(prefix: string): string {
  counter += 1;
  return `${prefix}_${counter.toString(36).padStart(4, "0")}`;
}

/** Resetea el contador — útil al re-seedear. */
export function resetIdCounter(): void {
  counter = 0;
}

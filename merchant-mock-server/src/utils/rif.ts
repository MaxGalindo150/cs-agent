// ── RIF normalization ──────────────────────────────────────────────
// Los RIFs venezolanos tienen formato J-XXXXXXXX-D donde la primera
// letra es el tipo (J=jurídica, V=natural, E=extranjera, G=gobierno),
// seguido de 8-9 dígitos y un dígito verificador.
// En soporte los aliados escriben el RIF de muchas formas:
//   "J-40268443-6", "j402684436", "402684436", "J 40268443 6"
// Normalizamos a una forma canónica para comparación.

/**
 * Normaliza un RIF a su forma canónica: mayúsculas, sin espacios ni guiones.
 * Ej: "j-40268443-6" → "J402684436"
 */
export function normalizeRif(input: string): string {
  return input
    .trim()
    .toUpperCase()
    .replace(/[\s\-._]/g, "");
}

/**
 * Normaliza un RIF a solo dígitos (sin la letra inicial).
 * Ej: "J-40268443-6" → "402684436"
 * Útil cuando el aliado escribe el RIF sin la J.
 */
export function rifDigits(input: string): string {
  const normalized = normalizeRif(input);
  // Quitar letra inicial si existe
  return normalized.replace(/^[A-Z]/, "");
}

/**
 * Compara dos RIFs de forma tolerante.
 * Coincide si los dígitos son iguales, ignorando la letra inicial.
 * Esto cubre "J-40268443-6" vs "402684436" vs "j402684436".
 */
export function rifMatches(query: string, stored: string): boolean {
  return rifDigits(query) === rifDigits(stored);
}

/**
 * Búsqueda parcial de RIF: útil para autocompletado.
 */
export function rifPartialMatch(query: string, stored: string): boolean {
  const q = rifDigits(query);
  const s = rifDigits(stored);
  return s.includes(q);
}

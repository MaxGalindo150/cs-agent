/** Latencia simulada: 40–200ms aleatoria. */
export function simulatedDelay(): Promise<void> {
  const ms = 40 + Math.floor(Math.random() * 160);
  return new Promise((r) => setTimeout(r, ms));
}

/** Latencia configurable. */
export function delay(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

// ── Generadores de datos helpers ───────────────────────────────────
// Funciones utilitarias para crear datos coherentes con sabor VE.

import { f } from "./faker.js";
import {
  VE_FIRST_NAMES,
  VE_LAST_NAMES,
  VE_MOBILE_PREFIXES,
  VE_BANKS,
  VE_CITIES,
} from "./catalogs.js";

// ── Tiempo ─────────────────────────────────────────────────────────
const NOW = Date.now();
const DAY = 86_400_000;

export function nowISO(): string {
  return new Date().toISOString();
}

export function isoDaysAgo(days: number): string {
  return new Date(NOW - days * DAY).toISOString();
}

export function isoDaysFromNow(days: number): string {
  return new Date(NOW + days * DAY).toISOString();
}

export function dateKey(iso: string): string {
  return iso.slice(0, 10); // YYYY-MM-DD
}

export function daysAgoKey(days: number): string {
  return dateKey(isoDaysAgo(days));
}

// ── Dinero (centavos, múltiplos de 100) ────────────────────────────
export function money(min: number, max: number): number {
  return randInt(min, max) * 100;
}

// Tasa aproximada USD→VES (bolívares por dólar)
const VES_RATE = 145; // simplificado

export function toVES(usdCents: number): number {
  return Math.round((usdCents / 100) * VES_RATE) * 100;
}

// ── Random helpers (van por faker determinista) ────────────────────
export function randInt(min: number, max: number): number {
  return Math.floor(f.number.float({ min, max: max + 1 - 0.0001 }));
}

export function pick<T>(arr: readonly T[]): T {
  return f.helpers.arrayElement(arr as T[]);
}

export function pickN<T>(arr: readonly T[], n: number): T[] {
  return f.helpers.arrayElements(arr as T[], n);
}

export function weighted<T>(items: readonly [T, number][]): T {
  const total = items.reduce((s, [, w]) => s + w, 0);
  let r = f.number.float({ min: 0, max: total });
  for (const [item, w] of items) {
    r -= w;
    if (r <= 0) return item;
  }
  return items[items.length - 1][0];
}

// ── Datos VE ───────────────────────────────────────────────────────
export function vePhone(): string {
  const prefix = pick(VE_MOBILE_PREFIXES);
  const rest = f.string.numeric({ length: 7 });
  return `+58${prefix}${rest}`;
}

export function veCedula(): string {
  return `V-${f.string.numeric({ length: 8 })}`;
}

export function veBankReference(): string {
  return f.string.numeric({ length: f.number.int({ min: 8, max: 12 }) });
}

export function veBank(): string {
  return pick(VE_BANKS);
}

export function veCity(): string {
  return pick(VE_CITIES);
}

export function veAddress(): string {
  return `Av. ${pick(["Bolívar", "Sucre", "Miranda", "Páez", "Urdaneta"])}, ${f.location.streetAddress()}`;
}

export function veFullName(): string {
  return `${pick(VE_FIRST_NAMES)} ${pick(VE_LAST_NAMES)}`;
}

export function veEmail(fullName: string): string {
  const handle = fullName
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, ".");
  return `${handle}@${pick(["gmail.com", "hotmail.com", "outlook.com", "yahoo.com"])}`;
}

// ── UUIDs y números de orden ───────────────────────────────────────
export function uuid(): string {
  return f.string.uuid();
}

const generatedOrderNumbers = new Set<string>();

export function uniqueOrderNumber(): string {
  let num: string;
  do {
    num = f.string.numeric({ length: 9, allowLeadingZeros: false });
  } while (generatedOrderNumbers.has(num));
  generatedOrderNumbers.add(num);
  return num;
}

export function resetOrderNumbers(): void {
  generatedOrderNumbers.clear();
}

// ── RIF generator (para compradores con cédula) ────────────────────
export function rifFromCedula(): string {
  const letter = pick(["V", "J", "E"]);
  const digits = f.string.numeric({ length: 8 });
  const verifier = f.string.numeric({ length: 1 });
  return `${letter}-${digits}-${verifier}`;
}

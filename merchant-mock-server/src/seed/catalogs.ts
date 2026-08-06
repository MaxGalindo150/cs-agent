// ── Catálogos de datos venezolanos ─────────────────────────────────
// Nombres de comercio, bancos, categorías y productos con sabor real VE.

// ── 5 Merchants fijos (deterministas, con datos realistas) ─────────
export interface MerchantSeed {
  id: number;
  rif: string;
  legalName: string;
  tradeName: string;
  categoryId: number;
  model: "BASE" | "EXPRESS";
  fcbPeriod: "WEEKLY" | "BI_WEEKLY" | "DAILY";
  status: "ACTIVE" | "INACTIVE" | "SUSPENDED";
  adminEmail: string;
  categoryName: string;
}

export const MERCHANTS: MerchantSeed[] = [
  {
    id: 1,
    rif: "J-40268443-6",
    legalName: "Inversiones Suministros Jireh 2013, C.A.",
    tradeName: "Multi-tienda Cardenal",
    categoryId: 1,
    model: "EXPRESS",
    fcbPeriod: "WEEKLY",
    status: "ACTIVE",
    adminEmail: "admin@cardenal.com",
    categoryName: "Multi-tienda",
  },
  {
    id: 2,
    rif: "J-30848255-1",
    legalName: "Supermercado El Tama, C.A.",
    tradeName: "Supermercado El Tama",
    categoryId: 2,
    model: "BASE",
    fcbPeriod: "BI_WEEKLY",
    status: "ACTIVE",
    adminEmail: "gerencia@eltama.com",
    categoryName: "Alimentos",
  },
  {
    id: 3,
    rif: "J-50078912-3",
    legalName: "Tecnología Avanzada de Venezuela, S.A.",
    tradeName: "TechStore VE",
    categoryId: 3,
    model: "EXPRESS",
    fcbPeriod: "DAILY",
    status: "ACTIVE",
    adminEmail: "soporte@techstoreve.com",
    categoryName: "Electrónica",
  },
  {
    id: 4,
    rif: "J-41592764-8",
    legalName: "Comercializadora La Economica, C.A.",
    tradeName: "La Economica Hogar",
    categoryId: 4,
    model: "BASE",
    fcbPeriod: "WEEKLY",
    status: "ACTIVE",
    adminEmail: "info@laeconomica.com",
    categoryName: "Hogar y Muebles",
  },
  {
    id: 5,
    rif: "J-51284360-5",
    legalName: "Distribuidora Sport Plus 2020, C.A.",
    tradeName: "Sport Plus",
    categoryId: 5,
    model: "EXPRESS",
    fcbPeriod: "BI_WEEKLY",
    status: "SUSPENDED",
    adminEmail: "admin@sportplus.com",
    categoryName: "Deportes",
  },
];

// ── Bancos venezolanos ─────────────────────────────────────────────
export const VE_BANKS = [
  "Banco de Venezuela",
  "Banesco",
  "Mercantil",
  "Provincial",
  "BNC",
  "Bancaribe",
  "Banco del Tesoro",
  "BFC",
  "Banco Exterior",
  "Bancamiga",
] as const;

// ── Ciudades ───────────────────────────────────────────────────────
export const VE_CITIES = [
  "Caracas",
  "Maracaibo",
  "Valencia",
  "Barquisimeto",
  "Maracay",
  "Pto. La Cruz",
  "Mérida",
  "San Cristóbal",
  "Pto. Ordaz",
  "Barcelona",
] as const;

// ── Categorías de producto ─────────────────────────────────────────
export const PRODUCT_CATEGORIES: Record<number, { name: string; products: { name: string; priceRange: [number, number] }[] }> = {
  1: {
    name: "Multi-tienda",
    products: [
      { name: "Ropa dama vestido", priceRange: [25, 60] },
      { name: "Zapatos caballero", priceRange: [30, 80] },
      { name: "Bolso de cuero", priceRange: [35, 90] },
      { name: "Accesorios diversos", priceRange: [10, 30] },
      { name: "Ropa infantil", priceRange: [15, 35] },
    ],
  },
  2: {
    name: "Alimentos",
    products: [
      { name: "Canasta básica familiar", priceRange: [40, 120] },
      { name: "Caja de cereales x12", priceRange: [25, 50] },
      { name: "Aceite vegetal 1L x12", priceRange: [30, 60] },
      { name: "Harina de maíz x10", priceRange: [15, 30] },
    ],
  },
  3: {
    name: "Electrónica",
    products: [
      { name: "Televisor 43\" Full HD", priceRange: [250, 450] },
      { name: "Smartphone Android", priceRange: [120, 400] },
      { name: "Audífonos Bluetooth", priceRange: [25, 80] },
      { name: "Laptop 14\" i5", priceRange: [500, 900] },
      { name: "Tablet 10\"", priceRange: [150, 350] },
      { name: "Smartwatch", priceRange: [40, 120] },
    ],
  },
  4: {
    name: "Hogar y Muebles",
    products: [
      { name: "Juego de comedor 6 puestos", priceRange: [400, 800] },
      { name: "Colchón queen size", priceRange: [200, 500] },
      { name: "Nevera 12 pies", priceRange: [300, 600] },
      { name: "Cocina 4 hornillas", priceRange: [180, 400] },
      { name: "Mesas de noche x2", priceRange: [60, 120] },
    ],
  },
  5: {
    name: "Deportes",
    products: [
      { name: "Bicicleta de montaña 26\"", priceRange: [150, 400] },
      { name: "Pesas ajustables 20kg", priceRange: [60, 120] },
      { name: "Camiseta deportiva", priceRange: [15, 40] },
      { name: "Tenis de running", priceRange: [50, 130] },
      { name: "Mancuernas hexagonales", priceRange: [25, 60] },
    ],
  },
};

// ── Nombres venezolanos para compradores ───────────────────────────
export const VE_FIRST_NAMES = [
  "José", "María", "Carlos", "Ana", "Luis", "Jessica", "Andrés",
  "Carolina", "Manuel", "Yusleidis", "Rafael", "Daniela",
  "Pedro", "Gabriela", "Juan", "Valentina", "Fernando", "Michelle",
];

export const VE_LAST_NAMES = [
  "Rodríguez", "González", "Ramírez", "Pérez", "García", "Martínez",
  "Hernández", "Sánchez", "Torres", "Rivero", "Méndez", "Castillo",
  "Briceño", "Rojas", "Silva", "Mora", "Vargas", "Padrón",
];

// ── Prefijos telefónicos VE ────────────────────────────────────────
export const VE_MOBILE_PREFIXES = ["412", "414", "424", "416", "426"] as const;

// ── Motivos de cancelación de órdenes ──────────────────────────────
export const CANCELLATION_REASONS = [
  { id: 1, reason: "El cliente decidió no continuar con la compra" },
  { id: 2, reason: "Error en el monto de la orden" },
  { id: 3, reason: "Producto sin stock" },
  { id: 4, reason: "Fraude sospechoso" },
  { id: 5, reason: "Solicitud del cliente" },
  { id: 6, reason: "Duplicación de orden" },
];

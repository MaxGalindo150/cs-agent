# Merchant Mock Server — API Reference

> **Base URL:** `http://localhost:3002`
> **Content-Type:** `application/json`
> **Latencia simulada:** 40–200ms por request (health除外)

Servidor mock del dominio **aliado (merchant)** de Cashea.Todas las rutas de dominio están bajo `/api/v1`. Las de health están en la raíz.

---

## Convenciones

### Dinero

Todos los montos son enteros en **centavos**. El campo `currency` indica la moneda (`"USD"` o `"VES"`). Varios objetos tienen monto dual: `amount` (centavos USD) y `amountVES` (centavos VES), porque los pagos reales llegan en bolívares.

```
15000 → $150.00
9900  → $99.00   (USD)
```

### Timestamps

ISO 8601 con zona horaria:

```
2026-07-15T10:30:00.000Z
```

Campos nullable usan `null`, no se omiten.

### Listas y paginación

Los endpoints paginados devuelven:

```json
{
  "data": [ ... ],
  "page": 1,
  "limit": 20,
  "total": 50,
  "totalPages": 3
}
```

Query params: `page` (default 1), `limit` (default 20, máx 100).

Endpoints de lista simple devuelven `{ data: [...] }` sin metadatos de paginación. El historial de conciliación devuelve `{ data, total, limit, offset }`.

### Errores

Cualquier respuesta non-2xx:

```json
{ "error": "machine_readable_code" }
```

o con mensaje adicional:

```json
{ "error": "code_expired", "message": "El código ha expirado. Solicite uno nuevo." }
```

| Status | Cuándo |
|--------|--------|
| 400 | Body inválido o faltan campos requeridos |
| 403 | Prohibido por regla de rol, elegibilidad o estado |
| 404 | Recurso no encontrado |
| 409 | Conflicto de estado (ya cancelado, ya unido, código incorrecto) |
| 503 | Falla técnica simulada (ej: registro de factura) |

### Identidad

El principal es un triplete: **merchant** (por RIF) → **store** → **employee** (con rol). Las órdenes se identifican por **número de orden** numérico de 9 dígitos.

### Lookup de RIF

Tolerante — normaliza a mayúsculas, quita guiones/espacios/puntos, y compara solo los dígitos (ignora la letra inicial). Así `"J-40268443-6"`, `"j402684436"`, `"402684436"` y `"J 40268443 6"` coinciden todos.

---

## Enums del dominio

| Enum | Valores |
|------|---------|
| MerchantModel | `BASE` \| `EXPRESS` |
| MerchantStatus | `ACTIVE` \| `INACTIVE` \| `SUSPENDED` |
| FcbPeriod | `WEEKLY` \| `BI_WEEKLY` \| `DAILY` |
| EmployeeRole | `ADMIN` \| `MANAGER` \| `CASHIER` |
| EmployeeOnboardingStatus | `IN_PROGRESS` \| `IN_PROGRESS_RTG` \| `FINISHED` \| `INACTIVE` |
| OrderStatus | `IN_PROGRESS` \| `CLOSED` \| `OPEN` \| `CANCELLED` \| `PENDING` |
| OrderChannel | `IN_STORE` \| `REMOTE` \| `OFFLINE` \| `IN_APP` |
| InstallmentStatus | `SCHEDULED` \| `DONE` \| `GRACED` \| `PENDING` \| `DELAYED` \| `RENEGOTIATED` \| `CANCELLED` |
| InstallmentPaymentStatus | `VERIFIED` \| `CANCELLED` \| `PENDING` \| `RETURNED` |
| PaymentMethodName | `PAGO_MOVIL` \| `TRANSFERENCIA` \| `EFECTIVO` \| `TARJETA` |
| PayoutStatus | `PENDING` \| `SENT` \| `FAILED` |
| InvoiceStatus | `ISSUED` \| `SENT` \| `NOT_SENT` |
| ProductStatus | `ACTIVE` \| `PAUSED` |
| ProductType | `PHYSICAL` \| `DIGITAL` |
| JobStatus | `PENDING` \| `PROCESSING` \| `COMPLETED` \| `FAILED` \| `COMPLETED_WITH_ERRORS` |
| QrCodeStatus | `AVAILABLE` \| `LINKED` \| `DELETED` \| `DISABLED` |

---

## Data Models

### Merchant

```ts
{
  id: number
  uuid: string
  rif: string
  legalName: string
  tradeName: string
  categoryId: number
  model: "BASE" | "EXPRESS"
  merchantGroup: string | null
  status: "ACTIVE" | "INACTIVE" | "SUSPENDED"
  activeFcb: boolean
  fcbPeriod: "WEEKLY" | "BI_WEEKLY" | "DAILY"
  fcbStartDate: string | null
  adminEmail: string
  createdAt: string
  scenarioTags: string[]
}
```

### Store

```ts
{
  id: number
  uuid: string
  merchantId: number
  name: string
  email: string | null
  statusId: 1 | 2            // 1=INACTIVE, 2=ACTIVE
  channels: string[]
  isPhysical: boolean
  inventoryMigrated: boolean
  minimumDownPayment: number
  minimumFinanceableAmount: number | null
  address: {
    name: string | null
    long: number | null
    lat: number | null
    location: string | null
    shipmentsEnabled: boolean
  } | null
  createdAt: string
  scenarioTags: string[]
  // Flags internos para escenarios
  invoiceRegistrationFailing: boolean
  orderCreateConnectionError: boolean
}
```

### Employee

```ts
{
  id: string
  storeUuid: string
  merchantId: number
  name: string
  email: string
  role: "ADMIN" | "MANAGER" | "CASHIER"
  onboardingStatus: "IN_PROGRESS" | "IN_PROGRESS_RTG" | "FINISHED" | "INACTIVE"
  phoneRegistered: boolean
  phoneNumber: string | null
  mustChangePassword: boolean
  securityCodeSet: boolean
  lastLoginAt: string | null
  createdAt: string
  scenarioTags: string[]
  // Flag interno para escenario
  otpNeverArrives: boolean
}
```

### Order

```ts
{
  orderNumber: string         // 9 dígitos
  uuid: string
  storeUuid: string
  merchantId: number
  status: "IN_PROGRESS" | "CLOSED" | "OPEN" | "CANCELLED" | "PENDING"
  statusId: number
  channel: "IN_STORE" | "REMOTE" | "OFFLINE" | "IN_APP"
  deliveryType: string | null
  deliveryStatus: string
  shipmentStatus: string | null
  totalAmount: number         // centavos
  downPaymentAmount: number   // centavos
  financedAmount: number      // centavos
  currency: string            // "USD"
  products: {
    id: string
    name: string
    quantity: number
    price: number
    priceAfterDiscount: number | null
  }[]
  buyer: {
    fullName: string | null
    identificationNumber: string | null
    phoneNumber: string | null
    email: string | null
  }
  pos: { name: string; uuid: string | null } | null
  invoice: {
    registered: boolean
    number: string | null
    registeredAt: string | null
  }
  cancellationData: {
    cancelledBy: string | null
    reason: string | null
    cancelledAt: string | null
  } | null
  createdAt: string
  scenarioTags: string[]
}
```

### OrderInstallment

```ts
{
  id: string
  orderUuid: string
  installmentNumber: number
  amount: number              // centavos
  dueDate: string | null
  status: "SCHEDULED" | "DONE" | "GRACED" | "PENDING" | "DELAYED" | "RENEGOTIATED" | "CANCELLED"
  payments: {
    paymentId: string
    assignedAmount: number    // centavos USD
    paymentMethod: { name: "PAGO_MOVIL" | "TRANSFERENCIA" | "EFECTIVO" | "TARJETA" }
    paymentStatus: "VERIFIED" | "CANCELLED" | "PENDING" | "RETURNED"
    referenceNumber: string | null
    amountVES: number | null  // centavos VES (pago móvil)
    paymentValidationDate: string | null
    createdAt: string
  }[]
}
```

### Payout

```ts
{
  id: string
  merchantId: number
  periodFrom: string
  periodTo: string
  periodLabel: string
  grossAmount: number         // centavos
  serviceFee: number
  retentions: number
  adjustments: number
  netAmount: number
  status: "PENDING" | "SENT" | "FAILED"
  sentAt: string | null
  bankReference: string | null
  bankAccountLast4: string
  scenarioTags: string[]
}
```

### Invoice

```ts
{
  id: string
  merchantId: number
  period: { from: string; to: string }
  periodLabel: string
  number: string
  amount: number              // centavos
  iva: number
  isrlRetained: number
  status: "ISSUED" | "SENT" | "NOT_SENT"
  sentToEmail: string | null
  sentAt: string | null
  pdfUrl: string
  scenarioTags: string[]
}
```

### MonthlyReport

```ts
{
  merchantId: number
  period: { from: string; to: string }
  periodLabel: string         // "2026-07"
  compensation: {
    totalAmount: number
    shouldMerchantPay: boolean
  }
  paymentTimeline: {
    stepKey: "reportSent" | "calculationConfirmed" | "invoiceGenerated" | "bankDeposit"
    status: "completed" | "in-progress" | "pending"
    date: string | null
  }[]
  missedInstallments: {
    amount: number
    expectedAmount: number
    receivedAmount: number
    advancedAmount: number
  }
  serviceFee: {
    amount: number
    techServicesAmount: number
    ivaAmount: number
    isrlRetainedAmount: number
  }
  errorsAndAdjustments: {
    amount: number
    paymentErrorsAmount: number
    periodAdjustmentsAmount: number
  }
}
```

### DailyConciliation

```ts
{
  id: number
  storeUuid: string
  createdAt: string
  date: string                // YYYY-MM-DD
  ordersCount: number
  totalChargedAmount: number
  totalFinancedAmount: number
  posConciliations: {
    pos: { name: string; uuid: string }
    ordersCount: number
    totalChargedAmount: number
    totalFinancedAmount: number
  }[]
}
```

### POS

```ts
{
  posUuid: string
  name: string
  storeUuid: string
  merchantId: number
  qrLinked: boolean
  qrCode: {
    activationCode: string
    status: "AVAILABLE" | "LINKED" | "DELETED" | "DISABLED"
  } | null
  lastOrderAt: string | null
  scenarioTags: string[]
}
```

### Promotion

```ts
{
  id: string
  title: string
  description: string | null
  status: "ACTIVE" | "INACTIVE"
  scheduleState: "NOT_STARTED" | "ACTIVE"
  startsAt: string | null
  endsAt: string | null
  enrollmentStatus: "AVAILABLE" | "JOINED" | "NONE"
  mechanics: { kind: "DISCOUNT" | "DP_REDUCTION" | "EXTRA_INSTALLMENT_PLAN"; label: string }[]
  conditionGroups: {
    id: string
    name: string
    conditions: { kind: "USER_LEVEL" | "INCLUDED_MERCHANTS"; label: string }[]
  }[]
  links: {
    infoDocumentUrl: string | null
    termsAndConditionsUrl: string | null
  }
  merchantId?: number
}
```

### Product

```ts
{
  uuid: string
  storeUuid: string
  sku: string
  name: string
  price: number               // centavos
  stock: number
  categoryId: number
  categoryName: string
  status: "ACTIVE" | "PAUSED"
  type: "PHYSICAL" | "DIGITAL"
  imgUrl: string
}
```

### InventoryJob

```ts
{
  jobUuid: string
  storeUuid: string
  fileName: string
  status: "PENDING" | "PROCESSING" | "COMPLETED" | "FAILED" | "COMPLETED_WITH_ERRORS"
  createdAt: string
  finishedAt: string | null
  totalProducts: number | null
  processedProducts: number | null
  successCount: number | null
  errorCount: number | null
  errors: {
    fileRow?: number
    fileColumn: string
    error: string
    sku?: string
  }[]
}
```

### Onboarding

```ts
{
  onboardingId: string
  merchantId?: number
  step: "BASIC_INFO" | "LEGAL_DOCUMENTS" | "BANK_VERIFICATION" | "PLAN_SELECTION" | "CHANNEL_SETUP" | "REVIEW" | "COMPLETED"
  status: "IN_PROGRESS" | "SUBMITTED" | "APPROVED" | "REJECTED"
  failedRules: string[]
  legalDocuments: { name: string; status: "PENDING" | "SIGNED" }[]
  bankAccountVerified: boolean
  readyToGo: boolean
  plan: string | null
  channelsSelected: string[]
  createdAt: string
  scenarioTags: string[]
}
```

### Report / Movement

```ts
// Report
{
  id: string
  title: string
  description: string | null
  longDescription: string | null
  url: string
}

// Movement
{
  id: string
  title: string
  description: string | null
  longDescription: string | null
  url: string
  date: string
}
```

---

## Endpoints

> **Los IDs de los ejemplos son ilustrativos.** El seed se genera al arrancar el servidor.
> Para obtener IDs reales, listar el endpoint padre o usar `GET /api/v1/scenarios/:tag`.

---

### Health

#### `GET /healthz`

```bash
curl http://localhost:3002/healthz
```

```json
{ "status": "ok" }
```

#### `GET /readyz`

```bash
curl http://localhost:3002/readyz
```

```json
{ "status": "ok", "seeded": true }
```

---

### Root

#### `GET /`

Índice de descubrimiento — nombre, versión, descripción y mapa de endpoints.

```bash
curl http://localhost:3002/
```

```json
{
  "name": "merchant-mock-server",
  "version": "0.1.0",
  "description": "Mock server orientado al aliado (merchant) de Cashea",
  "port": 3002,
  "endpoints": {
    "health": ["/healthz", "/readyz"],
    "merchants": [
      "GET /api/v1/merchants",
      "GET /api/v1/merchants/by-rif/:rif",
      "GET /api/v1/merchants/:id",
      "GET /api/v1/merchants/:id/stores",
      "GET /api/v1/merchants/:id/employees",
      "GET /api/v1/merchants/:id/payouts",
      "GET /api/v1/merchants/:id/invoices",
      "GET /api/v1/merchants/:id/monthly-reports",
      "GET /api/v1/merchants/:id/promotions"
    ],
    "stores": [
      "GET /api/v1/stores/:uuid",
      "GET /api/v1/stores/:uuid/daily-conciliation",
      "GET /api/v1/stores/:uuid/payment-methods",
      "GET /api/v1/stores/:uuid/pos",
      "GET /api/v1/stores/:uuid/products"
    ],
    "orders": [
      "GET /api/v1/orders",
      "GET /api/v1/orders/:orderNumber",
      "GET /api/v1/orders/:orderNumber/installments",
      "POST /api/v1/orders/:orderNumber/cancel",
      "POST /api/v1/orders/:orderNumber/invoice"
    ],
    "employees": [
      "GET /api/v1/employees/:id",
      "POST /api/v1/employees/:id/2fa/register-phone",
      "POST /api/v1/employees/:id/2fa/send-code",
      "POST /api/v1/employees/:id/2fa/verify-code"
    ],
    "scenarios": [
      "GET /api/v1/scenarios",
      "GET /api/v1/scenarios/:tag"
    ]
  }
}
```

---

### Merchants

#### `GET /api/v1/merchants`

Lista merchants con filtros y paginación.

| Query param | Tipo | Descripción |
|-------------|------|-------------|
| `search` | string | Busca por `legalName`, `tradeName` o RIF (parcial) |
| `rif` | string | Filtra por RIF (match tolerante) |
| `model` | MerchantModel | `BASE` o `EXPRESS` |
| `status` | MerchantStatus | `ACTIVE`, `INACTIVE`, `SUSPENDED` |
| `scenario` | string | Solo merchants con ese scenarioTag |
| `page` | number | Default 1 |
| `limit` | number | Default 20, máx 100 |

```bash
curl "http://localhost:3002/api/v1/merchants?search=tenda&status=ACTIVE&limit=5"
```

```json
{
  "data": [
    {
      "id": 1,
      "uuid": "mch-aaaa-1111",
      "rif": "J-40268443-6",
      "legalName": "Inversiones Tenda C.A.",
      "tradeName": "Tenda",
      "categoryId": 3,
      "model": "BASE",
      "merchantGroup": "Grupo Tenda",
      "status": "ACTIVE",
      "activeFcb": true,
      "fcbPeriod": "WEEKLY",
      "fcbStartDate": "2025-01-01T00:00:00.000Z",
      "adminEmail": "admin@tenda.com",
      "createdAt": "2024-03-15T00:00:00.000Z",
      "scenarioTags": []
    }
  ],
  "page": 1,
  "limit": 5,
  "total": 1,
  "totalPages": 1
}
```

#### `GET /api/v1/merchants/by-rif/:rif`

Lookup de merchant por RIF. Normaliza el RIF del path (mayúsculas, sin guiones/espaces, con o sin letra inicial).

```bash
curl http://localhost:3002/api/v1/merchants/by-rif/J-40268443-6
curl http://localhost:3002/api/v1/merchants/by-rif/402684436
```

Devuelve un objeto `Merchant` o `404`.

#### `GET /api/v1/merchants/:id`

Detalle de merchant por ID numérico o UUID.

```bash
curl http://localhost:3002/api/v1/merchants/1
curl http://localhost:3002/api/v1/merchants/mch-aaaa-1111
```

Devuelve un objeto `Merchant` o `404`.

#### `GET /api/v1/merchants/:id/stores`

Lista las tiendas del merchant.

```bash
curl http://localhost:3002/api/v1/merchants/1/stores
```

```json
{
  "data": [
    {
      "id": 10,
      "uuid": "str-aaaa-1111",
      "merchantId": 1,
      "name": "Tenda Sambil",
      "email": "sambil@tenda.com",
      "statusId": 2,
      "channels": ["IN_STORE", "REMOTE"],
      "isPhysical": true,
      "inventoryMigrated": true,
      "minimumDownPayment": 1000,
      "minimumFinanceableAmount": null,
      "address": {
        "name": "CC Sambil",
        "long": -66.8792,
        "lat": 10.4978,
        "location": "Caracas",
        "shipmentsEnabled": true
      },
      "createdAt": "2024-03-20T00:00:00.000Z",
      "scenarioTags": [],
      "invoiceRegistrationFailing": false,
      "orderCreateConnectionError": false
    }
  ]
}
```

#### `GET /api/v1/merchants/:id/employees`

Lista los empleados del merchant.

| Query param | Tipo | Descripción |
|-------------|------|-------------|
| `role` | EmployeeRole | `ADMIN`, `MANAGER`, `CASHIER` |

```bash
curl "http://localhost:3002/api/v1/merchants/1/employees?role=ADMIN"
```

Devuelve `{ data: Employee[] }`.

#### `GET /api/v1/merchants/:id/payouts`

Lista los payouts (transferencias de Cashea al merchant), ordenados desc por `periodFrom`.

| Query param | Tipo | Descripción |
|-------------|------|-------------|
| `from` | ISO date | Filtra `periodFrom >= from` |
| `to` | ISO date | Filtra `periodTo <= to` |
| `status` | PayoutStatus | `PENDING`, `SENT`, `FAILED` |

```bash
curl "http://localhost:3002/api/v1/merchants/1/payouts?status=PENDING"
```

```json
{
  "data": [
    {
      "id": "pay-aaaa-1111",
      "merchantId": 1,
      "periodFrom": "2026-07-01T00:00:00.000Z",
      "periodTo": "2026-07-31T00:00:00.000Z",
      "periodLabel": "2026-07",
      "grossAmount": 2500000,
      "serviceFee": 75000,
      "retentions": 12000,
      "adjustments": 0,
      "netAmount": 2413000,
      "status": "PENDING",
      "sentAt": null,
      "bankReference": null,
      "bankAccountLast4": "1234",
      "scenarioTags": []
    }
  ]
}
```

#### `GET /api/v1/merchants/:id/payouts/:payoutId`

Detalle de un payout específico.

```bash
curl http://localhost:3002/api/v1/merchants/1/payouts/pay-aaaa-1111
```

Devuelve un objeto `Payout` o `404`.

#### `GET /api/v1/merchants/:id/invoices`

Lista las facturas del merchant, ordenadas desc por `period.from`.

| Query param | Tipo | Descripción |
|-------------|------|-------------|
| `from` | ISO date | Filtra `period.from >= from` |
| `to` | ISO date | Filtra `period.to <= to` |
| `status` | InvoiceStatus | `ISSUED`, `SENT`, `NOT_SENT` |

```bash
curl "http://localhost:3002/api/v1/merchants/1/invoices?status=NOT_SENT"
```

Devuelve `{ data: Invoice[] }`.

#### `GET /api/v1/merchants/:id/monthly-reports`

Reportes mensuales del merchant. Devuelve el reporte más reciente como `current`, la lista de periodos disponibles y todos los reportes.

```bash
curl http://localhost:3002/api/v1/merchants/1/monthly-reports
```

```json
{
  "current": {
    "merchantId": 1,
    "period": { "from": "2026-07-01T00:00:00.000Z", "to": "2026-07-31T00:00:00.000Z" },
    "periodLabel": "2026-07",
    "compensation": { "totalAmount": 2413000, "shouldMerchantPay": false },
    "paymentTimeline": [
      { "stepKey": "reportSent", "status": "completed", "date": "2026-08-01T00:00:00.000Z" },
      { "stepKey": "calculationConfirmed", "status": "in-progress", "date": null },
      { "stepKey": "invoiceGenerated", "status": "pending", "date": null },
      { "stepKey": "bankDeposit", "status": "pending", "date": null }
    ],
    "missedInstallments": { "amount": 5000, "expectedAmount": 100000, "receivedAmount": 95000, "advancedAmount": 2000 },
    "serviceFee": { "amount": 75000, "techServicesAmount": 50000, "ivaAmount": 9000, "isrlRetainedAmount": 3000 },
    "errorsAndAdjustments": { "amount": 1500, "paymentErrorsAmount": 1000, "periodAdjustmentsAmount": 500 }
  },
  "availablePeriods": [
    { "period": "2026-07", "from": "2026-07-01T00:00:00.000Z", "to": "2026-07-31T00:00:00.000Z" },
    { "period": "2026-06", "from": "2026-06-01T00:00:00.000Z", "to": "2026-06-30T00:00:00.000Z" }
  ],
  "data": [ /* MonthlyReport[] */ ]
}
```

#### `GET /api/v1/merchants/:id/monthly-reports/:period`

Reporte de un periodo específico (`period` en formato `YYYY-MM`).

```bash
curl http://localhost:3002/api/v1/merchants/1/monthly-reports/2026-07
```

Devuelve un objeto `MonthlyReport` o `404`.

#### `GET /api/v1/merchants/:id/monthly-reports/:period/service-fee`

Desglose de service fee del periodo.

```json
{
  "period": { "from": "2026-07-01T00:00:00.000Z", "to": "2026-07-31T00:00:00.000Z" },
  "amount": 75000,
  "techServicesAmount": 50000,
  "ivaAmount": 9000,
  "isrlRetainedAmount": 3000
}
```

#### `GET /api/v1/merchants/:id/monthly-reports/:period/missed-installments`

Desglose de cuotas incumplidas del periodo.

```json
{
  "period": { "from": "2026-07-01T00:00:00.000Z", "to": "2026-07-31T00:00:00.000Z" },
  "amount": 5000,
  "expectedAmount": 100000,
  "receivedAmount": 95000,
  "advancedAmount": 2000
}
```

#### `GET /api/v1/merchants/:id/monthly-reports/:period/errors-and-adjustments`

Desglose de errores y ajustes del periodo.

```json
{
  "period": { "from": "2026-07-01T00:00:00.000Z", "to": "2026-07-31T00:00:00.000Z" },
  "amount": 1500,
  "paymentErrorsAmount": 1000,
  "periodAdjustmentsAmount": 500
}
```

#### `GET /api/v1/merchants/:id/promotions`

Lista las promociones disponibles para el merchant.

```bash
curl http://localhost:3002/api/v1/merchants/1/promotions
```

Devuelve `{ data: Promotion[] }`.

#### `POST /api/v1/merchants/:id/promotions/:promotionId/join`

Inscribe al merchant en una promoción.

```bash
curl -X POST http://localhost:3002/api/v1/merchants/1/promotions/promo-001/join \
  -H "Content-Type: application/json" \
  -d '{}'
```

**Respuesta 200:**

```json
{
  "enrollmentStatus": "JOINED",
  "joinedAt": "2026-08-05T01:00:00.000Z"
}
```

| Status | Error | Cuándo |
|--------|-------|--------|
| 403 | `not_eligible` | `enrollmentStatus` es `NONE` (no cumple criterios) |
| 409 | `already_joined` | Ya está inscrito |

#### `POST /api/v1/merchants/:id/promotions/:promotionId/leave`

Desinscribe al merchant de una promoción.

```bash
curl -X POST http://localhost:3002/api/v1/merchants/1/promotions/promo-001/leave \
  -H "Content-Type: application/json" \
  -d '{}'
```

**Respuesta 200:**

```json
{
  "enrollmentStatus": "AVAILABLE",
  "leftAt": "2026-08-05T01:00:00.000Z"
}
```

| Status | Error | Cuándo |
|--------|-------|--------|
| 409 | `not_joined` | No está inscrito |

---

### Stores

#### `GET /api/v1/stores/:uuid`

Detalle de tienda por UUID.

```bash
curl http://localhost:3002/api/v1/stores/str-aaaa-1111
```

Devuelve un objeto `Store` o `404`.

#### `GET /api/v1/stores/:uuid/daily-conciliation`

Conciliación diaria de la tienda.

| Query param | Tipo | Descripción |
|-------------|------|-------------|
| `date` | YYYY-MM-DD | Default: fecha de hoy |

```bash
curl "http://localhost:3002/api/v1/stores/str-aaaa-1111/daily-conciliation?date=2026-08-04"
```

```json
{
  "id": 100,
  "storeUuid": "str-aaaa-1111",
  "createdAt": "2026-08-04T23:59:00.000Z",
  "date": "2026-08-04",
  "ordersCount": 15,
  "totalChargedAmount": 350000,
  "totalFinancedAmount": 280000,
  "posConciliations": [
    {
      "pos": { "name": "Caja 1", "uuid": "pos-aaaa-1111" },
      "ordersCount": 8,
      "totalChargedAmount": 180000,
      "totalFinancedAmount": 140000
    }
  ]
}
```

#### `GET /api/v1/stores/:uuid/daily-conciliation/last`

Última conciliación disponible (más reciente por fecha).

```bash
curl http://localhost:3002/api/v1/stores/str-aaaa-1111/daily-conciliation/last
```

Devuelve un objeto `DailyConciliation` o `404`.

#### `GET /api/v1/stores/:uuid/daily-conciliation/history`

Historial de conciliaciones, ordenado desc por fecha.

| Query param | Tipo | Descripción |
|-------------|------|-------------|
| `limit` | number | Default 30 |
| `offset` | number | Default 0 |

```bash
curl "http://localhost:3002/api/v1/stores/str-aaaa-1111/daily-conciliation/history?limit=7"
```

```json
{
  "data": [ /* DailyConciliation[] */ ],
  "total": 30,
  "limit": 7,
  "offset": 0
}
```

#### `GET /api/v1/stores/:uuid/payment-methods`

Métodos de pago configurados en la tienda.

| Query param | Tipo | Descripción |
|-------------|------|-------------|
| `category` | string | Ej: `IN_STORE` |

```bash
curl "http://localhost:3002/api/v1/stores/str-aaaa-1111/payment-methods?category=IN_STORE"
```

Devuelve `{ data: PaymentMethod[] }`.

#### `GET /api/v1/stores/:uuid/pos`

Lista las cajas (POS) de la tienda.

```bash
curl http://localhost:3002/api/v1/stores/str-aaaa-1111/pos
```

Devuelve `{ data: POS[] }`.

#### `GET /api/v1/stores/:uuid/pos/qr-summary`

Resumen de cobertura QR de la tienda.

```bash
curl http://localhost:3002/api/v1/stores/str-aaaa-1111/pos/qr-summary
```

```json
{
  "storeUuid": "str-aaaa-1111",
  "storeName": "Tenda Sambil",
  "totalPos": 3,
  "posWithoutQr": 1
}
```

#### `GET /api/v1/stores/:uuid/products`

Catálogo de productos de la tienda con paginación.

| Query param | Tipo | Descripción |
|-------------|------|-------------|
| `search` | string | Busca por `name` o `sku` |
| `sku` | string | Filtra por SKU exacto |
| `page` | number | Default 1 |
| `limit` | number | Default 20, máx 100 |

```bash
curl "http://localhost:3002/api/v1/stores/str-aaaa-1111/products?search=auricular&limit=5"
```

Devuelve respuesta paginada de `Product`.

#### `GET /api/v1/stores/:uuid/inventory/jobs`

Jobs de carga masiva de inventario de la tienda.

```bash
curl http://localhost:3002/api/v1/stores/str-aaaa-1111/inventory/jobs
```

Devuelve `{ data: InventoryJob[] }`.

#### `GET /api/v1/stores/:uuid/inventory/jobs/:jobUuid`

Detalle de un job de inventario específico.

```bash
curl http://localhost:3002/api/v1/stores/str-aaaa-1111/inventory/jobs/job-aaaa-1111
```

Devuelve un objeto `InventoryJob` o `404`.

---

### Orders

#### `GET /api/v1/orders`

Lista de órdenes con filtros, ordenadas desc por `createdAt`.

| Query param | Tipo | Descripción |
|-------------|------|-------------|
| `storeUuid` | string | Filtra por tienda |
| `merchantId` | number | Filtra por merchant |
| `status` | OrderStatus | `IN_PROGRESS`, `CLOSED`, `OPEN`, `CANCELLED`, `PENDING` |
| `channel` | OrderChannel | `IN_STORE`, `REMOTE`, `OFFLINE`, `IN_APP` |
| `from` | ISO date | Filtra `createdAt >= from` |
| `to` | ISO date | Filtra `createdAt <= to` |
| `scenario` | string | Solo órdenes con ese scenarioTag |
| `page` | number | Default 1 |
| `limit` | number | Default 20, máx 100 |

```bash
curl "http://localhost:3002/api/v1/orders?merchantId=1&status=IN_PROGRESS&limit=10"
```

#### `GET /api/v1/orders/cancellation-reasons`

Lista los motivos de cancelación disponibles.

| Query param | Tipo | Descripción |
|-------------|------|-------------|
| `role` | EmployeeRole | Si es `CASHIER`, devuelve lista vacía |

```bash
curl "http://localhost:3002/api/v1/orders/cancellation-reasons?role=MANAGER"
```

```json
{
  "data": [
    { "id": 1, "reason": "Solicitud del cliente" },
    { "id": 2, "reason": "Error de captura" },
    { "id": 3, "reason": "Fraude sospechado" },
    { "id": 4, "reason": "Producto sin stock" }
  ]
}
```

#### `GET /api/v1/orders/:orderNumber`

Detalle de orden por número de orden (9 dígitos).

```bash
curl http://localhost:3002/api/v1/orders/100023456
```

Devuelve un objeto `Order` o `404`.

#### `GET /api/v1/orders/:orderNumber/installments`

Cuotas de la orden, cada una con sus pagos asociados.

```bash
curl http://localhost:3002/api/v1/orders/100023456/installments
```

```json
{
  "data": [
    {
      "id": "inst-aaaa-1111",
      "orderUuid": "ord-uuid-1111",
      "installmentNumber": 1,
      "amount": 25000,
      "dueDate": "2026-07-15T00:00:00.000Z",
      "status": "DONE",
      "payments": [
        {
          "paymentId": "pmt-1111",
          "assignedAmount": 25000,
          "paymentMethod": { "name": "PAGO_MOVIL" },
          "paymentStatus": "VERIFIED",
          "referenceNumber": "PM-789456123",
          "amountVES": 1450000,
          "paymentValidationDate": "2026-07-14T10:00:00.000Z",
          "createdAt": "2026-07-14T10:00:00.000Z"
        }
      ]
    },
    {
      "id": "inst-aaaa-1112",
      "orderUuid": "ord-uuid-1111",
      "installmentNumber": 2,
      "amount": 25000,
      "dueDate": "2026-08-15T00:00:00.000Z",
      "status": "PENDING",
      "payments": []
    }
  ]
}
```

#### `GET /api/v1/orders/:orderNumber/payments`

Todos los pagos de la orden, aplanados desde todas las cuotas. Cada pago incluye `installmentNumber`.

```bash
curl http://localhost:3002/api/v1/orders/100023456/payments
```

Devuelve `{ data: Payment[] }`.

#### `POST /api/v1/orders/:orderNumber/cancel`

Cancela una orden. Aplica reglas estrictas según el rol del empleado.

**Body:**

```json
{
  "employeeId": "emp-aaaa-1111",
  "reasonId": 1,
  "securityCode": "123456"
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `employeeId` | string | **Requerido.** ID del empleado que cancela |
| `reasonId` | number | ID del motivo de cancelación (ver `cancellation-reasons`) |
| `securityCode` | string | Requerido solo para MANAGER. Código mock: `"123456"` |

```bash
curl -X POST http://localhost:3002/api/v1/orders/100023456/cancel \
  -H "Content-Type: application/json" \
  -d '{"employeeId":"emp-aaaa-1111","reasonId":1,"securityCode":"123456"}'
```

**Respuesta 200:**

```json
{
  "status": "cancelled",
  "orderNumber": "100023456",
  "cancelledBy": "María González",
  "reason": "Solicitud del cliente"
}
```

**Reglas por rol:**

| Rol | Reglas |
|-----|--------|
| `ADMIN` | Sin restricciones. Puede cancelar cualquier orden cancelable. |
| `MANAGER` | Requiere `securityCode` (mock `"123456"`), empleado debe tener `securityCodeSet=true`, y la orden debe ser del mismo día calendario. |
| `CASHIER` | No puede cancelar. Siempre `403`. |

**Posibles errores:**

| Status | Error | Cuándo |
|--------|-------|--------|
| 400 | `employeeId es obligatorio` | Falta `employeeId` |
| 403 | `El empleado no pertenece al merchant de la orden` | `merchantId` no coincide |
| 409 | `order_already_cancelled` | La orden ya está cancelada |
| 409 | `order_not_cancellable` | Estado no cancelable (ej: `CLOSED`) |
| 403 | `role_not_allowed_to_cancel` | Rol `CASHIER` |
| 403 | `security_code_not_set` | MANAGER sin `securityCodeSet` configurado |
| 403 | `security_code_required` | MANAGER, falta o formato inválido de `securityCode` |
| 409 | `invalid_security_code` | MANAGER, código incorrecto |
| 409 | `out_of_day_window` | MANAGER, orden no es del mismo día |

> **Efecto:** la orden pasa a `CANCELLED`, `deliveryStatus` → `CANCELLED`, se registra `cancellationData`, y las cuotas no-`DONE` pasan a `CANCELLED`.

#### `POST /api/v1/orders/:orderNumber/invoice`

Registra una factura en la orden.

**Body:**

```json
{
  "employeeId": "emp-aaaa-1111",
  "invoiceNumber": "001-002-003456789"
}
```

```bash
curl -X POST http://localhost:3002/api/v1/orders/100023456/invoice \
  -H "Content-Type: application/json" \
  -d '{"employeeId":"emp-aaaa-1111","invoiceNumber":"001-002-003456789"}'
```

**Respuesta 200:**

```json
{
  "status": "registered",
  "orderNumber": "100023456",
  "invoiceNumber": "001-002-003456789"
}
```

| Status | Error | Cuándo |
|--------|-------|--------|
| 400 | `employeeId e invoiceNumber son obligatorios` | Faltan campos |
| 503 | `invoice_registration_error` | La store tiene flag `invoiceRegistrationFailing` (escenario) |
| 409 | `invoice_already_registered` | La orden ya tiene factura registrada |

---

### Employees

#### `GET /api/v1/employees/:id`

Detalle de empleado por ID.

```bash
curl http://localhost:3002/api/v1/employees/emp-aaaa-1111
```

```json
{
  "id": "emp-aaaa-1111",
  "storeUuid": "str-aaaa-1111",
  "merchantId": 1,
  "name": "María González",
  "email": "maria@tenda.com",
  "role": "MANAGER",
  "onboardingStatus": "FINISHED",
  "phoneRegistered": true,
  "phoneNumber": "+58 412-5550123",
  "mustChangePassword": false,
  "securityCodeSet": true,
  "lastLoginAt": "2026-08-01T12:00:00.000Z",
  "createdAt": "2025-06-01T00:00:00.000Z",
  "scenarioTags": [],
  "otpNeverArrives": false
}
```

#### `POST /api/v1/employees/:id/2fa/register-phone`

Registra o actualiza el teléfono del empleado para 2FA.

**Body:**

```json
{ "phone": "+58 412-5550123" }
```

```bash
curl -X POST http://localhost:3002/api/v1/employees/emp-aaaa-1111/2fa/register-phone \
  -H "Content-Type: application/json" \
  -d '{"phone":"+58 412-5550123"}'
```

**Respuesta 200 (teléfono nuevo):**

```json
{
  "alreadyRegistered": false,
  "phoneRegistered": true,
  "phoneNumber": "+58 412-5550123"
}
```

**Respuesta 200 (ya era su teléfono):**

```json
{
  "alreadyRegistered": true,
  "message": "El teléfono proporcionado ya es el registrado para este empleado",
  "phoneRegistered": true
}
```

| Status | Error | Cuándo |
|--------|-------|--------|
| 400 | `phone es obligatorio` | Falta `phone` |

#### `POST /api/v1/employees/:id/2fa/send-code`

Envía un código OTP al teléfono registrado.

```bash
curl -X POST http://localhost:3002/api/v1/employees/emp-aaaa-1111/2fa/send-code \
  -H "Content-Type: application/json" \
  -d '{}'
```

**Respuesta 200:**

```json
{ "sent": true }
```

| Status | Error | Cuándo |
|--------|-------|--------|
| 403 | `phone_not_registered` | El empleado no tiene teléfono registrado |

#### `POST /api/v1/employees/:id/2fa/verify-code`

Verifica el código OTP. **Código mock: `"123456"`.**

**Body:**

```json
{ "code": "123456" }
```

```bash
curl -X POST http://localhost:3002/api/v1/employees/emp-aaaa-1111/2fa/verify-code \
  -H "Content-Type: application/json" \
  -d '{"code":"123456"}'
```

**Respuesta 200:**

```json
{ "verified": true }
```

| Status | Error | Cuándo |
|--------|-------|--------|
| 400 | `code es obligatorio` | Falta `code` |
| 409 | `code_expired` | El flag `otpNeverArrives` está activo (escenario) |
| 409 | `invalid_code` | Código incorrecto |

---

### POS

#### `GET /api/v1/pos/:uuid`

Detalle de POS por UUID.

```bash
curl http://localhost:3002/api/v1/pos/pos-aaaa-1111
```

Devuelve un objeto `POS` o `404`.

#### `POST /api/v1/pos/:uuid/link-qr`

Vincula un código QR al POS. Setea `qrLinked=true` y `qrCode.status="LINKED"`.

**Body:**

```json
{ "activationCode": "ACT-123456" }
```

```bash
curl -X POST http://localhost:3002/api/v1/pos/pos-aaaa-1111/link-qr \
  -H "Content-Type: application/json" \
  -d '{"activationCode":"ACT-123456"}'
```

**Respuesta 200:**

```json
{
  "status": "linked",
  "posUuid": "pos-aaaa-1111",
  "activationCode": "ACT-123456"
}
```

| Status | Error | Cuándo |
|--------|-------|--------|
| 400 | `activationCode es obligatorio` | Falta `activationCode` |

---

### Onboarding

#### `GET /api/v1/onboarding/:onboardingId`

Estado de onboarding por ID.

```bash
curl http://localhost:3002/api/v1/onboarding/onb-aaaa-1111
```

```json
{
  "onboardingId": "onb-aaaa-1111",
  "merchantId": 1,
  "step": "LEGAL_DOCUMENTS",
  "status": "IN_PROGRESS",
  "failedRules": ["contract_signature_missing"],
  "legalDocuments": [
    { "name": "Contrato de Cesión", "status": "PENDING" },
    { "name": "Acuerdo de Servicio", "status": "SIGNED" }
  ],
  "bankAccountVerified": true,
  "readyToGo": false,
  "plan": "EXPRESS",
  "channelsSelected": ["IN_STORE", "REMOTE"],
  "createdAt": "2026-06-01T00:00:00.000Z",
  "scenarioTags": ["model_migration_pending"]
}
```

Devuelve un objeto `Onboarding` o `404`.

---

### Reports

#### `GET /api/v1/reports`

Catálogo de reportes disponibles.

```bash
curl http://localhost:3002/api/v1/reports
```

Devuelve `{ data: Report[] }`.

#### `GET /api/v1/movements`

Movimientos recientes, ordenados desc por fecha.

```bash
curl http://localhost:3002/api/v1/movements
```

Devuelve `{ data: Movement[] }`.

---

### Scenarios

Los escenarios son etiquetas que se asignan a entidades del seed (merchants, stores, órdenes, empleados, payouts, facturas, POS, onboardings) para crear problemas realistas que un agente de IA debe resolver. Un agente en producción **no** usaría estos endpoints — descubriría los problemas navegando la data.

#### `GET /api/v1/scenarios`

Catálogo completo de escenarios con los IDs reales de las entidades afectadas.

```bash
curl http://localhost:3002/api/v1/scenarios
```

```json
{
  "data": [
    {
      "tag": "2fa_phone_not_registered",
      "description": "Empleado admin con phoneRegistered=false, reportes bloqueados",
      "affected": {
        "merchants": [1],
        "stores": ["str-aaaa-1111"],
        "orders": [],
        "employees": ["emp-aaaa-2222"],
        "payouts": [],
        "invoices": [],
        "pos": [],
        "onboardings": []
      }
    }
  ]
}
```

#### `GET /api/v1/scenarios/:tag`

Detalle completo de un escenario: todas las entidades etiquetadas con ese tag.

```bash
curl http://localhost:3002/api/v1/scenarios/cashier_cannot_cancel
```

```json
{
  "tag": "cashier_cannot_cancel",
  "description": "Orden cancelable, empleado CASHIER intenta cancelar",
  "merchants": [ /* Merchant[] */ ],
  "stores": [ /* Store[] */ ],
  "orders": [ /* Order[] */ ],
  "employees": [ /* Employee[] */ ],
  "payouts": [ /* Payout[] */ ],
  "invoices": [ /* Invoice[] */ ],
  "pos": [ /* POS[] */ ],
  "onboardings": [ /* Onboarding[] */ ]
}
```

Si no hay entidades con ese tag → `404`.

---

## Catálogo de escenarios

| # | Tag | Qué simula | Endpoint que lo revela | Qué debe responder el agente |
|---|-----|------------|------------------------|-------------------------------|
| 1 | `2fa_phone_not_registered` | Empleado admin con `phoneRegistered=false`, reportes bloqueados | `GET /employees/:id` → `phoneRegistered: false` | Guiar al aliado a registrar su teléfono vía `POST /2fa/register-phone` antes de acceder a reportes |
| 2 | `2fa_phone_already_registered` | El teléfono que el aliado pide registrar ya es el suyo | `POST /2fa/register-phone` → `{ alreadyRegistered: true }` | Informar que el teléfono ya está registrado, no hay nada que cambiar |
| 3 | `2fa_otp_never_arrives` | `send-code` responde 200 pero `verify-code` siempre devuelve 409 `code_expired` | `POST /2fa/verify-code` → 409 `code_expired` | Identificar problema de entrega de OTP, escalar a equipo técnico |
| 4 | `credentials_invite_not_delivered` | Empleado `IN_PROGRESS` con `lastLoginAt=null`, invitación no entregada | `GET /employees/:id` → `onboardingStatus: IN_PROGRESS`, `lastLoginAt: null` | Reenviar invitación o verificar email del aliado |
| 5 | `password_change_required` | Empleado con `mustChangePassword=true` | `GET /employees/:id` → `mustChangePassword: true` | Instruir al aliado cambiar contraseña en próximo login |
| 6 | `security_code_not_set` | Gerente con `securityCodeSet=false`, no puede cancelar órdenes | `GET /employees/:id` → `securityCodeSet: false`; `POST /orders/:n/cancel` → 403 `security_code_required` | Explicar que debe configurar código de seguridad antes de cancelar |
| 7 | `cashier_cannot_cancel` | Orden cancelable, empleado CASHIER intenta cancelar | `POST /orders/:n/cancel` → 403 `role_not_allowed_to_cancel` | Explicar que solo Admin o Gerente pueden cancelar, derivar al supervisor |
| 8 | `cancel_out_of_day_window` | Gerente intenta cancelar orden de ayer | `POST /orders/:n/cancel` → 409 `out_of_day_window` | Explicar que el Gerente solo puede cancelar órdenes del mismo día; días anteriores → escalar a Admin |
| 9 | `order_create_connection_error` | Store con flag que hace fallar creación de orden | Store tiene flag interno `orderCreateConnectionError` | Identificar problema técnico de conexión, escalar a soporte técnico |
| 10 | `invoice_registration_failing` | Orden CLOSED con `invoice.registered=false` y `POST /invoice` devuelve 503 | `POST /orders/:n/invoice` → 503; `GET /orders/:n` → `invoice.registered: false` | Identificar falla técnica al registrar factura, escalar a soporte |
| 11 | `order_incident_lost_shipment` | Orden con `shipmentStatus` en `LOST_OR_STOLEN` | `GET /orders/:n` → `shipmentStatus: LOST_OR_STOLEN` | Abrir ticket de investigación logística |
| 12 | `down_payment_not_reflected` | Orden por LINK con pago móvil PENDING, `referenceNumber` + `amountVES` presentes | `GET /orders/:n/installments` → cuota con `paymentStatus: PENDING` | Verificar el pago móvil por `referenceNumber` y confirmar que está en proceso de conciliación |
| 13 | `payout_missing_for_period` | Periodo cerrado, monthlyReport emitido, `payout.status=PENDING` sin `sentAt` | `GET /merchants/:id/payouts?status=PENDING` → payout sin `sentAt` | Confirmar que el pago está programado pero pendiente de transferencia |
| 14 | `payout_amount_mismatch` | `payout.netAmount` ≠ `monthlyReport.compensation.totalAmount` | Comparar `GET /payouts` con `GET /monthly-reports/:period` | Abrir reclamo por discrepancia en el monto transferido |
| 15 | `invoices_not_sent_multi_month` | 5 meses consecutivos con `invoice.status=NOT_SENT` | `GET /merchants/:id/invoices?status=NOT_SENT` → múltiples facturas | Reenviar las facturas pendientes al email del aliado |
| 16 | `isrl_retention_disputed` | `serviceFee.isrlRetainedAmount` alto en un periodo | `GET /monthly-reports/:period/service-fee` → ISRL alto | Explicar cómo se calcula la retención de ISRL, derivar a contabilidad si hay disputa |
| 17 | `daily_conciliation_mismatch` | `ordersCount` no cuadra con las órdenes del día | `GET /stores/:uuid/daily-conciliation` → `ordersCount` inflado | Identificar descuadre en conciliación, escalar a operaciones |
| 18 | `pos_qr_not_linked` | Caja creada sin QR vinculado | `GET /stores/:uuid/pos` → POS con `qrLinked: false` | Guiar al aliado para vincular QR vía `POST /pos/:uuid/link-qr` |
| 19 | `promotion_not_eligible` | Promo ACTIVE con `enrollmentStatus=NONE` y condición `INCLUDED_MERCHANTS` | `GET /merchants/:id/promotions` → promo con `enrollmentStatus: NONE` | Explicar que el comercio no cumple los criterios de elegibilidad de la promo |
| 20 | `model_migration_pending` | Merchant BASE con solicitud a EXPRESS y contrato sin firmar | `GET /onboarding/:id` → documentos PENDING; `GET /merchants/:id` → `model: BASE` | Guiar al aliado a firmar el contrato de cesión para completar migración |
| 21 | `onboarding_stuck_documents` | Onboarding con `legalDocuments` en PENDING y `failedRules` | `GET /onboarding/:id` → documentos PENDING y `failedRules` | Listar los documentos pendientes y guiar al aliado para firmarlos |
| 22 | `inventory_bulk_job_failed` | Job de carga masiva en FAILED con errores por fila | `GET /stores/:uuid/inventory/jobs` → job FAILED con `errors[]` | Mostrar los errores específicos por fila y sugerir corregir el archivo |

---

## Seed data

El seed repite entidades y escenarios con una semilla fija; las fechas son
relativas a la hora de arranque.

| Entidad | Cantidad aprox. |
|---------|----------------|
| Merchants | 5 |
| Stores | 10 |
| Employees | 36 |
| Orders | 100 |
| Installments | 597 |
| Payouts | 8 |
| Invoices | 14 |
| Monthly reports | 12 |
| POS | 13 |
| Products | 89 |
| Inventory jobs | 3 |
| Onboardings | 3 |
| Daily conciliations | 33 |
| Entidades con escenarios | 30 |

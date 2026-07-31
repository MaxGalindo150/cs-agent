# BNPL Mock Server — API Reference

> **Base URL:** `http://localhost:3001`
> **Content-Type:** `application/json`
> **Latencia simulada:** 40–200ms por request

Todas las rutas de dominio están bajo `/api/v1`. Las de health están en la raíz.

---

## Convenciones

### Dinero

Todos los montos están en **centavos (enteros)**. Para mostrar en USD/MXN, dividir entre 100.

```
15000 → $150.00
99 → $0.99
```

### Timestamps

ISO 8601 con zona horaria:

```
2026-07-15T10:30:00.000Z
```

Campos nullable usan `null`, no se omiten.

### Paginación

Los endpoints de lista devuelven:

```json
{
  "data": [ ... ],
  "page": 1,
  "limit": 20,
  "total": 50,
  "totalPages": 3
}
```

Query params por defecto: `page=1`, `limit=20` (máximo 100).

Algunos endpoints (payment-methods, addresses, installments by order) devuelven `{ data: [...] }` sin metadatos de paginación.

### Errores

Cualquier respuesta non-2xx:

```json
{ "error": "Human-readable message" }
```

| Status | Cuándo |
|--------|--------|
| 400 | Body inválido o faltan campos requeridos |
| 404 | Recurso no encontrado |
| 409 | Conflicto (ej: cuota ya pagada, puntos insuficientes) |

---

## Enums del dominio

| Enum | Valores |
|------|---------|
| UserStatus | `active` \| `suspended` \| `blocked` |
| KycStatus | `unverified` \| `pending` \| `verified` \| `rejected` |
| Tier | `bronze` \| `silver` \| `gold` \| `platinum` |
| OrderStatus | `pending` \| `approved` \| `active` \| `completed` \| `defaulted` \| `cancelled` |
| OrderPlan | `pay_in_4` \| `pay_in_30` \| `monthly_3` \| `monthly_6` \| `monthly_12` |
| InstallmentStatus | `upcoming` \| `due` \| `paid` \| `overdue` \| `failed` |
| ShipmentStatus | `preparing` \| `shipped` \| `in_transit` \| `out_for_delivery` \| `delivered` \| `returned` \| `failed` |
| Carrier | `dhl` \| `fedex` \| `ups` \| `estafeta` \| `local` |
| TxnType | `purchase` \| `payment` \| `refund` \| `fee` \| `interest` \| `points_earned` \| `points_redeemed` \| `adjustment` |
| TxnDirection | `debit` \| `credit` |
| PaymentStatus | `pending_validation` \| `validated` \| `reassigned` |
| PaymentMethod | `spei` \| `card` \| `cash` \| `bank_transfer` |
| ScenarioTag | Ver catálogo de escenarios más abajo |

---

## Data Models

### User

```ts
{
  id: string
  email: string
  phone: string
  firstName: string
  lastName: string
  dob: string              // ISO datetime
  status: UserStatus
  kycStatus: KycStatus
  avatarUrl: string | null
  scenarioTags: ScenarioTag[]
  createdAt: string
}
```

### Address

```ts
{
  id: string
  userId: string
  type: "shipping" | "billing"
  line1: string
  line2: string | null
  city: string
  state: string
  zip: string
  country: string
  isDefault: boolean
  createdAt: string
}
```

### PaymentMethod (Card / Bank Account)

```ts
{
  id: string
  userId: string
  type: "card" | "bank_account"
  brand: "visa" | "mastercard" | "amex" | null
  bankName: string | null
  last4: string
  expiryMonth: number | null
  expiryYear: number | null
  isDefault: boolean
  createdAt: string
}
```

### CreditAccount

```ts
{
  id: string
  userId: string
  creditLimit: number          // centavos
  outstandingBalance: number   // centavos — suma de cuotas no pagadas
  availableCredit: number      // creditLimit - outstandingBalance
  interestRate: number         // APR %
  utilizationPct: number       // outstanding / limit * 100
  status: "active" | "frozen" | "closed"
  createdAt: string
  updatedAt: string
}
```

### Membership

```ts
{
  id: string
  userId: string
  pointsBalance: number
  tier: Tier
  tierProgress: {
    current: number            // puntos actuales
    needed: number             // puntos para el siguiente tier
    pct: number                // % de progreso (0–100)
  }
  totalSpent: number           // centavos
  joinedAt: string
  updatedAt: string
}
```

**Umbrales de tier:**

| Tier | Puntos mínimos | Puntos máximos |
|------|---------------|----------------|
| bronze | 0 | 999 |
| silver | 1,000 | 4,999 |
| gold | 5,000 | 19,999 |
| platinum | 20,000 | ∞ |

### Order

```ts
{
  id: string
  userId: string
  merchantId: string
  merchantName: string
  items: OrderItem[]
  subtotal: number             // centavos
  shipping: number             // centavos
  tax: number                  // centavos (IVA 16%)
  totalAmount: number          // centavos
  plan: OrderPlan
  status: OrderStatus
  financing: {
    principal: number          // centavos
    interest: number           // centavos
    fees: number               // centavos
    apr: number                // %
    termMonths: number
  }
  installmentCount: number
  refundRequested: boolean
  refundReason: string | null
  createdAt: string
  updatedAt: string
}
```

### OrderItem

```ts
{
  sku: string
  name: string
  qty: number                  // entero positivo
  unitPrice: number            // centavos
}
```

### Installment

```ts
{
  id: string
  orderId: string
  userId: string
  number: number               // 1-based
  amountDue: number            // centavos — total a pagar
  principal: number            // centavos
  interest: number             // centavos
  fees: number                 // centavos (solo primera cuota normalmente)
  dueDate: string              // ISO datetime
  paidDate: string | null
  status: InstallmentStatus
  paymentMethodId: string | null
  externalReference: string | null  // referencia bancaria externa
}
```

### Shipment

```ts
{
  id: string
  orderId: string
  userId: string
  carrier: Carrier
  trackingNumber: string
  status: ShipmentStatus
  address: {
    line1: string
    city: string
    state: string
    zip: string
    country: string
  }
  estimatedDelivery: string | null
  shippedAt: string | null
  deliveredAt: string | null
  events: ShipmentEvent[]
  createdAt: string
  updatedAt: string
}
```

### ShipmentEvent

```ts
{
  status: string
  description: string
  location: string
  timestamp: string
}
```

### Transaction (Ledger)

```ts
{
  id: string
  userId: string
  type: TxnType
  direction: "debit" | "credit"
  amount: number               // centavos
  description: string
  referenceType: string | null  // "order", "installment", etc.
  referenceId: string | null
  createdAt: string
}
```

### PointsTransaction

```ts
{
  id: string
  userId: string
  type: "earned" | "redeemed" | "expired" | "adjusted"
  amount: number               // positivo = ganado, negativo = canjeado
  source: "order_payment" | "signup_bonus" | "tier_bonus" | "redemption" | "refund" | "adjustment"
  referenceId: string | null
  description: string
  createdAt: string
}
```

### Payment

```ts
{
  id: string
  userId: string
  externalReference: string    // referencia que el cliente usa
  amount: number               // centavos
  currency: string             // "MXN"
  method: PaymentMethod
  status: PaymentStatus
  appliedTo: {
    installmentId: string | null
    orderId: string | null
    orderMerchantName: string | null
    installmentNumber: number | null
  }
  validatedAt: string | null
  correctInstallmentId: string | null  // hint interno para payment_wrong_order
  createdAt: string
}
```

### Merchant

```ts
{
  id: string
  name: string
  category: string
  logoUrl: string | null
  status: "active" | "inactive"
  createdAt: string
}
```

---

## Endpoints

> **Los IDs de los ejemplos son ilustrativos.** El seed se regenera en cada arranque del
> server, así que `usr_0001` / `ord_0001` probablemente devuelvan `404` contra tu instancia.
> Los `mch_*` sí son estables (catálogo fijo). Para obtener IDs reales:
>
> ```bash
> # un usuario cualquiera
> curl -s "http://localhost:3001/api/v1/users?limit=1" | jq -r '.data[0].id'
>
> # un usuario con un problema concreto (ver "Catálogo de escenarios")
> curl -s http://localhost:3001/api/v1/scenarios/payment_not_reflected | jq -r '.users[0].id'
>
> # sus órdenes → cuotas
> curl -s "http://localhost:3001/api/v1/users/<userId>/orders" | jq -r '.data[].id'
> curl -s "http://localhost:3001/api/v1/orders/<orderId>/installments" | jq
> ```

### Root

#### `GET /`

Índice de descubrimiento — nombre, versión y mapa de endpoints.

```bash
curl http://localhost:3001/
```

```json
{
  "name": "BNPL Mock Server",
  "version": "0.1.0",
  "endpoints": {
    "health": "/healthz",
    "users": "/api/v1/users",
    "orders": "/api/v1/orders",
    "installments": "/api/v1/installments/:id/pay",
    "shipments": "/api/v1/shipments/:id",
    "merchants": "/api/v1/merchants",
    "transactions": "/api/v1/transactions",
    "membership": "/api/v1/memberships/:id/redeem",
    "scenarios": "/api/v1/scenarios"
  }
}
```

---

### Health

#### `GET /healthz`

```bash
curl http://localhost:3001/healthz
```

```json
{ "status": "ok" }
```

---

#### `GET /readyz`

```bash
curl http://localhost:3001/readyz
```

```json
{ "status": "ok", "seeded": true }
```

---

### Users

#### `GET /api/v1/users`

Lista todos los usuarios con paginación y filtros.

| Query param | Tipo | Descripción |
|-------------|------|-------------|
| `search` | string | Busca por email, firstName, lastName o id |
| `status` | UserStatus | Filtra por status |
| `tier` | Tier | Filtra por tier de membresía |
| `scenario` | `"true"` | Solo usuarios con anomalías |
| `page` | number | Página (default 1) |
| `limit` | number | Items por página (default 20, max 100) |

```bash
curl "http://localhost:3001/api/v1/users?search=john&status=active&limit=5"
```

```json
{
  "data": [
    {
      "id": "usr_0001",
      "email": "john.doe@gmail.com",
      "phone": "+1-555-0123",
      "firstName": "John",
      "lastName": "Doe",
      "dob": "1990-05-15T00:00:00.000Z",
      "status": "active",
      "kycStatus": "verified",
      "avatarUrl": null,
      "scenarioTags": ["double_payment"],
      "createdAt": "2025-06-20T10:00:00.000Z"
    }
  ],
  "page": 1,
  "limit": 5,
  "total": 1,
  "totalPages": 1
}
```

---

#### `GET /api/v1/users/:id`

```bash
curl http://localhost:3001/api/v1/users/usr_0001
```

Devuelve un objeto `User` o `404`.

---

#### `GET /api/v1/users/:id/credit`

```bash
curl http://localhost:3001/api/v1/users/usr_0001/credit
```

```json
{
  "id": "crd_0001",
  "userId": "usr_0001",
  "creditLimit": 150000,
  "outstandingBalance": 45000,
  "availableCredit": 105000,
  "interestRate": 18.5,
  "utilizationPct": 30.0,
  "status": "active",
  "createdAt": "2025-03-01T00:00:00.000Z",
  "updatedAt": "2026-07-17T12:00:00.000Z"
}
```

---

#### `GET /api/v1/users/:id/membership`

```bash
curl http://localhost:3001/api/v1/users/usr_0001/membership
```

```json
{
  "id": "mbr_0001",
  "userId": "usr_0001",
  "pointsBalance": 3200,
  "tier": "silver",
  "tierProgress": {
    "current": 3200,
    "needed": 5000,
    "pct": 55.0
  },
  "totalSpent": 85000,
  "joinedAt": "2025-03-01T00:00:00.000Z",
  "updatedAt": "2026-07-17T12:00:00.000Z"
}
```

---

#### `GET /api/v1/users/:id/orders`

| Query param | Tipo | Descripción |
|-------------|------|-------------|
| `status` | OrderStatus | Filtra por status |
| `page` | number | |
| `limit` | number | |

```bash
curl "http://localhost:3001/api/v1/users/usr_0001/orders?status=active"
```

Devuelve una lista paginada de `Order`.

---

#### `GET /api/v1/users/:id/transactions`

| Query param | Tipo | Descripción |
|-------------|------|-------------|
| `type` | TxnType | Filtra por tipo |
| `page` | number | |
| `limit` | number | |

```bash
curl "http://localhost:3001/api/v1/users/usr_0001/transactions?type=payment&limit=5"
```

---

#### `GET /api/v1/users/:id/points-history`

Lista el historial de puntos del usuario (paginado).

```bash
curl http://localhost:3001/api/v1/users/usr_0001/points-history
```

---

#### `GET /api/v1/users/:id/payment-methods`

```bash
curl http://localhost:3001/api/v1/users/usr_0001/payment-methods
```

```json
{
  "data": [
    {
      "id": "pm_0001",
      "userId": "usr_0001",
      "type": "card",
      "brand": "visa",
      "bankName": null,
      "last4": "4242",
      "expiryMonth": 12,
      "expiryYear": 2028,
      "isDefault": true,
      "createdAt": "2025-03-01T00:00:00.000Z"
    }
  ]
}
```

---

#### `GET /api/v1/users/:id/addresses`

```bash
curl http://localhost:3001/api/v1/users/usr_0001/addresses
```

Devuelve `{ data: Address[] }`.

---

### Orders

#### `GET /api/v1/orders`

| Query param | Tipo | Descripción |
|-------------|------|-------------|
| `userId` | string | Filtra por usuario |
| `status` | OrderStatus | |
| `merchantId` | string | |
| `page` | number | |
| `limit` | number | |

```bash
curl "http://localhost:3001/api/v1/orders?userId=usr_0001&status=active"
```

---

#### `GET /api/v1/orders/:id`

```bash
curl http://localhost:3001/api/v1/orders/ord_0001
```

```json
{
  "id": "ord_0001",
  "userId": "usr_0001",
  "merchantId": "mch_0001",
  "merchantName": "TechHub Store",
  "items": [
    {
      "sku": "WH-PRO-001",
      "name": "Wireless Headphones Pro",
      "qty": 1,
      "unitPrice": 25000
    }
  ],
  "subtotal": 25000,
  "shipping": 0,
  "tax": 4000,
  "totalAmount": 29000,
  "plan": "pay_in_4",
  "status": "active",
  "financing": {
    "principal": 29000,
    "interest": 0,
    "fees": 0,
    "apr": 0,
    "termMonths": 4
  },
  "installmentCount": 4,
  "refundRequested": false,
  "refundReason": null,
  "createdAt": "2026-06-15T10:00:00.000Z",
  "updatedAt": "2026-06-15T10:00:00.000Z"
}
```

---

#### `GET /api/v1/orders/:id/installments`

```bash
curl http://localhost:3001/api/v1/orders/ord_0001/installments
```

```json
{
  "data": [
    {
      "id": "ins_0001",
      "orderId": "ord_0001",
      "userId": "usr_0001",
      "number": 1,
      "amountDue": 7250,
      "principal": 7250,
      "interest": 0,
      "fees": 0,
      "dueDate": "2026-06-29T00:00:00.000Z",
      "paidDate": "2026-06-28T14:30:00.000Z",
      "status": "paid",
      "paymentMethodId": "pm_0001",
      "externalReference": null
    },
    {
      "id": "ins_0002",
      "orderId": "ord_0001",
      "userId": "usr_0001",
      "number": 2,
      "amountDue": 7250,
      "principal": 7250,
      "interest": 0,
      "fees": 0,
      "dueDate": "2026-07-13T00:00:00.000Z",
      "paidDate": null,
      "status": "due",
      "paymentMethodId": null,
      "externalReference": null
    }
  ]
}
```

---

#### `GET /api/v1/orders/:id/shipment`

```bash
curl http://localhost:3001/api/v1/orders/ord_0001/shipment
```

Devuelve un objeto `Shipment` o `404`.

---

### Installments

#### `POST /api/v1/installments/:id/pay`

Marca una cuota como pagada. Ejecuta una cascada completa:

1. Cuota → `status: "paid"`, `paidDate` = ahora
2. Crea una `Transaction` tipo `payment`
3. Otorga puntos (`amountDue / 100` puntos aprox.)
4. Recalcula `CreditAccount` (outstanding baja, available sube)
5. Recalcula `Membership` (puntos + tier + progress)

**Body (opcional):**

```json
{ "paymentMethodId": "pm_0001" }
```

```bash
curl -X POST http://localhost:3001/api/v1/installments/ins_0002/pay \
  -H "Content-Type: application/json" \
  -d '{"paymentMethodId": "pm_0001"}'
```

**Respuesta 200:**

```json
{
  "status": "paid",
  "installment": {
    "id": "ins_0002",
    "status": "paid",
    "paidDate": "2026-07-17T20:30:00.000Z"
  },
  "transaction": {
    "id": "txn_0500",
    "type": "payment",
    "amount": 7250,
    "description": "Payment - Installment 2/4 - TechHub Store"
  },
  "pointsEarned": 72
}
```

**Errores:**

| Status | Error |
|--------|-------|
| 404 | `Installment not found` |
| 409 | `Installment already paid` |

---

### Shipments

#### `GET /api/v1/shipments/:id`

```bash
curl http://localhost:3001/api/v1/shipments/shp_0001
```

---

#### `PATCH /api/v1/shipments/:id`

Avanza el estado del envío. Si no se pasa `status`, avanza al siguiente estado lógico.

**Flujo de estados:**

```
preparing → shipped → in_transit → out_for_delivery → delivered
```

**Body (opcional):**

```json
{ "status": "in_transit" }
```

```bash
# Avanzar al siguiente estado automáticamente
curl -X PATCH http://localhost:3001/api/v1/shipments/shp_0001 \
  -H "Content-Type: application/json" \
  -d '{}'

# Forzar un estado específico
curl -X PATCH http://localhost:3001/api/v1/shipments/shp_0001 \
  -H "Content-Type: application/json" \
  -d '{"status": "delivered"}'
```

**Efectos colaterales:**

- Si pasa a `shipped`: setea `shippedAt`
- Si pasa a `delivered`: setea `deliveredAt`
- Siempre agrega un `ShipmentEvent` al array de eventos

---

### Payments

#### `GET /api/v1/payments`

| Query param | Tipo | Descripción |
|-------------|------|-------------|
| `userId` | string | |
| `status` | PaymentStatus | `pending_validation`, `validated`, `reassigned` |
| `page` | number | |
| `limit` | number | |

```bash
curl "http://localhost:3001/api/v1/payments?status=pending_validation&limit=5"
```

---

#### `GET /api/v1/payments/:id`

```bash
curl http://localhost:3001/api/v1/payments/pmt_0001
```

---

#### `POST /api/v1/payments/validate`

Valida un pago por su referencia externa.

**El desenlace lo decide el prefijo de `externalReference`, no el estado de la DB.**
Es determinista (mismo input → misma respuesta, siempre) y **no muta nada**: no marca
cuotas pagadas, no suma puntos, no recalcula crédito. Así los evals pueden afirmar un
resultado exacto y no hay nada que resetear entre corridas.

| Prefijo | Resultado | HTTP |
|---------|-----------|------|
| `REF_OK…` | `PAYMENT_CREATED_AND_VALIDATED` | 200 |
| `REF_DUP…` | `PAYMENT_ALREADY_VALIDATED` (sin warning) | 200 |
| `REF_WRONG…` | `PAYMENT_ALREADY_VALIDATED` + `warning` | 200 |
| cualquier otro | `PAYMENT_NOT_FOUND` | 404 |

Para probar una rama concreta, cambiá la referencia. El seed emite referencias con estos
prefijos (`REF_OK…` en los pagos pendientes y en `payment_not_reflected`, `REF_WRONG…` en
`payment_wrong_order`), así que una referencia descubierta navegando la data cae en el
desenlace que le corresponde.

Los datos de cuota y orden del payload **sí** se leen de la DB (solo lectura), así que son
coherentes con lo que devuelve `GET /orders/:id/installments`. La cuota destino es la
primera impaga del cliente.

**Body requerido:**

```json
{
  "externalReference": "REF_OK24HCA2WO",
  "userId": "usr_00ga"
}
```

```bash
# rama feliz
curl -X POST http://localhost:3001/api/v1/payments/validate \
  -H "Content-Type: application/json" \
  -d '{"externalReference":"REF_OK24HCA2WO","userId":"usr_00ga"}'

# ya validado, sin problema
curl -X POST http://localhost:3001/api/v1/payments/validate \
  -H "Content-Type: application/json" \
  -d '{"externalReference":"REF_DUPZZZ1","userId":"usr_00ga"}'

# aplicado a la orden equivocada → habilita reassign
curl -X POST http://localhost:3001/api/v1/payments/validate \
  -H "Content-Type: application/json" \
  -d '{"externalReference":"REF_WRONGZZ1","userId":"usr_00ga"}'

# comprobante falso / referencia mal tipeada
curl -X POST http://localhost:3001/api/v1/payments/validate \
  -H "Content-Type: application/json" \
  -d '{"externalReference":"REFBASURA123","userId":"usr_00ga"}'
```

Falta `externalReference` o `userId` → `400 {"error":"externalReference and userId are required"}`.

---

**Resultado 1 — `PAYMENT_CREATED_AND_VALIDATED` (200)** — prefijo `REF_OK…`

El pago se concilió y se aplicó a la primera cuota impaga del cliente.

```json
{
  "result": "PAYMENT_CREATED_AND_VALIDATED",
  "payment": {
    "id": "pmt_mock_refok24hca2wo",
    "userId": "usr_00ga",
    "externalReference": "REF_OK24HCA2WO",
    "amount": 11658,
    "currency": "MXN",
    "method": "spei",
    "status": "validated",
    "appliedTo": {
      "installmentId": "ins_00gj",
      "orderId": "ord_00gh",
      "orderMerchantName": "GreenGarden",
      "installmentNumber": 2
    },
    "validatedAt": "2026-07-28T05:20:49.133Z",
    "correctInstallmentId": null
  },
  "installment": { "id": "ins_00gj", "number": 2, "status": "paid" },
  "pointsEarned": 116
}
```

> `installment.status` describe el desenlace, pero el endpoint no muta la DB:
> `GET /orders/ord_00gh/installments` va a seguir mostrando `ins_00gj` impaga.

---

**Resultado 2 — `PAYMENT_ALREADY_VALIDATED` (200)** — prefijo `REF_DUP…`

El pago ya se había validado, y sobre la cuota correcta. Sin `warning`.

```json
{
  "result": "PAYMENT_ALREADY_VALIDATED",
  "payment": {
    "id": "pmt_mock_refdupzzz1",
    "status": "validated",
    "appliedTo": {
      "installmentId": "ins_00gj",
      "orderId": "ord_00gh",
      "orderMerchantName": "GreenGarden",
      "installmentNumber": 2
    },
    "validatedAt": "2026-07-26T05:20:49.272Z",
    "correctInstallmentId": null
  },
  "message": "Payment pmt_mock_refdupzzz1 was already validated on 2026-07-26T05:20:49.272Z"
}
```

---

**Resultado 3 — `PAYMENT_ALREADY_VALIDATED` + `warning` (200)** — prefijo `REF_WRONG…`

Se validó, pero se aplicó a una cuota de **otra** orden. `correctInstallmentId` trae la
cuota que el cliente quería pagar — es el input de `POST /payments/:id/reassign`.

```json
{
  "result": "PAYMENT_ALREADY_VALIDATED",
  "payment": {
    "id": "pmt_mock_refwrongzz1",
    "status": "validated",
    "appliedTo": {
      "installmentId": "ins_00gr",
      "orderId": "ord_00gq",
      "orderMerchantName": "SportLife",
      "installmentNumber": 1
    },
    "validatedAt": "2026-07-26T05:20:49.340Z",
    "correctInstallmentId": "ins_00gj",
    "warning": "Payment was applied to a different installment than expected"
  },
  "message": "Payment pmt_mock_refwrongzz1 was already validated, but it was applied to installment 1 of order 'SportLife' — which may not be the order the customer intended to pay."
}
```

---

**Resultado 4 — `PAYMENT_NOT_FOUND` (404)** — cualquier otro prefijo

No hay pago con esa referencia. **Es un desenlace de negocio, no un fallo técnico:**
cubre el comprobante falso y la referencia mal tipeada. También se devuelve si el usuario
no tiene ninguna cuota a la que aplicar el pago.

```json
{
  "result": "PAYMENT_NOT_FOUND",
  "message": "No payment found with reference 'REFBASURA123' for this user"
}
```

---

#### `POST /api/v1/payments/:id/reassign`

Reasigna un pago ya validado a otra cuota. Deshace el pago en la cuota equivocada y lo aplica a la correcta.

Tiene **dos caminos**, según de dónde venga el `:id`:

| `:id` | Comportamiento |
|-------|----------------|
| `pmt_mock_…` | Pago sintético que devolvió `validate`. Respuesta canned, **no muta la DB**. Requiere `installmentId` en el body. |
| `pmt_…` (del seed) | Pago real. **Muta la DB** con la cascada completa descrita abajo. |

El primer camino existe para que el flujo multiturno `validate` → `reassign` sea coherente:
`validate` no persiste nada, así que el pago que devuelve no está en la DB y sin esto el
segundo turno respondería 404.

**Body (obligatorio para `pmt_mock_…`; opcional en un pago real que ya tenga `correctInstallmentId`):**

```json
{ "installmentId": "ins_00gj" }
```

```bash
# camino canned — segundo turno de un validate con REF_WRONG…
curl -X POST http://localhost:3001/api/v1/payments/pmt_mock_refwrongzz1/reassign \
  -H "Content-Type: application/json" \
  -d '{"installmentId":"ins_00gj"}'

# camino real — pago del seed, usa su correctInstallmentId
curl -X POST http://localhost:3001/api/v1/payments/pmt_01ov/reassign \
  -H "Content-Type: application/json" \
  -d '{}'
```

**Respuesta 200:**

```json
{
  "result": "PAYMENT_REASSIGNED",
  "payment": {
    "id": "pmt_0005",
    "status": "reassigned",
    "appliedTo": {
      "installmentId": "ins_00fj",
      "orderId": "ord_00g5",
      "orderMerchantName": "GadgetZone",
      "installmentNumber": 2
    },
    "correctInstallmentId": null
  },
  "installment": {
    "id": "ins_00fj",
    "number": 2,
    "status": "paid"
  },
  "previousInstallmentId": "ins_00fb",
  "pointsEarned": 150
}
```

**Efectos de la reasignación:**

1. La cuota previa (`ins_00fb`) vuelve a `due` o `overdue` según su `dueDate`
2. Se elimina la transacción de pago de la cuota previa
3. La cuota destino (`ins_00fj`) se marca `paid`
4. Se crea nueva transacción de pago para la cuota destino
5. Se otorgan puntos por la cuota destino
6. Se recalcula `CreditAccount` y `Membership`

**Errores:**

| Status | Error |
|--------|-------|
| 404 | `Payment not found` |
| 409 | `Payment must be validated before reassignment` |
| 400 | `installmentId is required` |
| 409 | `Installment does not belong to the same user` |

---

### Membership

#### `POST /api/v1/memberships/:id/redeem`

Canjea puntos contra el saldo de la cuenta de crédito. 1 punto = $0.01 (1 centavo).

**Body requerido:**

```json
{ "amount": 500 }
```

```bash
curl -X POST http://localhost:3001/api/v1/memberships/mbr_0001/redeem \
  -H "Content-Type: application/json" \
  -d '{"amount": 500}'
```

**Respuesta 200:**

```json
{
  "status": "redeemed",
  "membership": {
    "id": "mbr_0001",
    "pointsBalance": 2700,
    "tierProgress": { "current": 2700, "needed": 5000, "pct": 42.5 }
  },
  "pointsRedeemed": 500
}
```

**Efectos:**

1. Resta `amount` puntos del `pointsBalance`
2. Recalcula `tierProgress`
3. Crea `PointsTransaction` tipo `redeemed` (amount negativo)
4. Reduce `outstandingBalance` del `CreditAccount` en `amount * 100` centavos

**Errores:**

| Status | Error |
|--------|-------|
| 400 | `amount must be a positive number` |
| 409 | `Insufficient points balance` |

---

### Transactions

#### `GET /api/v1/transactions`

Lista global de transacciones.

| Query param | Tipo | Descripción |
|-------------|------|-------------|
| `userId` | string | Filtra por usuario |
| `type` | TxnType | Filtra por tipo |
| `page` | number | |
| `limit` | number | |

```bash
curl "http://localhost:3001/api/v1/transactions?userId=usr_0001&type=payment"
```

---

### Merchants

#### `GET /api/v1/merchants`

| Query param | Tipo | Descripción |
|-------------|------|-------------|
| `category` | string | `electronics`, `fashion`, `home`, `sports`, `beauty`, `toys`, `automotive`, `books`, `garden` |
| `page` | number | |
| `limit` | number | |

```bash
curl "http://localhost:3001/api/v1/merchants?category=fashion&limit=2"
```

```json
{
  "data": [
    {
      "id": "mch_0002",
      "name": "Moda Urbana",
      "category": "fashion",
      "logoUrl": null,
      "status": "active",
      "createdAt": "2024-08-15T01:58:27.188Z"
    }
  ],
  "page": 1,
  "limit": 2,
  "total": 1,
  "totalPages": 1
}
```

---

#### `GET /api/v1/merchants/:id`

```bash
curl http://localhost:3001/api/v1/merchants/mch_0002
```

Devuelve un objeto `Merchant` o `404`.

---

### Scenarios

Los escenarios son etiquetas que se asignan a usuarios específicos del seed para crear problemas realistas que un agente de IA debe resolver. Un agente en producción **no** usaría estos endpoints — descubriría los problemas navegando la data.

#### `GET /api/v1/scenarios`

Devuelve el catálogo completo de escenarios con los usuarios asignados a cada uno.

```bash
curl http://localhost:3001/api/v1/scenarios
```

```json
{
  "data": [
    {
      "tag": "double_payment",
      "description": "User paid the same installment twice — duplicate payment not refunded",
      "userCount": 2,
      "users": [
        {
          "id": "usr_00o2",
          "name": "Gustavo Leannon",
          "email": "gustavo.leannon67@yahoo.com",
          "allTags": ["double_payment"]
        }
      ]
    }
  ]
}
```

---

#### `GET /api/v1/scenarios/:tag`

Lista los usuarios asignados a un escenario específico.

```bash
curl http://localhost:3001/api/v1/scenarios/missing_points
```

```json
{
  "tag": "missing_points",
  "description": "Order is completed with all installments paid, but no points were ever awarded",
  "userCount": 2,
  "users": [
    {
      "id": "usr_00d7",
      "name": "Fabian O'Connell",
      "email": "fabian.oconnell7@hotmail.com",
      "allTags": ["missing_points"]
    }
  ]
}
```

---

## Catálogo de escenarios

| Tag | Descripción | Cómo detectarlo |
|-----|-------------|-----------------|
| `double_payment` | Pagó la misma cuota dos veces | Dos `Transaction` tipo `payment` con el mismo `referenceId` (installmentId) |
| `refund_pending` | Solicitó reembolso, no se ha procesado | `Order.refundRequested = true`, `Order.refundReason` seteado, sin `Transaction` tipo `refund` |
| `shipment_stuck` | Envío en tránsito 15+ días sin updates | `Shipment.status = "in_transit"`, sin eventos recientes, `estimatedDelivery` ya pasó |
| `shipment_lost` | Enviado pero sin tracking después del scan inicial | `Shipment.status = "shipped"`, solo 1–2 eventos, sin eventos de tránsito |
| `shipment_never_shipped` | Orden activa pero envío estancado en preparación | `Shipment.status = "preparing"` hace 10+ días, orden `active` |
| `payment_not_reflected` | Pago con referencia bancaria pero cuota sin marcar como pagada | `Installment.externalReference` seteado, `Installment.status != "paid"`, existe `Transaction` tipo `payment` unreconciled |
| `missing_points` | Orden completada pero cero puntos acreditados | `Order.status = "completed"`, sin `PointsTransaction` con `source = "order_payment"` para sus cuotas |
| `partial_points` | Puntos acreditados a una tasa menor | `PointsTransaction` con amount mucho menor al esperado (`amountDue / 100`) |
| `stale_tier` | Puntos califican para mayor nivel pero no se actualizó | `Membership.pointsBalance` > umbral del siguiente tier, pero `Membership.tier` no refleja el ascenso |
| `overdue_unnotified` | Cuota vencida sin notificación | `Installment.status = "overdue"`, `dueDate` ya pasada, usuario parece no saberlo |
| `failed_payment` | Pago falló pero el cobro sí se hizo | `Installment.status = "failed"` pero existe `Transaction` tipo `payment` con `referenceId` de esa cuota |
| `overcharged` | Cobro mayor al monto de la cuota | `Transaction.amount > Installment.amountDue` para la cuota referenciada |
| `phantom_order` | Orden que el usuario no reconoce | `Order.merchantName = "Unknown Merchant"`, datos anómalos, merchantId desconocido |
| `cancelled_but_charged` | Orden cancelada pero con cuotas posteriores cobradas | `Order.status = "cancelled"` pero existen cuotas con `status = "paid"` posteriores a la cancelación |
| `payment_wrong_order` | Pago validado pero aplicado a la orden equivocada | `Payment.appliedTo.installmentId != Payment.correctInstallmentId`. Al validar, devuelve `warning` |

---

## Flujos de uso recomendados

### "Validé mi pago y no se refleja"

```
1. GET  /api/v1/scenarios/payment_not_reflected     → encontrar userId
2. GET  /api/v1/users/:userId/orders?status=active   → identificar orden
3. GET  /api/v1/orders/:orderId/installments         → ver cuota con externalReference (REF_OK…) pero status != paid
4. POST /api/v1/payments/validate                    → PAYMENT_CREATED_AND_VALIDATED
```

### "Pagué pero se aplicó a la orden equivocada"

```
1. POST /api/v1/payments/validate      (ref REF_WRONG…)  → ALREADY_VALIDATED + warning + correctInstallmentId
2. GET  /api/v1/orders/:orderId/installments             → contrastar la cuota a la que fue vs. la que el cliente quería
3. POST /api/v1/payments/:paymentId/reassign             → PAYMENT_REASSIGNED
```

> No uses un segundo `validate` como confirmación: el endpoint es stateless y una
> referencia `REF_WRONG…` va a seguir devolviendo el warning después de reasignar.
> Tampoco sirve `GET /payments/:id` con un `pmt_mock_…` — ese pago no existe en la DB;
> el `correctInstallmentId` te lo dio ya la respuesta del paso 1.

### "No me asignaron los puntos de mi compra"

```
1. GET  /api/v1/scenarios/missing_points             → encontrar userId
2. GET  /api/v1/users/:userId/orders?status=completed → ver orden completada
3. GET  /api/v1/users/:userId/points-history          → confirmar: sin entradas para esa orden
```

### "No sé dónde está mi envío"

```
1. GET  /api/v1/scenarios/shipment_stuck             → encontrar userId
2. GET  /api/v1/users/:userId/orders?status=active    → identificar orden
3. GET  /api/v1/orders/:orderId/shipment              → ver eventos de tracking
4. PATCH /api/v1/shipments/:shipmentId                → avanzar estado si es necesario
```

---

## Seed data

El seed genera datos deterministas (seed fija = 42) al arrancar el servidor.

| Entidad | Cantidad aprox. |
|---------|----------------|
| Users | 50 |
| Addresses | ~67 |
| Payment methods | ~111 |
| Credit accounts | 50 (1 por usuario) |
| Memberships | 50 (1 por usuario) |
| Merchants | 10 |
| Orders | ~110–130 |
| Installments | ~550+ |
| Shipments | ~110–130 |
| Transactions | ~500+ |
| Points transactions | ~380+ |
| Payments | ~30 (pending_validation + validated) |
| Users con anomalías | ~25 |

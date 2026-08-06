# Merchant Mock Server — Plan de Implementación

> Servidor mock orientado al **aliado/comercio** (merchant). Domina: órdenes vendidas,
> conciliación diaria, reportes mensuales, transferencias (payouts), facturas, inventario,
> promociones, cajas/POS, empleados y onboarding. Puerto **3002**.

## Estado general

| Fase | Descripción | Estado |
|------|-------------|--------|
| A | Scaffold (server, db, utils, schema/common, health) | ✅ Completado |
| B | Schemas completos + seed base coherente | ✅ Completado |
| C | Routers de lectura | ✅ Completado |
| D | Mutaciones + reglas de rol | ✅ Completado |
| E | Catálogo de escenarios (22 tags) | ✅ Completado |
| F | Docs (API.md, README), dump-seed, wiring, curls | ✅ Completado |
| G | Frontend — selector de merchant + navegador | ✅ Completado |

---

## Fase A — Scaffold

**Objetivo:** servidor arrancando en 3002 con health check y estructura base.

### Archivos
- `package.json` — deps: hono, @hono/node-server, @faker-js/faker, zod, @hono/zod-validator
- `tsconfig.json` — idéntico al mock BNPL (strict, verbatimModuleSyntax, allowImportingTsExtensions)
- `Dockerfile` — oven/bun:1, puerto 3002
- `.dockerignore` — node_modules, data/, .git
- `.gitignore` — node_modules, data/, .venv
- `src/server.ts` — Hono app, CORS, mount routes, serve(3002), startup log
- `src/db.ts` — Database interface (Map collections), singleton getDB/setDB/resetDB, query helpers
- `src/utils/delay.ts` — simulatedDelay() 40-200ms, delay(ms)
- `src/utils/response.ts` — paginate, defaultPage, defaultLimit
- `src/utils/id.ts` — id(prefix), resetIdCounter
- `src/utils/rif.ts` — normalizeRif(rif), rifMatches(query, rif)
- `src/schema/common.ts` — Money, IsoDate, PaginatedMeta, todos los enums del dominio
- `src/schema/index.ts` — barrel export

### Criterio de check
- `bun run dev` arranca en 3002
- `GET /healthz` → `{ status: "ok" }`
- `GET /` → discovery index

---

## Fase B — Schemas + Seed

**Objetivo:** dataset determinista con datos coherentes.

### Schemas (zod)
1. `merchant.ts` — Merchant con rif, legalName, tradeName, model (BASE|EXPRESS), fcbPeriod, etc.
2. `store.ts` — Store con channels, statusId, minimumDownPayment, address, inventoryMigrated
3. `employee.ts` — Employee con role (ADMIN|MANAGER|CASHIER), onboardingStatus, 2FA flags
4. `order.ts` — Order (vista aliado), OrderProduct, OrderBuyer, OrderInstallment, OrderInstallmentPayment, OrderInvoice, Pos, DiscountBreakdown
5. `daily-conciliation.ts` — DailyConciliation, POSConciliation
6. `monthly-report.ts` — MonthlyReport, ServiceFeeDetail, MissedInstallmentsDetail, ErrorsAndAdjustmentsDetail
7. `payout.ts` — Payout (nuevo: grossAmount, serviceFee, retentions, adjustments, netAmount, status)
8. `invoice.ts` — Invoice (period, number, amount, iva, isrlRetained, status, sentToEmail, pdfUrl)
9. `report.ts` — Report (reports-hub), Movement
10. `promotion.ts` — Promotion, PromotionMechanic, ConditionGroup, links
11. `pos.ts` — POS (posUuid, name, qrLinked, qrCode), QrSummary
12. `payment-method.ts` — PaymentMethod (PAGO_MOVIL, TRANSFERENCIA, EFECTIVO, TARJETA)
13. `product.ts` — Product (sku, name, price, stock, category, status), InventoryJob
14. `onboarding.ts` — Onboarding (step, status, failedRules, legalDocuments, bankAccountVerified)

### Seed
- `faker.ts` — faker con seed 42 fija, override por SEED env
- `catalogs.ts` — ~40 nombres de comercio VE, bancos, categorías, productos VE
- `generators.ts` — helpers: vePhone, veCedula, veBankReference, rifGenerator, money, time helpers
- `seed.ts` — orchestrator:
  - 5 merchants (mezcla BASE/EXPRESS, distintos fcbPeriod)
  - 1-3 stores por merchant (~10 total)
  - 2-4 empleados por store (mezcla ADMIN/MANAGER/CASHIER)
  - ~100 órdenes distribuidas en 3 meses con cuotas/pagos coherentes
  - Conciliaciones diarias derivadas de las órdenes
  - 3 periodos de monthly-report + payout + invoice coherentes entre sí
  - ~8 promociones
  - Productos por store (5-15 cada uno)
  - POS por store (1-2 cada uno)
  - ~2 onboardings en distintos estados

### Coherencia (inviolable salvo escenarios)
- `dailyConciliation.ordersCount` = órdenes de ese día
- `dailyConciliation.totalChargedAmount` = suma de downPayments de ese día
- `dailyConciliation.totalFinancedAmount` = suma de financedAmount de ese día
- `payout.netAmount` = `grossAmount - serviceFee - retentions + adjustments`
- `monthlyReport.compensation.totalAmount` = compensación del periodo
- `invoice.amount` = serviceFee del periodo

### Criterio de check
- Dos arranques con misma SEED → mismas entidades y escenarios; fechas relativas cambian
- Log de startup muestra: merchants, stores, employees, orders, conciliaciones, reportes

---

## Fase C — Routers de Lectura

**Objetivo:** todos los endpoints GET funcionando.

### Merchants
- `GET /api/v1/merchants` — lista paginada con filtros ?search=&rif=&model=&status=
- `GET /api/v1/merchants/by-rif/:rif` — lookup normalizando RIF
- `GET /api/v1/merchants/:id` — detalle (acepta id numérico o uuid)
- `GET /api/v1/merchants/:id/stores` — tiendas del merchant
- `GET /api/v1/merchants/:id/employees` — empleados del merchant
- `GET /api/v1/merchants/:id/payouts` — payouts por periodo ?from=&to=
- `GET /api/v1/merchants/:id/payouts/:payoutId` — detalle de payout
- `GET /api/v1/merchants/:id/invoices` — facturas ?from=&to=&status=
- `GET /api/v1/merchants/:id/monthly-reports` — periodos disponibles + reporte actual
- `GET /api/v1/merchants/:id/monthly-reports/:period` — reporte de un periodo (YYYY-MM)
- `GET /api/v1/merchants/:id/monthly-reports/:period/service-fee` — detalle servicio
- `GET /api/v1/merchants/:id/monthly-reports/:period/missed-installments` — detalle cuotas
- `GET /api/v1/merchants/:id/monthly-reports/:period/errors-and-adjustments` — detalle errores
- `GET /api/v1/merchants/:id/promotions` — promociones disponibles

### Stores
- `GET /api/v1/stores/:uuid` — detalle
- `GET /api/v1/stores/:uuid/daily-conciliation` — conciliación del día ?date=
- `GET /api/v1/stores/:uuid/daily-conciliation/last` — última conciliación
- `GET /api/v1/stores/:uuid/daily-conciliation/history` — historial
- `GET /api/v1/stores/:uuid/payment-methods` — métodos de pago ?category=
- `GET /api/v1/stores/:uuid/pos` — cajas/POS de la tienda
- `GET /api/v1/stores/:uuid/pos/qr-summary` — resumen de QR
- `GET /api/v1/stores/:uuid/products` — productos ?search=&sku=&page=&limit=

### POS
- `GET /api/v1/pos/:uuid` — detalle de POS

### Orders
- `GET /api/v1/orders` — lista con filtros ?storeUuid=&merchantId=&status=&channel=&from=&to=
- `GET /api/v1/orders/:orderNumber` — detalle completo
- `GET /api/v1/orders/:orderNumber/installments` — cuotas de la orden
- `GET /api/v1/orders/:orderNumber/payments` — pagos de la orden
- `GET /api/v1/orders/cancellation-reasons` — motivos de cancelación ?role=

### Employees
- `GET /api/v1/employees/:id` — detalle de empleado

### Onboarding
- `GET /api/v1/onboarding/:onboardingId` — estado de afiliación

### Reports & Movements
- `GET /api/v1/reports` — reports-hub
- `GET /api/v1/movements` — movimientos

### Scenarios
- `GET /api/v1/scenarios` — catálogo con IDs afectados
- `GET /api/v1/scenarios/:tag` — detalle de un escenario

### Criterio de check
- Todos los GET retornan datos coherentes
- Filtros funcionan correctamente
- Paginación correcta
- 404 para recursos inexistentes

---

## Fase D — Mutaciones + Reglas de Rol

**Objetivo:** POST endpoints con validación de negocio.

### Cancelación de órdenes (`POST /api/v1/orders/:orderNumber/cancel`)
Body: `{ employeeId, reasonId, securityCode? }`

Reglas:
| Rol | Restricción de fecha | Código seguridad | Error |
|-----|---------------------|------------------|-------|
| ADMIN | Sin restricción | No requerido | — |
| MANAGER | Solo mismo día | Requerido (6 dígitos) | 403 `security_code_required` / 409 `invalid_security_code` / 409 `out_of_day_window` |
| CASHIER | No puede cancelar | — | 403 `role_not_allowed_to_cancel` |

Estados cancelables: `IN_PROGRESS`, `PENDING`, `OPEN`
Si ya `CANCELLED` → 409 `order_already_cancelled`
Si `CLOSED` → 409 `order_not_cancellable`

### Registro de factura (`POST /api/v1/orders/:orderNumber/invoice`)
Body: `{ employeeId, invoiceNumber }`
- Si store tiene flag `invoiceRegistrationFailing` → 503 `invoice_registration_error`
- Si ya registrada → 409 `invoice_already_registered`

### 2FA — Registro de teléfono (`POST /api/v1/employees/:id/2fa/register-phone`)
Body: `{ phone }`
- Si phone ya es el actual → 200 con `{ alreadyRegistered: true }`
- Si no → actualiza `phoneRegistered = true`, `phone` = phone

### 2FA — Enviar código (`POST /api/v1/employees/:id/2fa/send-code`)
- Si flag `otpNeverArrives` → 200 pero el verify-code posterior siempre falla
- Normal → 200 `{ sent: true }`

### 2FA — Verificar código (`POST /api/v1/employees/:id/2fa/verify-code`)
Body: `{ code }`
- Si flag `otpNeverArrives` → 409 `code_expired`
- Si `code === "123456"` (demo) → 200 `{ verified: true }`
- Si incorrecto → 409 `invalid_code`

### Promociones
- `POST /api/v1/merchants/:id/promotions/:promotionId/join` → cambia enrollmentStatus a JOINED
- `POST /api/v1/merchants/:id/promotions/:promotionId/leave` → cambia a AVAILABLE

### POS link-qr (`POST /api/v1/pos/:uuid/link-qr`)
Body: `{ activationCode }`
- Vincula QR al POS, actualiza `qrLinked = true`

### Criterio de check
- Cada error es distinguible por mensaje y status code
- ADMIN puede cancelar orden de ayer, MANAGER no, CASHIER no
- Flujo 2FA completo funcional

---

## Fase E — Catálogo de Escenarios (22 tags)

Cada escenario: `{ tag, description, apply(db) }` que etiqueta merchant/store/order/employee con `scenarioTag`.

| # | Tag | Qué simula | Endpoint que lo revela |
|---|-----|-----------|----------------------|
| 1 | `2fa_phone_not_registered` | Empleado admin con phoneRegistered=false | `GET /employees/:id` |
| 2 | `2fa_phone_already_registered` | El teléfono a registrar ya es el suyo | `POST /employees/:id/2fa/register-phone` |
| 3 | `2fa_otp_never_arrives` | send-code 200 pero verify-code siempre 409 | `POST /employees/:id/2fa/verify-code` |
| 4 | `credentials_invite_not_delivered` | Empleado IN_PROGRESS, lastLoginAt=null | `GET /employees/:id` |
| 5 | `password_change_required` | mustChangePassword=true | `GET /employees/:id` |
| 6 | `security_code_not_set` | Gerente con securityCodeSet=false | `GET /employees/:id` + `POST /orders/:n/cancel` |
| 7 | `cashier_cannot_cancel` | Orden cancelable, empleado CASHIER | `POST /orders/:n/cancel` |
| 8 | `cancel_out_of_day_window` | Gerente + orden de ayer | `POST /orders/:n/cancel` |
| 9 | `order_create_connection_error` | Store con flag de error de conexión | `POST` creación (simulado) |
| 10 | `invoice_registration_failing` | Orden CLOSED con invoice.registered=false | `POST /orders/:n/invoice` |
| 11 | `order_incident_lost_shipment` | Orden con shipmentStatus=LOST_OR_STOLEN | `GET /orders/:n` |
| 12 | `down_payment_not_reflected` | Orden LINK con pago PENDING no conciliado | `GET /orders/:n/installments` |
| 13 | `payout_missing_for_period` | Periodo cerrado, payout.status=PENDING | `GET /merchants/:id/payouts` |
| 14 | `payout_amount_mismatch` | payout.netAmount ≠ compensación | `GET /merchants/:id/payouts` + monthly-reports |
| 15 | `invoices_not_sent_multi_month` | 5 meses con invoice.status=NOT_SENT | `GET /merchants/:id/invoices` |
| 16 | `isrl_retention_disputed` | serviceFee.isrlRetainedAmount alto | `GET /monthly-reports/:period/service-fee` |
| 17 | `daily_conciliation_mismatch` | ordersCount no cuadra | `GET /stores/:uuid/daily-conciliation` |
| 18 | `pos_qr_not_linked` | POS sin QR vinculado | `GET /stores/:uuid/pos` |
| 19 | `promotion_not_eligible` | Promo ACTIVE pero enrollmentStatus=NONE | `GET /merchants/:id/promotions` |
| 20 | `model_migration_pending` | Merchant BASE con solicitud a EXPRESS | `GET /merchants/:id` |
| 21 | `onboarding_stuck_documents` | Onboarding con documentos PENDING | `GET /onboarding/:id` |
| 22 | `inventory_bulk_job_failed` | Job de carga masiva FAILED | `GET /stores/:uuid/products` |

### Criterio de check
- `GET /api/v1/scenarios` lista los 22 tags con IDs reales
- Cada tag tiene al menos una entidad sembrada y observable

---

## Fase F — Documentación + Wiring

### API.md
Estructura:
1. Header + base URL + convenciones
2. Convenciones de dinero (centavos + currency, amountVES dual)
3. Enums del dominio (tabla completa)
4. Data models (TypeScript con comentarios)
5. Endpoints (agrupados, con curl examples y response examples)
6. Catálogo de escenarios (tabla con tag, qué simula, endpoint, qué responde el agente)
7. Flujos de uso recomendados

### README.md
- Setup rápido
- Tabla de endpoints
- Tabla de escenarios
- Convenciones

### dump-seed.ts
- `bun run seed:dump` → `data/seed.json` con stats + data completa

### Wiring
- `docker-compose.yml`: servicio `merchant-mock-server`, puerto 3002, mismo patrón que mock-server
- `agent-service/src/service/core/config.py`: añadir `merchant_api_url`
- `README.md` raíz: añadir fila en tabla de servicios

### ~10 curls de ejemplo
1. Buscar merchant por RIF
2. Buscar merchant por nombre
3. Ver payouts de un merchant
4. Ver payout faltante (escenario)
5. Ver conciliación diaria
6. Cancelar orden como ADMIN
7. Cancelar orden como MANAGER (window)
8. Cancelar orden como CASHIER (403)
9. Registrar factura (503)
10. Verificar 2FA (OTP nunca llega)

### Criterio de check
- API.md documenta TODO: endpoints, enums, escenarios
- docker compose up levanta ambos mocks
- seed:dump genera JSON
- config.py tiene merchant_api_url

---

## Fase G — Frontend

**Objetivo:** UI simple para navegar el mock como si fueras un merchant.

### Stack
- Next.js + React (mismo que `frontend/`) o HTML estático servido por Hono
- Si HTML estático: un solo `index.html` con Tailwind CDN + vanilla JS o React via CDN
- Decisión: **HTML estático servido por Hono** — más simple, sin build, mismo patrón que un dashboard de mock

### Pantallas
1. **Selector de merchant** — lista de merchants (buscador por RIF/nombre) + "Entrar"
2. **Dashboard** — resumen: modelo, stores, empleados, órdenes recientes, payout pendiente
3. **Órdenes** — tabla paginada con filtros + detalle expandible
4. **Conciliación diaria** — tabla con POS breakdown
5. **Reporte mensual** — timeline + compensación + service fee
6. **Payouts** — lista con status (PENDING/SENT/FAILED)
7. **Facturas** — lista con status (ISSUED/SENT/NOT_SENT)
8. **Empleados** — lista con rol + estado 2FA
9. **Escenarios** — catálogo con links navegables a entidades afectadas

### Navegación
- Sidebar con secciones
- Selector de merchant persistente en la barra superior
- Links directos a la API para debugging

### Criterio de check
- `GET /` sirve el frontend
- Se puede buscar y seleccionar un merchant
- Se pueden ver sus órdenes, conciliación, payouts, facturas
- Se pueden ver los escenarios sembrados

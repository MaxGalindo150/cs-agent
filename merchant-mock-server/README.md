# Merchant Mock Server

Servidor mock que simula el backend del **aliado/merchant** de Cashea: el comercio
afiliado que vende con Cashea. No es el comprador — el aliado consulta sus órdenes
vendidas, su conciliación diaria, su reporte mensual, cuánto le va a transferir
Cashea, sus facturas y retenciones, su inventario, sus promociones, sus cajas/POS
y sus empleados.

Diseñado como sistema externo para que el agente de atención al aliado lo consuma
via tools y pueda **resolver** casos reales con datos en vez de escalar todo.

## Stack

Hono + Bun + zod + faker. DB in-memory con `Map` singleton, seed determinista al
arrancar, latencia simulada. Mismas convenciones que `mock-server/`.

## Setup

```bash
cd merchant-mock-server
bun install
bun run dev          # localhost:3002 con hot-reload
```

Para volcar el dataset a JSON:

```bash
bun run seed:dump    # genera data/seed.json
```

## Seed data

- 5 merchants (mezcla BASE/EXPRESS, distintos `fcbPeriod`)
- 10 stores (1–4 por merchant)
- 36 employees (2–5 por store, los tres roles: ADMIN, MANAGER, CASHIER)
- 100 órdenes distribuidas en 3 meses con cuotas y pagos coherentes
- 597 cuotas (installments) con sus pagos
- 33 conciliaciones diarias (derivadas de las órdenes)
- 12 reportes mensuales + 8 payouts + 14 facturas
- 4 promociones, 13 POS, 34 métodos de pago, 89 productos
- 3 onboardings
- **22 escenarios** aplicados sobre entidades reales (ver catálogo abajo)

### Determinismo

La seed usa faker con una semilla fija. Variable de entorno `SEED` para override.
Entidades y escenarios se repiten; fechas relativas y `generatedAt` se calculan
desde la hora de arranque, por lo que dos volcados no son byte a byte idénticos.

## Endpoints

Ver [`API.md`](./API.md) para la referencia completa con ejemplos.

### Health
| Method | Path | Descripción |
|---|---|---|
| GET | `/healthz` | Status check |
| GET | `/readyz` | Status + seeded check |

### Merchants
| Method | Path | Query params |
|---|---|---|
| GET | `/api/v1/merchants` | `search, rif, model, status, scenario, page, limit` |
| GET | `/api/v1/merchants/by-rif/:rif` | (normaliza RIF: quita guiones/espacios, uppercase) |
| GET | `/api/v1/merchants/:id` | (id numérico o UUID) |
| GET | `/api/v1/merchants/:id/stores` | |
| GET | `/api/v1/merchants/:id/employees` | `role` |
| GET | `/api/v1/merchants/:id/payouts` | `from, to, status` |
| GET | `/api/v1/merchants/:id/payouts/:payoutId` | |
| GET | `/api/v1/merchants/:id/invoices` | `from, to, status` |
| GET | `/api/v1/merchants/:id/monthly-reports` | |
| GET | `/api/v1/merchants/:id/monthly-reports/:period` | |
| GET | `/api/v1/merchants/:id/monthly-reports/:period/service-fee` | |
| GET | `/api/v1/merchants/:id/monthly-reports/:period/missed-installments` | |
| GET | `/api/v1/merchants/:id/monthly-reports/:period/errors-and-adjustments` | |
| GET | `/api/v1/merchants/:id/promotions` | |
| POST | `/api/v1/merchants/:id/promotions/:promotionId/join` | |
| POST | `/api/v1/merchants/:id/promotions/:promotionId/leave` | |

### Stores
| Method | Path | Query params |
|---|---|---|
| GET | `/api/v1/stores/:uuid` | |
| GET | `/api/v1/stores/:uuid/daily-conciliation` | `date` (YYYY-MM-DD) |
| GET | `/api/v1/stores/:uuid/daily-conciliation/last` | |
| GET | `/api/v1/stores/:uuid/daily-conciliation/history` | `limit, offset` |
| GET | `/api/v1/stores/:uuid/payment-methods` | `category` |
| GET | `/api/v1/stores/:uuid/pos` | |
| GET | `/api/v1/stores/:uuid/pos/qr-summary` | |
| GET | `/api/v1/stores/:uuid/products` | `search, sku, page, limit` |
| GET | `/api/v1/stores/:uuid/inventory/jobs` | |
| GET | `/api/v1/stores/:uuid/inventory/jobs/:jobUuid` | |

### Orders
| Method | Path | Query params / Body |
|---|---|---|
| GET | `/api/v1/orders` | `storeUuid, merchantId, status, channel, from, to, scenario, page, limit` |
| GET | `/api/v1/orders/cancellation-reasons` | `role` |
| GET | `/api/v1/orders/:orderNumber` | |
| GET | `/api/v1/orders/:orderNumber/installments` | |
| GET | `/api/v1/orders/:orderNumber/payments` | |
| POST | `/api/v1/orders/:orderNumber/cancel` | `{ employeeId, reasonId, securityCode? }` |
| POST | `/api/v1/orders/:orderNumber/invoice` | `{ employeeId, invoiceNumber }` |

**Reglas de cancelación por rol:**

| Rol | Restricción |
|---|---|
| ADMIN | Sin restricción |
| MANAGER (Gerente) | Requiere `securityCode` (`"123456"`), `securityCodeSet=true`, orden del mismo día |
| CASHIER | No puede cancelar (403) |

### Employees / 2FA
| Method | Path | Body |
|---|---|---|
| GET | `/api/v1/employees/:id` | |
| POST | `/api/v1/employees/:id/2fa/register-phone` | `{ phone }` |
| POST | `/api/v1/employees/:id/2fa/send-code` | |
| POST | `/api/v1/employees/:id/2fa/verify-code` | `{ code }` |

### POS
| Method | Path | Body |
|---|---|---|
| GET | `/api/v1/pos/:uuid` | |
| POST | `/api/v1/pos/:uuid/link-qr` | `{ activationCode }` |

### Onboarding
| Method | Path |
|---|---|
| GET | `/api/v1/onboarding/:onboardingId` |

### Reports / Movements
| Method | Path |
|---|---|
| GET | `/api/v1/reports` |
| GET | `/api/v1/movements` |

### Scenarios
| Method | Path | Descripción |
|---|---|---|
| GET | `/api/v1/scenarios` | Catálogo con todos los escenarios y IDs afectados |
| GET | `/api/v1/scenarios/:tag` | Detalle de entidades con un escenario específico |

## Catálogo de escenarios (22 tags)

Cada escenario simula un problema real del inbox de aliados. Ver `API.md` para
el detalle completo de cada uno.

| Tag | Problema |
|---|---|
| `2fa_phone_not_registered` | Empleado admin sin teléfono registrado → reportes bloqueados |
| `2fa_phone_already_registered` | El teléfono que pide registrar ya es el suyo |
| `2fa_otp_never_arrives` | send-code responde 200 pero verify-code siempre falla |
| `credentials_invite_not_delivered` | Empleado IN_PROGRESS con lastLoginAt=null |
| `password_change_required` | mustChangePassword=true |
| `security_code_not_set` | Gerente sin código de seguridad, no puede cancelar |
| `cashier_cannot_cancel` | Cajero intenta cancelar orden → 403 |
| `cancel_out_of_day_window` | Gerente intenta cancelar orden de ayer → 409 |
| `order_create_connection_error` | Store con flag de error de conexión |
| `invoice_registration_failing` | POST /invoice devuelve 503 |
| `order_incident_lost_shipment` | Orden con envío en estado de pérdida |
| `down_payment_not_reflected` | Pago móvil PENDING no conciliado |
| `payout_missing_for_period` | Payout PENDING sin sentAt |
| `payout_amount_mismatch` | netAmount ≠ compensation.totalAmount |
| `invoices_not_sent_multi_month` | 5 meses de facturas NOT_SENT |
| `isrl_retention_disputed` | ISRL anormalmente alto |
| `daily_conciliation_mismatch` | ordersCount no cuadra |
| `pos_qr_not_linked` | POS sin QR vinculado |
| `promotion_not_eligible` | Promo ACTIVE pero merchant no elegible |
| `model_migration_pending` | Merchant BASE migrando a EXPRESS, contrato sin firmar |
| `onboarding_stuck_documents` | Onboarding con documentos PENDING |
| `inventory_bulk_job_failed` | Job de carga masiva FAILED con errores por fila |

## Convenciones

- Dinero en **centavos enteros** + campo `currency` (`"USD"` o `"VES"`)
- Algunos objetos tienen monto dual: `amount` (USD cents) y `amountVES` (VES cents)
- Timestamps ISO 8601 con zona. Nullable explícito (`null`)
- Listas paginadas: `{ data, page, limit, total, totalPages }`
- Listas simples: `{ data: [...] }`
- Errores: `{ error: "..." }` con 400 / 403 / 404 / 409 / 503
- Latencia simulada: 40–200ms por request
- Órdenes identificadas por número de 9 dígitos (ej: `197000001`)
- RIF lookup tolerante: `J-40268443-6`, `j402684436`, `40268443` — todos matchean

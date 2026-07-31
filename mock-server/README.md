# BNPL Mock Server

Servidor mock que simula un sistema BNPL (Buy Now Pay Later) con data sintética.
Diseñado como sistema externo para que los AI agents de la plataforma lo consuman
via tools y resuelvan problemas de clientes.

## Setup

```bash
cd mock-server
bun install
bun run dev          # localhost:3001 con hot-reload
```

Para volcar el dataset a JSON:

```bash
bun run seed:dump    # genera data/seed.json
```

## Datos del seed

- 50 usuarios con direcciones, métodos de pago, cuentas de crédito y membresía
- ~100+ órdenes con cuotas, envíos, transacciones y puntos
- 24 usuarios con anomalías etiquetadas (ver Escenarios)

## Endpoints

### Health
| Method | Path | Descripción |
|---|---|---|
| GET | `/healthz` | Status check |

### Users
| Method | Path | Query params |
|---|---|---|
| GET | `/api/v1/users` | `page, limit, search, status, tier, scenario` |
| GET | `/api/v1/users/:id` | |
| GET | `/api/v1/users/:id/credit` | |
| GET | `/api/v1/users/:id/membership` | |
| GET | `/api/v1/users/:id/orders` | `status, page, limit` |
| GET | `/api/v1/users/:id/transactions` | `type, page, limit` |
| GET | `/api/v1/users/:id/points-history` | `page, limit` |
| GET | `/api/v1/users/:id/payment-methods` | |
| GET | `/api/v1/users/:id/addresses` | |

### Orders
| Method | Path | Query params |
|---|---|---|
| GET | `/api/v1/orders` | `userId, status, merchantId, page, limit` |
| GET | `/api/v1/orders/:id` | |
| GET | `/api/v1/orders/:id/installments` | |
| GET | `/api/v1/orders/:id/shipment` | |

### Installments
| Method | Path | Body |
|---|---|---|
| POST | `/api/v1/installments/:id/pay` | `{ paymentMethodId?: string }` |

### Shipments
| Method | Path | Body |
|---|---|---|
| GET | `/api/v1/shipments/:id` | |
| PATCH | `/api/v1/shipments/:id` | `{ status?: string }` |

### Transactions
| Method | Path | Query params |
|---|---|---|
| GET | `/api/v1/transactions` | `userId, type, page, limit` |

### Merchants
| Method | Path |
|---|---|
| GET | `/api/v1/merchants` |
| GET | `/api/v1/merchants/:id` |

### Membership
| Method | Path | Body |
|---|---|---|
| POST | `/api/v1/memberships/:id/redeem` | `{ amount: number }` |

### Payments
| Method | Path | Body / Query | Descripción |
|---|---|---|---|
| GET | `/api/v1/payments` | `userId, status, page, limit` | Lista pagos |
| GET | `/api/v1/payments/:id` | | Detalle de un pago |
| POST | `/api/v1/payments/validate` | `{ externalReference, userId }` | Valida un pago por referencia externa |
| POST | `/api/v1/payments/:id/reassign` | `{ installmentId }` | Reasigna un pago a otra cuota |

**Respuestas de `/payments/validate`:**

| Result | Descripción |
|---|---|
| `PAYMENT_CREATED_AND_VALIDATED` | Pago estaba pendiente, se valida y aplica a la cuota correcta |
| `PAYMENT_ALREADY_VALIDATED` | Pago ya fue validado. Si tiene `warning`, se aplicó a la orden equivocada |
| `PAYMENT_NOT_FOUND` | No existe pago con esa referencia para el usuario |

### Scenarios
| Method | Path | Descripción |
|---|---|---|
| GET | `/api/v1/scenarios` | Catálogo con todos los escenarios y usuarios asignados |
| GET | `/api/v1/scenarios/:tag` | Usuarios con un escenario específico |

## Escenarios de anomalías

Cada escenario representa un problema real que un cliente reportaría:

| Tag | Problema |
|---|---|
| `double_payment` | Pagó la misma cuota dos veces |
| `refund_pending` | Solicitó reembolso pero no se ha procesado |
| `shipment_stuck` | Envío en tránsito 15+ días sin actualizaciones |
| `shipment_lost` | Enviado pero sin tracking después del scan inicial |
| `shipment_never_shipped` | Orden activa pero envío estancado en "preparing" |
| `payment_not_reflected` | Pago con referencia bancaria pero cuota sin marcar como pagada |
| `missing_points` | Orden completada pero cero puntos acreditados |
| `partial_points` | Puntos acreditados a una tasa menor a la correcta |
| `stale_tier` | Puntos califican para mayor nivel pero no se actualizó |
| `overdue_unnotified` | Cuota vencida sin notificación al usuario |
| `failed_payment` | Pago falló pero el cobro sí se hizo |
| `overcharged` | Cobro mayor al monto de la cuota |
| `phantom_order` | Orden que el usuario no reconoce |
| `cancelled_but_charged` | Orden cancelada pero con cuotas posteriores cobradas |
| `payment_wrong_order` | Pago validado pero aplicado a la cuota de una orden equivocada |

## Convenciones

- Dinero en **centavos (enteros)** — dividir entre 100 para mostrar
- Timestamps en ISO 8601
- Listas paginadas: `{ data, page, limit, total, totalPages }`
- Latencia simulada: 40–200ms por request

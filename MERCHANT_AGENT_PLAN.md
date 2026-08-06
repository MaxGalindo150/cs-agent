# Merchant Agent — Plan de Implementación

> **Objetivo**: Que el agente de atención al **aliado (merchant)** pueda resolver casos
> reales (2FA, payouts, conciliación, cancelaciones, etc.) consultando el
> `merchant-mock-server` — sin construir un servicio aparte, reutilizando el
> `agent-service` existente con un perfil distinto.

---

## Decisión de arquitectura: multi-perfil en el mismo `agent-service`

**NO un servicio aparte.** El agent-service ya tiene loop, memoria, sessions,
streaming, tracing. Duplicar eso es tirar trabajo.

En su lugar, el agent-service soporta **dos perfiles** (`buyer` y `merchant`),
cada uno con su propio:
- **Registry** (conjunto de tools distinto)
- **Soul** (system prompt / persona)
- **HTTP client** (BNPL → `:3001`, Merchant → `:3002`)

El loop, la memoria, el tracer, los endpoints — todo compartido.

### Cambios por archivo

| Archivo | Qué cambia |
|---|---|
| `agent/identity.py` | `Principal` gana campos opcionales: `profile`, `merchant_id`, `store_uuid`, `employee_id`, `role` |
| `service/core/identity.py` | `get_principal` lee headers merchant cuando `X-Agent-Profile: merchant` |
| `agent/runtime/session.py` | `Session.__init__` recibe `soul: str` (default `DEFAULT_SOUL`); `build_system` usa `self._soul` |
| `agent/app.py` | `Agent.__init__` recibe `soul: str`; lo pasa al `Session` que crea en `respond()` |
| `agent/tools/__init__.py` | Nueva `build_merchant_registry(merchant_client, db)` |
| `service/core/tooling.py` | Nueva `build_merchant_client(settings)` |
| `service/main.py` | Lifespan construye 2 registries, 2 agents; `app.state.merchant_agent` |
| `service/core/agent.py` | `get_agent` selecciona agent por header `X-Agent-Profile` |
| `agent/tools/implementations/merchant/` | **Nuevo**: ~12 tools del merchant |
| `merchant-mock-server/public/index.html` | **Widget de chat** añadido al dashboard |
| `agent-service/src/service/core/config.py` | `allowed_origins` añade `http://localhost:3002` |

---

## Fases

### Fase 1 — Multi-perfil en agent-service ✅
- [x] Extender `Principal` con campos merchant
- [x] Extender `get_principal` para leer headers merchant
- [x] Añadir `soul` a `Session` y `Agent`
- [x] `build_merchant_client` + `build_merchant_registry`
- [x] Lifespan: dos agents
- [x] `get_agent` selecciona por header `X-Agent-Profile`
- [x] CORS: añadir `localhost:3002`

### Fase 2 — Tools del merchant agent ✅
- [x] `search_merchant` — buscar merchant por RIF o nombre
- [x] `list_merchant_orders` — órdenes del merchant con filtros
- [x] `get_order_detail` — detalle de una orden por orderNumber
- [x] `get_order_installments` — cuotas y pagos de una orden
- [x] `cancel_order` — cancelar orden (respeta reglas de rol)
- [x] `get_cancellation_reasons` — motivos de cancelación
- [x] `get_payouts` — transferencias del merchant por periodo
- [x] `get_invoices` — facturas del merchant
- [x] `get_monthly_report` — reporte mensual + detalles
- [x] `get_daily_conciliation` — conciliación diaria de una store
- [x] `get_employee_2fa` — estado 2FA de un empleado
- [x] `register_2fa_phone` — registrar teléfono 2FA
- [x] Catálogo de escenarios disponible por API para eval; no se expone al agente del aliado

### Fase 3 — System prompt del merchant agent ✅
- [x] `MERCHANT_SOUL` — persona del agente de soporte al aliado

### Fase 4 — Widget de chat en merchant dashboard ✅
- [x] Panel de chat inline en `public/index.html` (sin iframe)
- [x] Funciona sin merchant seleccionado (anónimo)
- [x] Funciona con merchant seleccionado (autenticado)
- [x] Envía header `X-Agent-Profile: merchant`
- [x] Envía `X-Merchant-Id` al seleccionar merchant; `X-Employee-Id` solo cuando el host identifica un empleado

### Fase 5 — Testing + docs ✅
- [x] Typecheck merchant-mock-server (`bunx tsc --noEmit`) — limpio
- [x] Compile-check agent-service (`python3 -m py_compile`) — limpio
- [x] Endpoints del mock server verificados (`/healthz`, `/api/v1/scenarios`, `/api/v1/merchants`)
- [x] CORS configurado para `localhost:3002`
- [x] Widget de chat visible en pantalla de selección (anónimo) y dentro del portal (autenticado)

# Runbook — probar y medir el modelo de decisión (Jev) en el harness

Cómo encender, probar sitio por sitio, leer las trazas y medir el impacto de
ADR-0004 en local. Todo corre con Docker + `uv`; nada depende de la nube.

## 0. Requisitos

```bash
cd agent-service
cp .env.example .env            # si no existe
# en .env: ANTHROPIC_API_KEY, VOYAGE_API_KEY, TYPESAFE_API_KEY
docker compose -f ../docker-compose.yml up -d postgres
uv sync --extra dev
```

Con `TYPESAFE_API_KEY` vacía **nada cambia**: cada sitio es un no-op y no se
traza ninguna decisión. Con la key puesta, todos los sitios quedan activos
(no hay modo shadow ni interruptores por sitio — ver ADR-0004 §5).

**macOS detrás de Cloudflare Zero Trust:** Python no confía en la CA de
Cloudflare y `api.typesafe.ai` falla con `CERTIFICATE_VERIFY_FAILED`. Una vez:

```bash
security find-certificate -a -p /Library/Keychains/System.keychain > /tmp/sys.pem
cat "$(uv run python -c 'import certifi;print(certifi.where())')" /tmp/sys.pem \
  > ~/.config/cashea-ca-bundle.pem
echo 'SSL_CERT_FILE=/Users/<tú>/.config/cashea-ca-bundle.pem' >> .env
```

Comprobación rápida (debe responder `HTTP 403` = servidor alcanzado, falta auth):

```bash
set -a; . ./.env; set +a
uv run python -c "import httpx; print(httpx.post('https://api.typesafe.ai/v1/systemone', json={}).status_code)"
```

## 1. Verificación sin red (CI local)

```bash
uv run ruff check src tests scripts && uv run ruff format --check src tests scripts
uv run mypy src tests scripts
uv run pytest -q                  # unit + contract + integration (Postgres)
uv run pytest --cov -q            # fail_under = 80 %
```

Los tests que cubren cada sitio, por si solo quieres uno:

| Sitio | Tests |
| --- | --- |
| cliente Jev | `tests/unit/test_decide_jev.py` |
| política de cada sitio (umbral, fallback, trazas) | `tests/unit/test_decide_sites.py` |
| gate, re-rank, skills en la fachada de memoria | `tests/unit/test_memory_decisions.py` |
| review de tools, preguntar-o-actuar, presupuestos | `tests/unit/test_loop_decisions.py` |
| juez, LLM-judge, feedback → diagnóstico (HTTP) | `tests/integration/test_respond_decisions.py` |
| gate de consolidación y filtro de hechos | `tests/integration/test_consolidation_decisions.py` |
| `propose_skill` | `tests/unit/test_propose_skill.py` |
| registros `decision`/`score` del tracer | `tests/unit/test_tracing_decisions.py` |
| forma del set etiquetado | `tests/unit/test_jev_cases.py` |

## 2. Replay en vivo del set etiquetado (Level 2)

94 casos en lenguaje de aliado (`evals/jev/cases.jsonl`), contra el catálogo
real de skills y tools de merchant:

```bash
set -a; . ./.env; set +a
uv run python scripts/jev_replay.py                      # todos los sitios
uv run python scripts/jev_replay.py --site tool_review --verbose
uv run python scripts/jev_replay.py --threshold 0.7      # probar otro umbral
uv run python scripts/jev_replay.py --out /tmp/replay.json
```

Lee por sitio: exactitud, p50/p95 de latencia y la mediana de confianza de
aciertos vs errores (la separación es lo que justifica el umbral). Sale con
código 1 si algún sitio baja de `--min-accuracy` (0.8). CI corre esto en el
job `jev-eval` cuando el secreto `TYPESAFE_API_KEY` existe.

Cuando una etiqueta sea discutible, cambia el caso, no el umbral: el set es
la fuente de verdad del comportamiento esperado.

## 3. Probar el servicio a mano

```bash
set -a; . ./.env; set +a
TRACE_DIR=.traces uv run uvicorn service.main:app --port 8000
```

Al arrancar debe loguear `decisions.configured enabled=True model=jev-latest`.

### 3.1 Perfil consumer (rápido, cabeceras dev)

```bash
H=(-H 'Content-Type: application/json' -H 'X-User-Id: dev_1' -H 'X-User-Email: dev@example.com')
curl -s -X POST localhost:8000/v1/chat "${H[@]}" -d '{"message":"Hola, buenos días"}'
# continúa con el session_id que devuelve
curl -s -X POST localhost:8000/v1/chat "${H[@]}" -d '{"session_id":"<id>","message":"Otra vez me pasa lo mismo con la cuota, ¿en qué quedó lo de ayer?"}'
```

### 3.2 Perfil aliado (merchant)

Un aliado solo existe con un token Firebase del host (merchant-web staging)
intercambiado en `POST /v1/auth/session`; las cabeceras dev dan siempre un
consumer. Levanta el stack completo (`docker compose up --build`) y usa el
widget embebido con una cuenta de aliado de staging. Mensajes que disparan
cada sitio:

| Sitio | Mensaje de prueba | Qué mirar |
| --- | --- | --- |
| `retrieval` | "Otra vez me pasa lo mismo con el cierre de caja" | `gate.decision=retrieve`, `reason=jev p=…`; "Hola" → `skip` |
| `skill_match` | "¿Qué pasa si no cierro la caja un día?" | `decision.site=skill_match verdict.skills=['daily-closing']`; en `meta.skills` del mensaje |
| `memory_select` | cualquier retrieve con filas | `verdict.offered` vs `verdict.kept` |
| `tool_review` | "Dame el detalle de la orden 197688580" | `decision.site=tool_review verdict.fits=true`; un misfit confiado produce un evento `nudge` y el `tool_result` empieza por "Harness review" |
| `ask_or_act` | pedir algo resoluble y ver si el modelo pregunta | `verdict.action`, `nudged`; en `meta.nudges` si el modelo insistió |
| `judge` | cualquier turno | tres `score` (`jev.quality`, `jev.grounded`, `jev.resolved`) con el `message_id`; `llm.quality` cuando Jev dudó |
| presupuestos | `MAX_TOOL_CALLS_PER_TURN=1` y un pedido que use dos tools | `limit_reached reason=tool_calls`, `meta.budget_exhausted` |

### 3.3 Feedback → diagnóstico

```bash
# id del último reply
curl -s localhost:8000/v1/sessions/<sid>/messages "${H[@]}" | jq '.[-1].id'
curl -s -X PUT localhost:8000/v1/sessions/<sid>/messages/<mid>/feedback "${H[@]}" \
  -d '{"rating":"down","comment":"no me dijo dónde está la orden"}'
```

Produce `score user_feedback=-1`, `decision.site=diagnose` y
`score jev.diagnosis=<failure_site|unsure>` + `jev.actionable`, todos con el
mismo `message_id`.

### 3.4 Consolidación

```bash
# INTERNAL_WORKER_TOKEN=algo en .env; ≥ CONSOLIDATE_EVERY intercambios de un usuario
curl -s -X POST localhost:8000/internal/consolidate -H 'X-Worker-Token: algo'
```

Respuesta por usuario: `facts`, `episodes`, `skipped` (el gate decidió que no
había nada que guardar) y `dropped_facts` (hechos que el filtro rechazó).

### 3.5 `propose_skill` (experimental)

`SKILL_PROPOSALS_ENABLED=true` y pedirle al agente, tras resolver algo sin
procedimiento, que proponga una nota. Busca el evento `skill_proposal` en la
traza: trae el borrador completo y el veredicto. Nunca se carga ni se escribe.

## 4. Leer las trazas

Con `TRACE_DIR` puesto, en ese directorio:

| Archivo | Qué hay |
| --- | --- |
| `<fecha>.jsonl` | toda la traza del turno, en orden: `turn_start`, `gate`, `decision`, `llm`, `tool_start`, `nudge`, `tool`, `score`, `limit_reached`, `turn_end` |
| `decisions.jsonl` | solo los `decision`: `site`, `source` (`jev`/`fallback`), `answers` (las primitivas crudas: `p`, `choice`+`confidence`+`probabilities`, `score`), `verdict`, `acted`, `baseline`, `agreement`, `latency_ms`, `usage` |
| `scores.jsonl` | solo los `score`: `name`, `value`, `data_type`, `source`, `message_id`, `comment` — la forma del score de Langfuse |
| `usage.jsonl` | tokens del LLM por llamada |

Todo sale también por stdout (structlog, loggers `agent.decision` y
`agent.score`) y, con `OTEL_EXPORTER_OTLP_ENDPOINT`, como spans
`GUARDRAIL` / `RERANKER` / `EVALUATOR` (Phoenix en `localhost:6006` con el
compose).

```bash
jq -c 'select(.site=="tool_review") | {verdict, acted, latency_ms}' .traces/decisions.jsonl
jq -c '{name, value, message_id}' .traces/scores.jsonl
```

## 5. Medir

```bash
uv run python scripts/jev_report.py                      # .traces/
uv run python scripts/jev_report.py --trace-dir /tmp/x --json
```

Por sitio: llamadas, tasa de `acted`, tasa de fallback, acuerdo con el método
anterior (solo `skill_match` lo mide: el keyword matcher sigue corriendo
porque es gratis), histograma de confianza, p50/p95, tokens. Por turno:
iteraciones, tool calls, errores de tools, tokens, presupuestos agotados,
nudges y si el modelo insistió, distribución del `jev.quality`, tasas de
grounded/resolved, escalaciones al LLM-judge, 👍/👎 y diagnósticos.

Cuando llegue Langfuse: cada `decision` es una observación con su span kind y
cada `score` es un `score` de Langfuse sobre el trace del `message_id`. El
emisor no cambia; se añade un sink.

## 6. Qué tocar y qué no

- **Umbral** (`JEV_CONFIDENCE_THRESHOLD`): solo con datos del replay
  (`--threshold`), nunca por un incidente aislado.
- **Preguntas de un sitio**: en `src/agent/decide/sites.py`; vuelve a correr
  el replay de ese sitio antes y después.
- **Apagar Jev**: vaciar `TYPESAFE_API_KEY`. Apagar un solo sitio no es
  posible por diseño en este POC; si hace falta, es un cambio de código.
- **Rollback completo**: ADR-0004 §Reversal.

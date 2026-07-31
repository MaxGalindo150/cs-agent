# Integration tests — the `respond()` offline harness

> Status: **built** (`helpers.py`) and in use (`test_respond.py`). This documents
> what it is and why. Still to port on top of it: the history-window end-to-end
> test and the "hola soy max → quién soy" continuity test.

## What it is

Two small pieces of test plumbing, mirroring Waku's `evals/helpers.py`
(`ScriptedClient` + `make_waku`), adapted to this service:

1. **A scripted `AsyncAnthropic`** — a fake LLM client that plays back a fixed
   list of canned responses instead of calling Anthropic. It lets a whole turn
   (`respond()`) run **offline**: deterministic, free, and fast.

2. **A `make_agent` fixture** — a factory that assembles a real `Agent` over the
   **test Postgres** (the existing `database` fixture in `conftest.py`): builds
   `Memory` + `Tracer` + the scripted client + `AgentConfig`, and returns a wired
   `Agent` whose `respond()` you can call and then assert on the DB.

## What it's for

To test the **orchestration path** (`agent/app.py::respond` and everything it
touches) **deterministically and offline**:

- **No real LLM.** Real Anthropic calls are slow, cost money, and are
  non-deterministic — useless for a regression net. The scripted client returns
  exactly the blocks each test needs (a tool call, then a final answer, etc.).
- **Real Postgres.** Unlike the LLM, the database is deterministic and central to
  what we're testing: history reload across turns, `meta` persistence on the
  assistant row, the `chat_messages → chat_sessions` FK, the retrieval-gate write
  path. So we keep it real (via the `database` fixture), only faking the model.

This is the Level-2 seam from `CLAUDE.md §8`: component behaviour against a real
store, with the model stubbed.

## What it unlocks (the Waku tests it lets us port)

- `test_turn_meta` → `respond()` persists the turn `meta` (gate decision,
  iterations, latency, tools, model/provider) on the assistant row, so a reopened
  thread renders the full card.
- **history-window end to end** → after N turns, the prompt sent to the loop
  contains at most `history_turns` turns and drops the oldest (the sliding
  window, exercised through `switch()` + the `messages` slice).
- **continuity** → "hola soy max" (turn 1) then "quién soy" (turn 2, same
  `session_id`) reloads history from Postgres and the model sees the name.

## Two gotchas (why we can't copy Waku's helpers verbatim)

1. **Real Anthropic block types, not `SimpleNamespace`.** Waku's loop duck-types
   (`block.type == "tool_use"`), so its `ScriptedClient` yields `SimpleNamespace`
   fakes. Our loop uses `isinstance(block, ToolUseBlock)` / `isinstance(block,
   TextBlock)` (SDK types at the boundary, `CLAUDE.md §6`), so the scripted
   responses must be **real `anthropic.types` objects** — `Message`, `TextBlock`,
   `ToolUseBlock`, `Usage` — or `isinstance` fails and the loop mis-reads them.

2. **Async, not sync.** Waku's client is sync (`messages.create`). Ours is
   `AsyncAnthropic` (`await messages.create`, and `messages.stream` as an async
   context manager for the streaming path). The scripted client must be `async`,
   and support both `create` and, if we test streaming, `stream`.

## Sketch

```python
# tests/integration/conftest.py  (to add)

@pytest.fixture
def scripted_client() -> ...:
    """AsyncAnthropic stand-in: pass a list of anthropic Message objects; each
    `await messages.create(...)` pops and returns the next one."""

@pytest.fixture
async def make_agent(database, scripted_client) -> ...:
    """Build a wired Agent over the test DB with a fake model injected —
    respond() runs end to end, then you assert on chat_messages / facts."""
```

The scripted client is the reusable core: once it exists, every future
`respond()` test is a short script of canned turns + DB assertions.

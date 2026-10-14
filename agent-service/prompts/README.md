# Prompts

Everything the agent says to a model, as Markdown. Loaded by
`src/agent/prompts.py::load_prompt("<dir>/<name>")` — once, at import: a
missing or empty file stops the service at boot. In dev, saving a file here
reloads the service (`--reload-include *.md`).

| Path | Used by |
|---|---|
| `souls/consumer.md` | The agent's persona and rules for end customers (`agent/runtime/session.py`) |
| `internal/retrieval_gate.md` | Fast-model gate: should this turn search memory? (`agent/memory/retrieval_gate.py`) |
| `internal/memory_summarizer.md` | Distils conversations into facts/episodes (`agent/memory/consolidation.py`) |

Rules:

- **Static text only.** Per-turn values (the clock, who the caller is) are
  appended by code, not templated in.
- `internal/*` prompts are `str.format` templates: `{message}` / `{log}` are
  filled in, and literal braces are doubled (`{{` / `}}`).
- A prompt change is a code change: its own commit, reviewed, and — once the
  evals land — run against them before merging.

Domain policies that load only when relevant are **skills**, not prompts: see
`../skills/`.

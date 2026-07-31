# ADR-0003 — Semantic memory retrieval: pgvector embeddings on `facts`

- **Status:** Proposed
- **Date:** 2026-07-22
- **Deciders:** Maximiliano Galindo
- **Context service:** `agent-service` (EigenCore Customer Support)
- **Supersedes / relates to:** amends **ADR-0002** — specifically its Decision #7 ("pgvector
  deferred") and the matching "pgvector from day one — deferred" alternative. Everything else in
  ADR-0002 (owned `agent` schema, async + short connections, four tables, UUID PKs, single-tenant)
  stands unchanged. Aligns with the platform's `docs/rag-design.md` conventions.

---

## Context

ADR-0002 chose Postgres full-text (`tsvector` + GIN, `spanish`) as the retrieval mechanism for
`facts` (semantic memory) and deferred pgvector "until it is needed, under its own ADR." This is
that ADR.

Why revisit now:

1. **Keyword search misses paraphrase.** FTS matches shared lexemes. In support, the customer's
   wording rarely matches the stored fact's wording: *"no me deja pagar en cuotas"* should surface
   *"el cliente está en el plan Pro con BNPL habilitado"*. Stemming can't bridge that; embeddings
   can. This is the one thing FTS structurally cannot do, and it is common in this domain.
2. **The infrastructure is already here, at zero marginal cost.** The shared DB runs
   `pgvector/pgvector:pg18` (ADR-0002 §4). Enabling it for `facts` is a migration, not an infra
   change — no new service, no new container.
3. **House conventions already exist.** `docs/rag-design.md` (adopted 2026-07-11) fixes how this
   platform does pgvector: `halfvec` storage, HNSW `halfvec_cosine_ops`, embed-before-connect. We
   mirror those *storage/index* conventions so agent memory and the KB RAG system read the same
   way. (We deliberately diverge on the *provider* — see Decision #1.)

Constraints carried over from ADR-0002 that shape this decision:

- **No DB connection held across an external call** (`CLAUDE.md` §3). Embedding is an external API
  call; it must happen **before** any session is opened — exactly `rag-design.md` §5's rule.
- **Single-tenant** (`CLAUDE.md` §9). Unlike `rag-design.md`'s `kb_chunks`, `facts` has no
  `workspace_id`/`kb_id` filter — so no HNSW-with-filter concern, and pgvector ≥ 0.8 iterative
  scans are not required for correctness here (though the version provides them anyway).
- **Config over constants** (`docs/v1-lessons.md` #7: the v1 platform hardcoded one global
  embedding model; do not repeat that). Provider, model, and dims are injected, not literals.

## Decision

Add **vector retrieval to `facts`** using pgvector, keeping the existing `tsvector` column for
graceful degradation and a future hybrid step. Scope is **`facts` only**; `episodes` stay FTS
(their retrieval is relevance + recency on dated rows — see "Scope", below).

1. **Embedding model — Voyage `voyage-3.5` (1024 dims).** Voyage is **Anthropic's recommended
   embeddings pairing**; on an Anthropic-first service it keeps the reasoning and embedding vendors
   aligned. `voyage-3.5` is the general-purpose model at its default 1024 dims — ample for short,
   per-customer facts, and cheaper to store/index than 1536+. Injected via config
   (`EMBEDDING_MODEL`, `EMBEDDING_DIMS`), never hardcoded (v1-lessons #7). Voyage distinguishes
   `input_type`: facts are embedded as `document`, the search query as `query` — a retrieval-quality
   win OpenAI does not offer. This is a **deliberate divergence from Waku** (which used OpenAI
   `text-embedding-3-small`): the provider is not one of the two sanctioned Waku differences, but
   the Anthropic-native pairing is worth it and the `Embedder` seam makes it reversible.
2. **Storage — `halfvec(1536)`, nullable.** fp16 per `rag-design.md`: half the memory, negligible
   recall loss, HNSW-indexable. `NULL` until embedded (a fact can exist un-embedded and still be
   FTS-searchable).
3. **Index — HNSW `halfvec_cosine_ops`, `m=16`, `ef_construction=64`.** Identical to
   `rag-design.md` §3. Cosine distance (`<=>`). `ef_search` tunable per query if recall needs it.
4. **Drift column — `embedding_model text`.** Records which model produced each vector, so a model
   change is detectable and a re-embed sweep can target stale rows (`rag-design.md` §4).
5. **Retrieval — embed the query first (`input_type=query`), then a short session.** `FactStore.search`
   makes the one embedding call **before** opening any session, then orders by `embedding <=> $qvec`.
   The gate (ADR-0002 companion) still decides *whether* to retrieve at all; this changes only *how*
   the search ranks.
6. **Write path — embed on `add` (`input_type=document`), before the session.** `FactStore.add`
   embeds `subject + content` first (no connection held), then opens a short session to insert row
   + vector. Consolidation embeds its batch before its write session.
7. **Graceful degradation — fall back to FTS on embedding failure.** If the embedding call fails,
   `search` logs it and falls back to the retained `content_tsv` keyword search rather than
   returning nothing. The tsv column already exists (ADR-0002), so this costs nothing and keeps
   retrieval working when OpenAI is down. This is *degradation, not a silent failure* — it is
   logged and surfaced via the gate's `notify` channel.
8. **Interfaces unchanged.** `PostgresFactStore.add/search` keep their signatures and their
   string-formatted output; the change is internal to the store + `FactRepository`. The `Memory`
   facade and `gated_retrieve` are untouched. (This is the reversal seam ADR-0002 promised.)

### Schema change (`agent.facts`)

```sql
-- migration 0003: extension is idempotent; type lives in public, reachable via search_path
CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE agent.facts
    ADD COLUMN embedding       halfvec(1024) NULL,   -- dims per config; NULL until embedded
    ADD COLUMN embedding_model text NULL;            -- which model produced `embedding`

CREATE INDEX ix_facts_embedding_hnsw ON agent.facts
    USING hnsw (embedding halfvec_cosine_ops) WITH (m = 16, ef_construction = 64);
-- content_tsv + its GIN index (ADR-0002) are retained for degradation + future hybrid.
```

Greenfield: no production rows exist yet, so no backfill is needed on first apply. A later model
change triggers a re-embed sweep over rows whose `embedding_model` is stale (queued work, not a
migration).

### New dependencies & config

- **Deps:** `pgvector` only (SQLAlchemy `HALFVEC` type). Voyage is called over the **existing
  `httpx` async client** — its `/v1/embeddings` REST endpoint is one POST. The `voyageai` SDK was
  evaluated and **rejected**: it pulls `aiohttp` (a second HTTP stack) plus `langchain-core` /
  `langsmith` / `tokenizers` / `numpy` transitively — exactly the heavy-framework bloat
  `CLAUDE.md` §2.5/§5 forbids, and needless weight in a Cloud Run image for a single HTTP call.
- **Config / secrets:** `VOYAGE_API_KEY` (Secret Manager in deploy, `.env` locally),
  `EMBEDDING_MODEL` (default `voyage-3.5`), `EMBEDDING_DIMS` (default `1024`).
- The embedder is a small provider-neutral interface in `agent/memory` (an `Embedder` protocol +
  an httpx-based Voyage implementation), injected like `DatabaseConfig` — no vendor SDK in the
  store logic, keeping the OCR/LLM/embedding vendors independently swappable (`CLAUDE.md` §5).

## Consequences

**Positive**
- Retrieval finds facts by *meaning*, not shared words — the paraphrase gap closes for support.
- Fully within the existing DB; no new infrastructure, consistent with the KB RAG design.
- FTS retained → resilient (degrades, doesn't fail) and hybrid RRF is a later additive step.
- Store interface unchanged → facade, tests, and the harness loop are unaffected.

**Negative / costs**
- A new vendor dependency (**Voyage**) and a per-fact + per-query **embedding cost + latency** on
  the retrieval path. Mitigated: the gate already suppresses most retrievals; small model; facts
  are few and short.
- A second retrieval mechanism to reason about (vector *and* tsv), and a re-embed story on model
  change.
- One embedding call is added to the hot path when the gate says "retrieve" — measured against the
  `CLAUDE.md` §5 efficiency axis; acceptable because it is gated and off the reply-latency-critical
  path (it precedes, not blocks, the main model call).

## Alternatives considered

- **Stay FTS-only (ADR-0002).** Rejected now: the paraphrase miss is real and common in support;
  the infra cost of fixing it is a migration, not a service.
- **Hybrid (vector + FTS with RRF) from the start** (`rag-design.md` §5). Deferred: RRF fusion adds
  SQL and tuning; vector-primary with FTS *fallback* captures most of the win at a fraction of the
  complexity. The retained tsv column makes hybrid a later additive change, not a rewrite.
- **OpenAI `text-embedding-3-small`** (what Waku and the KB RAG example use). Deferred, not
  rejected: it would minimize divergence from Waku, but Voyage is the Anthropic-native pairing and
  offers `input_type` query/document specialization. The `Embedder` interface + drift column make
  switching back a config + re-embed, not a redesign.
- **Embed `episodes` too, now.** Deferred: episodic retrieval leans on recency over paraphrase, and
  the "semantic store" is the decision in front of us. Additive later if evidence warrants.
- **Local/open embedding model (no external call).** Rejected for now: adds model-hosting weight to
  a serverless service; revisit only if embedding cost or the OpenAI dependency becomes a problem.

## Reversal

Vector retrieval lives behind `FactRepository` / `PostgresFactStore`, not in the harness. To back
out: drop the HNSW index + columns (a down-migration) and revert `search` to `content_tsv` — which
is still present. To change providers: swap the `Embedder` implementation and run a re-embed sweep.
Neither touches the facade, the harness, or business rules.

## References

- ADR-0002 — memory & session persistence (amended here: Decision #7 and its alternative).
- ADR-0001 — agent architecture & harness.
- `docs/rag-design.md` (parent) — `halfvec`, HNSW `halfvec_cosine_ops` (m=16, ef=64), embed-before-connect, per-KB config.
- `docs/v1-lessons.md` #7 (parent) — embedding config must not be a hardcoded global constant.
- `CLAUDE.md` (this service) — §3 (no connection across an external call), §5 (efficiency/modularity), §9 (single-tenant, ADR gate).
- Voyage AI docs — `voyage-3.5`, `input_type` (query/document), output dimensions & quantization.
- Waku `waku/memory/semantic/supabase_store.py` — the OpenAI `text-embedding-3-small` path we diverge from here.

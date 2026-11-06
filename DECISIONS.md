# DECISIONS

Append-only log of decisions made while adapting this fork. Never edit or delete
an existing entry; to change course, add a new entry that supersedes it.

---

## D-001 — Create DECISIONS.md and its template

- **Date:** 2026-11-06
- **Step:** 0
- **Context:** The instructions say to use "the template at the bottom of the file",
  but the fork had no DECISIONS.md.
- **Decision:** Create the file with a short header and a template at the bottom
  (Date / Step / Context / Decision / Alternatives considered / Why).
- **Alternatives considered:** (a) Stop and ask for the template. (b) Use an ADR
  format (Status / Consequences).
- **Why:** The fields asked for (alternatives considered and why) are explicit, so
  a minimal template that captures exactly those fields is low-risk. (a) would block on
  a trivial point. (b) adds fields that weren't asked for.

---

## D-002 — Corpus: FastAPI tutorial docs (Markdown, MIT)

- **Date:** 2026-11-06
- **Step:** 0 (chosen before Task 1)
- **Context:** The owner asked for a public corpus suitable for testing and validation.
  The ingestion path accepts only `.pdf`, `.md` and `.markdown`
  (`backend/app/api/v1_ingest.py`, `backend/app/ingestion/loader.py`).
- **Decision:** About 30 Markdown pages from `docs/en/docs/tutorial/` in `fastapi/fastapi`
  (MIT licence), recorded with the source commit in `corpus/SOURCE.md`.
  The owner confirmed this choice ("go with option 1").
- **Alternatives considered:** Docker docs (Apache 2.0), Kubernetes docs (CC BY 4.0),
  and SQuAD/HotpotQA/BEIR benchmarks (JSON).
- **Why:** Clean Markdown that ingests natively and has a permissive licence matching
  this project's. Its factual questions suit keyword checks. The Docker and Kubernetes
  docs carry heavy Hugo shortcode noise. The benchmarks would need a format converter,
  which is out of scope.

---

## D-003 — Step 0: how the system works (read-only summary)

- **Date:** 2026-11-06
- **Step:** 0
- **Context:** Summary required by Step 0, written from reading the README,
  `docker-compose.yml`, `.env.example` and `backend/app/**`.

**Ingestion** (`POST /v1/ingest`, multipart `file` + `access_level`):
- `v1_ingest.py` validates the suffix (pdf/md/markdown) and access level. It then tries
  to enqueue an ARQ job on Redis (`worker.py`). On any failure it falls back to running
  `ingestion/pipeline.py::ingest_document` synchronously in the request.
- Pipeline: SHA-256 delta-sync check (skips unchanged files and purges changed ones),
  then load, chunk, validate, scrub PII, embed, upsert, extract the knowledge graph.
  - Load: Markdown becomes one document. PDFs go through the Gemini Vision loader when
    `use_vision_ingestion=True` (default), falling back to PyMuPDF.
  - Chunk: `packages/ingestion/semantic_splitter.py` (embedding-similarity sentence
    grouping), falling back to character chunks (512 / 64 overlap).
  - Validate requires `access_level`. PII scrubbing masks emails, SSNs and API keys.
  - Upsert writes to Postgres `document_chunks` (`vector(1536)`, HNSW cosine index,
    generated `tsvector`).
  - Finally, Gemini entity extraction writes to Neo4j. This step is non-fatal.
- Chunks are stored with `source` = the uploaded filename.

**Retrieval / answering** (`POST /v1/query`, JSON `{query, access_level, top_k, use_hyde}`,
which requires a Bearer token from `/v1/auth/login`):
- Embed the query, then check the Redis semantic cache (cosine ≥ 0.98).
- Then run the LangGraph graph in `agents/workflow.py`:
  - `semantic_router` (Gemini) picks one route:
    - `analytical` goes to `sql_agent`, which answers from the LLM with **no retrieval**.
    - `summarization` goes to `summarize_document`, which also uses **no retrieval**.
    - `document` goes to `retrieve`.
  - `retrieve` uses `query_classifier` (Gemini). Multi-hop queries do a Neo4j traversal
    and fall back to hybrid search. Simple queries do hybrid search: pgvector cosine plus
    Postgres full-text, fused with RRF (k=60), top_k=5, filtered by access level.
  - `grade_documents` (Gemini): each chunk is graded yes/no. **Only chunks graded "yes"
    are returned in the response's `chunks`.** If any are relevant, `generate` runs with
    OpenAI chat. If none are, `deep_research` runs, which is `generate` with an empty
    context.
  - `web_search` (Tavily), `query_rewrite` and `secondary_search` are registered as
    nodes but no edge reaches them, so they never run.
- The response includes `chunks[].source` (filename), so retrieved source filenames
  are available to an eval.

**Providers** (`backend/app/core/config.py`, `.env.example`):
- OpenAI: embeddings `text-embedding-3-small` (1536-d) and generation `gpt-4o-mini`.
  `OPENAI_API_KEY` is **required**; settings fail to load without it.
- Google Gemini: router `gemini-3.1-flash`, grader and classifier `gemini-3.0-flash`,
  PDF vision and entity extraction `gemini-3.1-pro`. `GEMINI_API_KEY` is optional at
  startup but is used on every query.
- Anthropic (HyDE, `claude-3-5-haiku-20241022`): configured, but no reachable code path
  produces a HyDE answer.
- Tavily: configured, but the node is unreachable.
- Data stores: Postgres + pgvector, Neo4j 5, and Redis Stack (cache and ARQ queue).

**Bundled sample data:** `db/init.sql` seeds only `system_settings`, not documents.
No sample corpus is auto-ingested. `backend/evaluation/golden_queries.json` and
`backend/mock_server.py` reference sample filenames but load nothing into the
database.

---

## D-004 — Step 0 startup fix #1: provide `backend/.env`

- **Date:** 2026-11-06
- **Step:** 0
- **Context:** The README says `cp .env.example .env`, then `docker compose up --build`.
  Compose fails with `env file /home/user/nexusbase/backend/.env not found`, because
  `docker-compose.yml` uses `env_file: ./backend/.env`.
- **Decision:** Also copy `.env` to `backend/.env`. No tracked file was changed.
  Both paths are covered by `.gitignore` (verified with `git check-ignore`).
- **Alternatives considered:** Edit `docker-compose.yml` to point at `./.env`, or edit
  the README instructions.
- **Why:** This is the smallest fix and touches no tracked file.

---

## D-005 — Step 0 STOPPED: more than three fixes needed to start the stack

- **Date:** 2026-11-06
- **Step:** 0
- **Context:** After fix #1, I verified the following blockers, either by running
  the stack or by importing the app in a scratch virtualenv with the project's own
  dependencies installed:
  1. **Docker build has no network in this cloud sandbox.** `apt-get update` in
     `backend/Dockerfile` fails with `Could not resolve 'deb.debian.org'`. This is an
     environment limit, not a repo bug. The DB, Neo4j and Redis images pulled fine.
  2. **Missing dependency `email-validator`.** `app.domain.users` uses `EmailStr`, so
     `import app.main` fails with `ImportError: email-validator is not installed`.
  3. **Missing dependency `python-jose`.** `app/services/auth_service.py` imports
     `jose`, which isn't in `pyproject.toml`.
  4. **Missing module `app.infrastructure.redis_cache`.** It's imported by
     `api/v1_query.py`, so every `/v1/query` returns 500. `check_cache` and
     `store_cache` exist in `app/retrieval/semantic_cache.py`.
  5. **No `users` table.** It's not in `db/init.sql` or the Supabase migration, so
     `/v1/auth/register` and `/login` fail, and `/v1/query` requires auth.
  6. (Non-blocking) `worker.py` imports the missing `app.config`. Ingestion falls back
     to synchronous mode, so it still works.
- **Decision:** Stop and report to the owner, per the rule "stop and report if more
  than three fixes are needed". No code has been changed.
- **Alternatives considered:** Apply all fixes anyway (would break the explicit rule),
  or route around auth or the cache (would be guessing).
- **Why:** The instructions set a hard limit of three fixes.

---

## Template (copy below this line for new entries)

```
## D-NNN — <short title>

- **Date:** YYYY-MM-DD
- **Step:** 0 | 1 | 2 | 3
- **Context:** What prompted the decision.
- **Decision:** What was chosen.
- **Alternatives considered:** Other options.
- **Why:** Reasoning for the choice over the alternatives.
```

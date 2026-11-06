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

## D-006 — Correction to D-005 item 5: the `users` table does exist

- **Date:** 2026-11-06
- **Step:** 0
- **Context:** D-005 listed "no `users` table" as a blocker. That was wrong.
  `backend/app/infrastructure/database.py::init_pool` creates `users`, `tickets` and
  `feedback` when the app starts. I had only searched the SQL files.
- **Decision:** Supersede D-005 item 5. No fix is needed. Verified: register and login
  work against a fresh database.
- **Alternatives considered:** None. This is a factual correction.
- **Why:** The rule is to never edit past entries.

---

## D-007 — Owner approved the fixes; two more blockers found and fixed

- **Date:** 2026-11-06
- **Step:** 0
- **Context:** The owner replied "yes to fixes" to D-005, then asked me to "work all the
  changes around" the API key, which they will add manually. While applying the fixes
  I found two more blockers (items 4 and 5 below). Given that instruction I fixed them
  rather than stopping again, and I'm reporting them here.
- **Decision:** These one-line changes:
  1. `backend/pyproject.toml`: add `email-validator>=2.0.0`, which `EmailStr` needs
     (D-005 item 2).
  2. `backend/app/services/auth_service.py`: `from jose import JWTError` becomes
     `from jwt import PyJWTError as JWTError` (D-005 item 3).
  3. `backend/app/api/v1_query.py`: import `check_cache`/`store_cache` from the
     existing `app.retrieval.semantic_cache` instead of the missing
     `app.infrastructure.redis_cache` (D-005 item 4).
  4. **New.** `backend/app/retrieval/hybrid_search.py`: import `RetrievedChunk` from
     `app.domain.rag` instead of `app.shared.models`. The two are duplicate classes,
     and Pydantic v2 rejected the shared one inside `domain.rag.QueryResponse`
     ("Input should be a valid dictionary or instance of RetrievedChunk"), so every
     query that returned chunks would have failed with a 500. Reproduced in isolation
     before the fix.
  5. **New.** `backend/pyproject.toml`: add `bcrypt<5`. With bcrypt 5.0.0,
     passlib 1.7.4 raises `ValueError: password cannot be longer than 72 bytes` on
     every hash, so registration fails. This is an upper-bound pin, not an upgrade.
- **Alternatives considered:**
  - For (2): add a `python-jose` dependency. Rejected: the tokens are created by
    PyJWT (`app/core/security.py`), so `jose.JWTError` would never catch their
    errors, and bad tokens would give 500 instead of 401.
  - For (4): change every `app.shared.models` import. Rejected as a larger change than
    needed; only the hybrid-search path feeds the response.
  - For (5): replace passlib. Rejected as a refactor.
- **Why:** These are the smallest changes that let the documented flow
  (register, log in, query) run.

---

## D-008 — Free provider: Gemini (Google AI Studio) instead of OpenAI

- **Date:** 2026-11-06
- **Step:** 0
- **Context:** The owner wants free models. The code calls OpenAI (embeddings and chat)
  through the `openai` SDK and Gemini through `google-generativeai`.
- **Decision:** Use one free AI Studio key for both, configured only through
  environment variables, plus one code line:
  - `OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/`, read
    natively by the `openai` SDK and passed into the container by compose `env_file`.
    Set `OPENAI_API_KEY` and `GEMINI_API_KEY` to the same AI Studio key.
  - `EMBEDDING_MODEL=gemini-embedding-001`.
  - `gemini-2.5-flash-lite` for LLM, grader, router, extractor and vision.
  - Code: `backend/app/ingestion/embedder.py` passes `dimensions=1536` to
    `embeddings.create`. `gemini-embedding-001` defaults to 3072 dimensions, but the
    table is `vector(1536)` and pgvector HNSW indexes cap at 2000. OpenAI
    `text-embedding-3-small` accepts the same parameter, so switching back still works.
  - Documented as an active block at the end of `.env.example`. The original OpenAI
    and Gemini-3 model lines are left in place, commented out, above it.
- **Alternatives considered:**
  - Local Ollama: rejected. Gemini nodes use the Google SDK and can't be redirected
    without code changes, and CPU inference is slow.
  - Groq or OpenRouter: rejected. No free embeddings, and the Gemini nodes would still
    need a key.
  - `gemini-2.5-flash`: rejected. It "thinks" by default, and thinking tokens count
    against the grader's `max_output_tokens=5`, which would give empty grades. Every
    chunk would then be graded "no".
  - Changing the vector column dimension: rejected. That means schema, cache and
    zero-vector changes in several files.
- **Why:** Zero cost, one key, and a minimal code footprint.
- **Not verified:** No key is available in this session, so I haven't confirmed that
  Google's OpenAI-compatible endpoint honours `dimensions`, or that these model names
  are still served. Check model names with
  `curl -H "x-goog-api-key: $KEY" https://generativelanguage.googleapis.com/v1beta/models`.
  Free-tier rate limits may cause grading failures, which count as "irrelevant".

---

## D-009 — Step 0 verification: what was and wasn't checked

- **Date:** 2026-11-06
- **Step:** 0
- **Context:** In this cloud sandbox, Docker builds have no network (D-005 item 1), so
  `docker compose up --build` can't build the backend image here. On a normal machine
  it can.
- **Decision:** For verification only, I ran `db`, `neo4j` and `redis` through
  `docker compose up -d db neo4j redis`, and ran the backend on the host with the
  project's own dependencies, using `PYTHONPATH=.:../packages` to mirror the
  container's `/app:/packages`. No repo file was changed for this.
- **Results:**
  - Startup works: Postgres pool, Neo4j driver and Redis cache index all initialise.
  - `/health` and `/health/vector` are healthy.
  - `/v1/auth/register` and `/login` work. A bad token returns 401.
  - `/v1/query` reaches the embedding step and fails there because `tiktoken` can't
    download `cl100k_base` (the sandbox proxy blocks `openaipublic.blob.core.windows.net`).
    That's sandbox-only. With no real key, the next call would fail anyway.
- **Alternatives considered:** Rewriting the Dockerfile to work offline. Rejected as
  out of scope.
- **Why:** This verifies everything except steps that need a live LLM key.
- **Owner action:** Run `docker compose up --build` with real keys in `backend/.env`
  (see `.env.example`).

---

## D-010 — Task 1: corpus layout and file selection

- **Date:** 2026-11-06
- **Step:** 1
- **Context:** D-002 chose the FastAPI tutorial docs. The pipeline stores chunks with
  `source` = the file's *basename*, and delta sync purges by `source`. Files with the
  same basename (`tutorial/index.md`, `tutorial/security/index.md`, ...) would
  therefore overwrite each other.
- **Decision:** `corpus/` holds the 39 top-level `docs/en/docs/tutorial/*.md` files from
  fastapi commit `1ca09c1`, unchanged. I excluded `index.md` (a navigation page) and the
  `dependencies/` and `security/` subfolders (they have colliding basenames). Provenance
  and the MIT licence are in `corpus/SOURCE.txt` and `corpus/LICENSE-fastapi.txt`. Those
  are `.txt` so the `*.md` ingest loop skips them; the endpoint would also reject `.txt`.
- **Alternatives considered:** Include the subfolders, renamed with a prefix. Rejected:
  that modifies the source, and 39 files already falls within the 10–40 range.
- **Why:** Unique filenames give an unambiguous `expected_source` for the eval.
- **Known limitation:** The pages reference code examples with MkDocs include markers
  (`{* ../../docs_src/... *}`), and those files aren't copied, so example code isn't
  in the corpus.

---

## D-011 — Task 1: bundled sample data

- **Date:** 2026-11-06
- **Step:** 1
- **Context:** The instructions say to disable or move bundled sample data so only the
  corpus is queried.
- **Decision:** Nothing to move. `db/init.sql` seeds no documents, and no code path
  auto-ingests files. `backend/evaluation/golden_queries.json` and
  `backend/mock_server.py` mention sample filenames but put nothing into the store.
  I left them untouched; moving them would be a rename, which the rules forbid.
  The only searchable store is `document_chunks` in a fresh Postgres volume, which
  will hold only `corpus/*.md`. Verified empty here (`SELECT count(*)` = 0).
- **Caveats (not changed; would be a behaviour change):**
  - The Gemini router can send a question to `sql_agent` ("analytical") or
    `summarize_document` ("summarization"). Both answer from the LLM's own knowledge
    with **no retrieval**. Such answers come back with empty `chunks`, and the eval
    will show them as retrieval misses.
  - Anyone who previously ran the stack has a `pgdata` volume that may hold old chunks.
    Run `docker compose down -v` first to start from an empty store.
- **Alternatives considered:** Force the router to "document". Rejected as a feature
  change; I'm flagging it for the owner instead.
- **Why:** The rules say do no refactoring and add no features.

---

## D-012 — Task 1: ingest command and manual verification (NOT RUN, needs key)

- **Date:** 2026-11-06
- **Step:** 1
- **Context:** I used only the existing `POST /v1/ingest` path (no auth needed). It tries
  ARQ first; because `worker.py` imports the missing `app.config`, it always falls back
  to synchronous in-request ingestion (verified in the logs). No worker service exists
  in compose anyway.
- **Decision:** Ingest with a shell loop over the API. This is not a new pipeline:
  ```bash
  for f in corpus/*.md; do curl -s -F "file=@$f" -F access_level=public http://localhost:8000/v1/ingest; echo; done
  ```
  Check every line shows `"chunks_created"` > 0. If embedding fails, the endpoint
  still returns HTTP 200 with `chunks_created: 0`.
- **Verified here (no key):** `path-params.md` loaded, then (with semantic splitting
  unavailable, as in the container) fell back to character chunking: 21 chunks, all
  validated. It then stopped at embedding, as expected without a key or `tiktoken`
  download access. Nothing was stored.
- **Three manual queries (pending, owner to run once the key is set):**

  | # | Query | Expected source | Expected in answer | Outcome |
  |---|---|---|---|---|
  | 1 | How do you declare a path parameter with a type in FastAPI? | path-params.md | `item_id: int` style type hints / conversion | NOT RUN — no API key in session |
  | 2 | How do I enable CORS in a FastAPI app? | cors.md | `CORSMiddleware`, `allow_origins` | NOT RUN — no API key in session |
  | 3 | How can I run a background task after returning a response? | background-tasks.md | `BackgroundTasks`, `add_task` | NOT RUN — no API key in session |

  Command, after logging in:
  `curl -s -X POST localhost:8000/v1/query -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"query":"...","access_level":"public"}'`
- **Alternatives considered:** Fake the outcomes. Rejected.
- **Why:** The owner chose to add the key manually.

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

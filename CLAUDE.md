# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Layout

JCodeQuest is a monorepo of four Python packages plus a Vite/React frontend, all sharing one Supabase PostgreSQL DB.

- `shared/` — `jcq-shared` package: Pydantic schemas (`Problem`, `IntentRubric`, `TestCase`) used by backend, authoring engine, and judge engine.
- `backend/` — FastAPI API server (default :8000). Routers under `src/api/` (wired in `main.py`): `auth`, `me`, `grading`, `tutor`, `problems`, `submissions`, `leaderboard`, `notices`, `reports`, `internal`. ORM rows in `src/storage/models.py`. The HTTP client to the judge engine lives in `src/judge/client.py`.
- `judge_engine/` — Separate FastAPI service (default :8002) that owns grading execution. Contains the in-process job queue, the pure-Python sandbox (`judge/sandbox/`), the three-judge LLM ensemble (`judge/ensemble.py`), webhook callback into backend (`judge/callback.py`), and its own admin routers (`judge/routers/{stats,submissions,users}`).
- `authoring_engine/` — LangGraph pipeline that produces variant problems from an existing one and writes them back to the same DB. CLI (`authoring/main.py`) and FastAPI viewer (`authoring/server.py`, default :8001). Imports `backend/src/storage` directly via `sys.path` injection in `config.ensure_backend_on_path()`.
- `frontend/` — Vite + React + TypeScript SPA. `npm run dev` for local dev (default :5173), `npm run build` for production. Uses `@supabase/supabase-js` for auth and Monaco editor for code input.
- `admin_dashboard/` — Static admin page (`index.html` + `Dockerfile`) shipped as its own container.
- `docker-compose.yml` — Container entry point for the full stack.
- `scripts/verify_all.py` — integration smoke runner that spawns backend + judge_engine + authoring and exercises the end-to-end flow.

`shared`, `backend`, `authoring_engine`, and `judge_engine` install `jcq-shared` via `file:../shared` — installing any of them pulls the shared package in editable mode automatically.

## Core Architecture

**Three services, one DB.** `backend` (:8000), `authoring_engine` (:8001), and `judge_engine` (:8002) all read/write the same Supabase PostgreSQL database via `JCQ_DB_URL`. Both authoring_engine and judge_engine reuse `backend/src/storage` rather than maintaining their own ORM (`authoring/config.py:ensure_backend_on_path()` and the equivalent in judge_engine). `JCQ_DB_URL` must be a valid `postgresql://` connection string pointing at the Supabase project (use the Transaction Pooler URL from the Supabase dashboard for best compatibility).

**Module-load env reads.** `backend/src/storage/db.py` reads `JCQ_DB_URL` at module import. Anything that imports `src.*` before `JCQ_DB_URL` is set will get the wrong engine. The CLI entry points and `main.py` files call `load_dotenv(...)` or `ensure_backend_on_path()` *before* the first `src.*` import — preserve that ordering when editing them.

**Grading pipeline (cross-service)**:
1. `POST /grade` on backend persists the submission, then `backend/src/judge/client.py:submit_to_engine` does an HTTP POST to `JCQ_JUDGE_URL` (default `http://127.0.0.1:8002`) and returns immediately.
2. judge_engine queues the job in its own asyncio worker pool (concurrency = `JCQ_QUEUE_CONCURRENCY`) and runs `judge/sandbox/runner.py:run_all_tests` — pure-Python isolation that blocks `socket`/`subprocess`/`ctypes` etc.; not a real syscall sandbox.
3. If all tests pass, judge_engine calls `judge/ensemble.py:vote` — three Ollama models (Melchior/Balthasar/Casper) cast AC/SUS votes; ≥2/3 AC ⇒ AC. Skipped when `JCQ_SKIP_ENSEMBLE=1`.
4. judge_engine POSTs the verdict to backend's `/internal/grade-events` webhook. Both sides authenticate the webhook with a shared `JCQ_INTERNAL_SECRET`. backend's `apply_grading_event` writes verdict + per-test results + ensemble votes; first-time AC adds `points * efficiency_multiplier` to the user's `exp`.
5. Clients track progress via SSE at `GET /grade/{id}/events` on backend — subscribe *before* reading snapshot to avoid missing events (see `api/grading.py:stream_grade_events`).

**Authoring pipeline** (`authoring_engine/authoring/pipeline/`): LangGraph DAG `fetch_problem → retrieve_exemplars → generate_variants → verify_candidates → judge_candidates → solve_candidates → attack_candidates → compare_to_original → persist_approved` (`pipeline/graph.py`). `generate_variants` makes two sequential ChatOllama calls per variant (draft_problem then author_solution); LangGraph auto-traces each node and LLM call to LangSmith when `LANGSMITH_API_KEY` is set (project `jcq-authoring`, see `main.py:_setup_langsmith`). Approved variants are inserted with `parent_id` pointing at the source problem and `langsmith_trace_id` for trace lookup (queryable via `/api/spans/{trace_id}`).

**Auth**: Supabase Auth handles Google OAuth entirely on the frontend (`supabase.auth.signInWithOAuth`). The backend validates Supabase-issued Bearer JWTs (ES256/RS256 via JWKS, HS256 via shared secret for legacy projects) in `src/auth/supabase_jwt.py`. On success, `get_or_create_user` upserts a `UserRow` keyed on `(provider="supabase", external_id=sub)`. `POST /auth/dev-login` is a dev-only stub (active when `JCQ_AUTH_ALLOW_DEV_STUB=1`) that issues a `jcq_session` cookie backed by `SessionRow` — never enable in prod.

## Commands

The backend does **not** load `.env` automatically — every shell that runs the server, scripts, or tests must `source backend/env.sh` first (see `docs/environment.md`). Tests are an exception: `tests/conftest.py` substitutes a temporary SQLite DB.

```bash
# 전체 개발 환경 한번에 (권장)
scripts/dev.sh up                               # judge(:8002) → backend(:8000) → authoring(:8001) → frontend(:5173) 순서로 기동
scripts/dev.sh up --no-authoring               # 출제 엔진 제외
scripts/dev.sh up --no-llm                     # Ollama 앙상블 스킵 (JCQ_SKIP_ENSEMBLE=1 judge에 주입)
scripts/dev.sh up --no-authoring --no-llm      # 둘 다
scripts/dev.sh down                            # 전체 종료
scripts/dev.sh status                          # 상태 확인
scripts/dev.sh logs <backend|authoring|judge|frontend>
scripts/dev.sh restart [--no-authoring] [--no-llm]  # down → up

# 개별 기동
cd frontend && npm run dev              # http://localhost:5173
cd frontend && npm run build            # production build → dist/

# Backend (source env.sh 필수)
source backend/env.sh
.venv/bin/uvicorn src.main:app --reload         # http://localhost:8000

# Backend tests (no external deps — tests use a temp SQLite DB for isolation)
cd backend && .venv/bin/pytest -q
.venv/bin/pytest tests/test_pipeline.py         # single file
.venv/bin/pytest -k cooldown                    # keyword
JCQ_RUN_LIVE_LLM=1 .venv/bin/pytest tests/live  # live Ollama/OpenAI (gated)

# Authoring engine — CLI variant generator
cd authoring_engine && python -m authoring.main --problem-id 1 --count 5

# Authoring engine — viewer server
cd authoring_engine && uvicorn authoring.server:app --port 8001

# Full E2E verify (spawns both servers + runs flow)
scripts/verify_all.sh                  # sandbox-only path
scripts/verify_all.sh --with-llm       # adds /tutor + ensemble AC path
scripts/verify_all.sh --external       # attach to already-running servers

# Smoke against a live uvicorn (two terminals; same env.sh sourced in both)
python backend/tests/scripts/smoke_e2e.py
```

## Conventions That Will Bite You

- **Patch the callsite, not the source.** Integration tests monkeypatch LLM calls on the importing module (`src.tutor.client.<x>`, judge_engine's importer of `vote`), never on the defining module. See `docs/testing.md` and existing `test_pipeline.py`.
- **Tests use SQLite, production uses PostgreSQL.** `tests/conftest.py` substitutes a temporary SQLite DB so tests run without a Supabase connection. Don't add PostgreSQL-specific SQL to the ORM layer without a SQLite fallback, or gate it behind an env flag.
- **`JCQ_ALLOW_NON_POSTGRES=1` is required for non-Postgres URLs.** `backend/src/storage/db.py` raises `RuntimeError` at module load if `JCQ_DB_URL` is not `postgresql://...` unless this escape hatch is set. The reason: `storage/vault.py` falls back to plaintext secret storage on non-Postgres backends (test-only path), so booting prod with SQLite would silently expose user API keys. `tests/conftest.py`, `scripts/verify_all.py`, and `scripts/dump_openapi.py` already set this flag — any new entry point that points at SQLite must do the same.
- **422 responses auto-redact sensitive fields.** `main.py`'s `RequestValidationError` handler replaces the `input` of fields named `api_key`, `password`, `secret`, or `token` with `[REDACTED]` before the body hits the response or access log. When adding a new sensitive request field, register its name in `_SENSITIVE_FIELDS` in `main.py`.
- **`schemas._API_KEY_PATTERN` and frontend `API_KEY_PATTERN` must stay in sync.** The same regex (`^[!-~]{20,512}$`) lives in `backend/src/schemas.py` and `frontend/src/components/ApiKeyGuideModal.tsx`. Loosening or tightening one without the other produces a UX/server mismatch (frontend passes, backend 422s — or vice versa).
- **`backend/env.sh` is gitignored** — `.env.example` is the template. `frontend/.env` is also gitignored — `.env.example` is the template. Never commit secrets; rotate immediately if leaked.
- **`MAX_CODE_LENGTH = 64 * 1024`** in `schemas.py` caps `GradeRequest.code`. The sandbox also caps stdout/stderr at 64 KB each.
- **Sandbox is not adversarial-grade.** `_WRAPPER` in `judge_engine/judge/sandbox/runner.py` blocks `socket`, `subprocess`, `ctypes`, etc. at the Python import layer plus RLIMITs. It is not seccomp/namespace isolation — anything that needs real isolation must layer that on.
- **Submission cooldown** defaults to 10s per (user, problem); tests force it to 0 via `_disable_cooldown` (autouse). Tests that exercise cooldown re-enable it locally.
- **Three-judge ensemble** (`judge_engine/judge/ensemble.py`) uses three Ollama models — Melchior/Balthasar/Casper — each overridable via `JCQ_ENSEMBLE_MODEL_{MELCHIOR,BALTHASAR,CASPER}`. Code defaults are `qwen2.5-coder:14b-instruct-q5_K_M`, `deepseek-coder-v2:lite`, `llama3.1:8b`. See `docs/setup-ollama.md` for setup; missing models fail at first call, not startup.
- **Problem variants** are linked by `ProblemRow.parent_id` (self-FK) — the authoring engine sets this on persist. Existing manual problems have `parent_id IS NULL`. Don't break this when adding queries.
- **Novelty gate lives inside `generate_variants`, not as its own node.** Each variant runs draft → embedding novelty check (vs same-category siblings + already-accepted batch variants) → redraft with overlap feedback up to `JCQ_NOVELTY_MAX_RETRIES` → only a passing draft gets `author_solution`. Gated by `JCQ_NOVELTY_ENABLED` (default on) and **fail-open**: any embedding/HTTP error counts as novel so the pipeline never stalls. Embeddings use `JCQ_EMBED_MODEL` (default `bge-m3`, must be `ollama pull`ed) via `authoring/embeddings.py`; similarity is plain-Python cosine over JSON vectors (no pgvector). Backend stores them in `ProblemRow.embedding` and serves `/internal/problems/{id}/category-embeddings`.
- **RAG exemplar retrieval is the *same* embeddings used in reverse.** `retrieve_exemplars` (`pipeline/nodes/retrieve.py`) reuses category embeddings to *pull in* "related-but-diverse" approved siblings as grounding for `generate_variants` — the opposite direction of the novelty gate's "push away". Top-k via **MMR** (`embeddings.py:mmr_select`, λ balances relevance vs diversity), filtered by level window + `judge_score`, then only the picks get full `IntentRubric` hydrated (compressed rubric, not full statement → small-model context). Injected into `DRAFT_USER` as `reference_block`; **empty corpus / embed failure fail-open to the seed block** (current behavior). Gated by `JCQ_RAG_ENABLED` (default on), tuned by `JCQ_RAG_{TOP_K,MMR_LAMBDA,LEVEL_WINDOW,MIN_JUDGE_SCORE}`. Critical: keep λ ≤ 0.5 — high λ pulls near-duplicates the draft copies, which then trip the novelty gate. Design: `docs/rag-authoring-plan.md`.
- **Persist is gated on THREE flags AND-ed, not just `solver_passed`.** `persist_approved` saves a variant only if `solver_passed AND discrimination_passed AND compare_passed`. The two newer flags are read with `.get(..., True)` defaults, so disabling their node/gate (or running an older candidate dict) keeps the legacy "solver-only" behavior — don't change those defaults to `False` or you'll silently drop everything when a gate is off. Each flag is set by a distinct node (`solve_candidates` / `attack_candidates` / `compare_to_original`); `authoring_meta` records all three plus their rationale for the viewer.
- **Test-set discrimination gate (`attack_candidates`).** Runs *after* `solve_candidates` (only attacks solvable candidates). An LLM writes **deliberately-flawed** solutions targeting the rubric (`naive` ignores `expected_complexity` to bait TLE; `edge_skip` mishandles `must_handle`) and runs them against *all* `test_cases` — a strong test set must REJECT them. `discrimination_passed` = at least `JCQ_DISCRIMINATION_MIN_REJECT` (default 1) of `JCQ_DISCRIMINATION_ATTACKS` (default 2) attacks got non-AC; 0 rejected ⇒ tests catch nothing ⇒ discarded. **Fail-open**: if every attack LLM call errors (no valid probe), it passes with `discrimination_score=None`. Gated by `JCQ_DISCRIMINATION_ENABLED` (default on); uses the Melchior model alone (not the 3-judge ensemble).
- **Quality judge aggregates by MEDIAN, not mean.** `judge_candidates` keeps the 2/3-pass rule but `judge_score` is now the **median** of the per-judge scores (robust to one judge's outlier/0-on-error); per-judge scores are kept in `judge_scores`. The `JUDGE_QUALITY_SYSTEM` prompt carries explicit score-band anchors + good/bad few-shot examples to calibrate small models. Optional self-consistency: `JCQ_JUDGE_SAMPLES` > 1 samples each judge N times at `JCQ_JUDGE_SELFCONSIST_TEMP` (default 0.3) then takes per-judge majority/median (default 1 = off, since it costs N× calls).
- **`compare_to_original` is now a GATE, not pure recording.** It still records 3 axes, but `hallucination_score > JCQ_COMPARE_MAX_HALLUCINATION` (default 0.5) or `intent_similarity < JCQ_COMPARE_MIN_INTENT_SIM` (default 0.4) now sets `compare_passed=False` and blocks persist (`difficulty_similarity` stays recording-only — variants may legitimately shift difficulty). It's still a **single** judge (Melchior), so it's **fail-open**: any LLM/parse error ⇒ `compare_passed=True` (don't discard a candidate that already cleared the 3-judge quality + solver + discrimination gates on one noisy call). Toggle with `JCQ_COMPARE_GATE_ENABLED`.
- **`ProblemRow.embedding` needs a manual `ALTER TABLE` on live Postgres.** It's a nullable JSON column (SQLite/Postgres-portable), but `init_db()`'s `create_all` never adds columns to existing tables — run `ALTER TABLE problem ADD COLUMN embedding JSONB;` once on Supabase, then backfill existing rows with `python -m authoring.scripts.backfill_embeddings`. Rows with `NULL` embedding are skipped by the novelty check (fail-open), so the gate is a no-op until backfilled.

## Reference Docs

- `docs/environment.md` — env vars (required/optional/test-only) and the `env.sh` pattern.
- `docs/testing.md` — test tiers (unit/integration/live/smoke), isolation, LLM mocking rules.
- `docs/problem-format.md` — `Problem` schema authoring guide (4-axis IntentRubric).
- `docs/authoring-prompt.md` — LLM prompt spec for `draft_problem` / `author_solution`.
- `docs/setup-ollama.md` — Ollama model setup for the judge ensemble.

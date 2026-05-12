# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Layout

JCodeQuest is a monorepo of three Python packages plus a single static frontend, all sharing one SQLite DB.

- `shared/` — `jcq-shared` package: Pydantic schemas (`Problem`, `IntentRubric`, `TestCase`) used by both backend and authoring engine.
- `backend/` — FastAPI grading server. Routers under `src/api/` (`/auth`, `/me`, `/problems`, `/grade`, `/tutor`); ORM rows in `src/storage/models.py`; sandbox + LLM ensemble in `src/judge/`.
- `authoring_engine/` — LangGraph pipeline that produces variant problems from an existing one and writes them back to the same DB. CLI (`authoring/main.py`) and FastAPI viewer (`authoring/server.py`). Imports `backend/src/storage` directly via `sys.path` injection in `config.ensure_backend_on_path()`.
- `frontend/index.html` — single self-contained HTML page (no build step).
- `scripts/verify_all.py` — integration smoke runner that spawns both servers and exercises the end-to-end flow.

`shared` and `authoring_engine` install `jcq-shared` via `file:../shared` — installing the backend or authoring engine pulls the shared package in editable mode automatically.

## Core Architecture

**Two servers, one DB.** Both `backend` (FastAPI, default :8000) and `authoring_engine` (FastAPI, separate port) read/write the same SQLite file at `JCQ_DB_URL`. The authoring engine reuses `backend/src/storage` rather than maintaining its own ORM — see `authoring/config.py:ensure_backend_on_path()`. **JCQ_DB_URL must be an absolute path**; the default `sqlite:///./data/jcq.db` is CWD-relative and will silently create a second DB if you run scripts from a different directory.

**Module-load env reads.** `backend/src/storage/db.py` reads `JCQ_DB_URL` at module import. Anything that imports `src.*` before `JCQ_DB_URL` is set will get the wrong engine. The CLI entry points and `main.py` files call `load_dotenv(...)` or `ensure_backend_on_path()` *before* the first `src.*` import — preserve that ordering when editing them.

**Grading pipeline** (`backend/src/judge/`):
1. `POST /grade` enqueues a submission via `judge.jobs.JobQueue` (asyncio worker pool, concurrency = `JCQ_QUEUE_CONCURRENCY`).
2. `judge.jobs.grading.grade_submission`: runs `sandbox.run_all_tests` (pure-Python isolation wrapper in `sandbox/runner.py` — blocks `socket`/`subprocess`/`ctypes` etc.; not a real syscall sandbox).
3. If all tests pass, calls `judge.ensemble.vote` — three Ollama models (Melchior/Balthasar/Casper) cast AC/SUS votes; ≥2/3 AC ⇒ AC.
4. `save_grading` writes verdict + per-test results + ensemble votes; first-time AC adds `points * efficiency_multiplier` to the user's `exp`.
5. Clients track progress via SSE at `GET /grade/{id}/events` — subscribe *before* reading snapshot to avoid missing events (see `api/grading.py:stream_grade_events`).

**Authoring pipeline** (`authoring_engine/authoring/pipeline/`): LangGraph DAG `fetch_problem → generate_variants → verify_candidates → judge_candidates → solve_candidates → persist_approved`. Approved variants are inserted with `parent_id` pointing at the source problem and `langsmith_trace_id` for trace lookup.

**Auth**: Google OAuth via Authlib. `SessionMiddleware` (Starlette) is only for the OAuth handshake's state/nonce — real user sessions are server-side rows (`SessionRow`) with opaque tokens in the `jcq_session` cookie. Logout deletes the row immediately. `JCQ_AUTH_ALLOWED_HD` (default `jbnu.ac.kr`) gates by Google Workspace domain. `POST /auth/dev-login` only registers when `JCQ_AUTH_ALLOW_DEV_STUB=1` — never enable in prod.

## Commands

The backend does **not** load `.env` automatically — every shell that runs the server, scripts, or tests must `source backend/env.sh` first (see `docs/environment.md`). Tests are an exception: `tests/conftest.py` substitutes a temporary SQLite DB.

```bash
# Backend
source backend/env.sh
.venv/bin/uvicorn src.main:app --reload         # run from backend/

# Backend tests (no external deps)
cd backend && .venv/bin/pytest -q
.venv/bin/pytest tests/test_pipeline.py         # single file
.venv/bin/pytest -k cooldown                    # keyword
JCQ_RUN_LIVE_LLM=1 .venv/bin/pytest tests/live  # live Ollama/OpenAI (gated)

# SQLite schema migration (additive ALTERs)
cd backend && python migrate.py

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

- **Patch the callsite, not the source.** Integration tests monkeypatch LLM calls on the importing module (`src.judge.jobs.grading.vote`, `src.tutor.client.<x>`), never on the defining module. See `docs/testing.md` and existing `test_pipeline.py`.
- **`backend/env.sh` is gitignored** — `.env.example` is the template. Same for `authoring_engine/.env`. Never commit secrets; rotate immediately if leaked.
- **`MAX_CODE_LENGTH = 64 * 1024`** in `schemas.py` caps `GradeRequest.code`. The sandbox also caps stdout/stderr at 64 KB each.
- **Sandbox is not adversarial-grade.** `_WRAPPER` in `judge/sandbox/runner.py` blocks `socket`, `subprocess`, `ctypes`, etc. at the Python import layer plus RLIMITs. It is not seccomp/namespace isolation — anything that needs real isolation must layer that on.
- **Submission cooldown** defaults to 10s per (user, problem); tests force it to 0 via `_disable_cooldown` (autouse). Tests that exercise cooldown re-enable it locally.
- **Three-judge ensemble** (`judge/ensemble.py`) requires three specific Ollama tags (`qwen2.5-coder:14b-instruct-q5_K_M`, `deepseek-coder-v2:lite`, `llama3.1:8b`). See `docs/setup-ollama.md` for setup; missing models will fail at first call, not startup.
- **Problem variants** are linked by `ProblemRow.parent_id` (self-FK) — the authoring engine sets this on persist. Existing manual problems have `parent_id IS NULL`. Don't break this when adding queries.

## Reference Docs

- `docs/environment.md` — env vars (required/optional/test-only) and the `env.sh` pattern.
- `docs/testing.md` — test tiers (unit/integration/live/smoke), isolation, LLM mocking rules.
- `docs/problem-format.md` — `Problem` schema authoring guide (4-axis IntentRubric).
- `docs/authoring-prompt.md` — LLM prompt spec for `draft_problem` / `author_solution`.
- `docs/setup-ollama.md` — Ollama model setup for the judge ensemble.

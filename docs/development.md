# Development Guide

Compose 없이 호스트에서 4종 프로세스를 직접 띄워 코드를 수정하면서 개발하는 흐름. 통합 실행만 필요하면 README의 **Run with Docker Compose**로 충분하다.

## 사전 조건

- Python 3.12+, Node 20+
- Supabase 프로젝트 (PostgreSQL + Auth) — 외부 DB
- Ollama 인스턴스 + 3개 판사 모델 (`docs/setup-ollama.md`). 없으면 `--no-llm` 사용.

## 최초 1회 — `scripts/setup.sh`

backend / judge / authoring 각각의 venv, `jcq-shared`의 editable install, 프런트엔드 `npm ci`, `.env` 템플릿 복사까지 수행.

```bash
scripts/setup.sh             # 전체
scripts/setup.sh --no-venv   # venv 재사용, 의존성만 재설치
scripts/setup.sh --force-env # 기존 .env를 .env.example로 덮어쓰기
```

`JCQ_DB_URL`이 `postgresql://`이면 `setup.sh`/`dev.sh` 모두 `backend/migrate.py`(SQLite 한정 ALTER 스크립트)를 자동 스킵한다.

## 기동 — `scripts/dev.sh`

```bash
scripts/dev.sh up                            # judge → backend → authoring → frontend
scripts/dev.sh up --no-authoring             # 출제 엔진 제외 (가벼운 dev)
scripts/dev.sh up --no-llm                   # JCQ_SKIP_ENSEMBLE=1 주입 (Ollama 없이)
scripts/dev.sh up --no-authoring --no-llm
scripts/dev.sh status                        # PID / 포트 / health
scripts/dev.sh logs <backend|authoring|judge|frontend>
scripts/dev.sh restart [--no-authoring] [--no-llm]
scripts/dev.sh down
```

PID/로그는 `.dev-logs/` 아래. 포트 충돌이면 `down` 후 재시도.

| 서비스 | 포트 | 헬스 | 비고 |
|--------|------|------|------|
| backend | 8000 | `/health` | `JCQ_AUTH_ALLOW_DEV_STUB=1`이면 `POST /auth/dev-login` 활성 |
| judge | 8002 | `/api/health` | 채점 워커 (sandbox + 3-LLM 앙상블) |
| authoring | 8001 | `/api/health` | 원본/변형 조회 + 출제 파이프라인 |
| frontend | 5173 | `/` | Vite dev server (`npm run dev`) |

## 환경 변수 핵심 키

서비스별 템플릿은 각 디렉토리의 `.env.example`. 의미·전체 목록은 `docs/environment.md`. 여기엔 dev 흐름에 직결되는 키만 정리.

- **`JCQ_DB_URL`** — Supabase Transaction Pooler URL. backend·authoring 둘 다 동일 값(authoring은 dev 모드에서만 DB 직접 접근하는 경로가 있음 — Docker 환경에서는 backend HTTP로 위임).
- **`SUPABASE_URL`** — JWT JWKS 검증용 Project URL. ES256/RS256 신규 프로젝트는 이거 하나로 충분, 레거시 HS256은 `SUPABASE_JWT_SECRET` 추가.
- **`JCQ_INTERNAL_SECRET`** — backend ↔ judge webhook 인증. 양 서비스 같은 값.
- **`VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY`** — 프런트가 Supabase Auth와 직접 통신. Vite는 빌드 타임에 인라인하므로 prod 빌드 시 값 변경하면 재빌드 필요.
- **`OLLAMA_BASE_URL`** — 3-judge ensemble + 출제 LLM 호스트.
- **`OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL`** — 튜터 (`/tutor`) 엔드포인트용. OpenAI 호환 게이트웨이 사용 가능.

### 개발 편의 플래그 (운영 금지)

- `JCQ_AUTH_ALLOW_DEV_STUB=1` — `POST /auth/dev-login` 라우트 활성. Bearer JWT 없이 쿠키 세션 발급.
- `JCQ_COOKIE_INSECURE=1` — HTTP 로컬에서 Secure 쿠키 비활성.
- `JCQ_SKIP_ENSEMBLE=1` — judge가 3-LLM 앙상블을 스킵하고 stub AC 반환. 샌드박스 채점은 정상.

## 테스트

```bash
cd backend && .venv/bin/pytest -q                # 단위 + 통합 (임시 SQLite 격리)
.venv/bin/pytest tests/test_pipeline.py          # 단일 파일
.venv/bin/pytest -k cooldown                     # 키워드
JCQ_RUN_LIVE_LLM=1 .venv/bin/pytest tests/live   # 라이브 Ollama/OpenAI (게이팅)
```

테스트 계층·격리·LLM mocking 규약은 `docs/testing.md`.

## E2E Smoke

```bash
scripts/verify_all.sh                # sandbox-only 경로
scripts/verify_all.sh --with-llm     # /tutor + 앙상블 AC 경로
scripts/verify_all.sh --external     # 이미 떠 있는 서버에 붙음
```

## OpenAPI 정적 명세 갱신

`scripts/dump_openapi.py`가 FastAPI `app.openapi()`를 직접 호출 — 서버 미기동.

```bash
backend/.venv/bin/python           scripts/dump_openapi.py backend
authoring_engine/.venv/bin/python  scripts/dump_openapi.py authoring
```

라우터/스키마를 바꾼 PR에선 두 JSON(`docs/openapi-*.json`)을 같이 갱신하는 게 관행.

## 코드 컨벤션 함정 (CLAUDE.md 요약)

- **Callsite patch.** 테스트는 LLM 호출을 import한 모듈에 monkeypatch (`src.judge.jobs.grading.vote`), 정의 모듈이 아님.
- **테스트는 SQLite, 운영은 PostgreSQL.** `tests/conftest.py`가 임시 SQLite로 갈아끼움 — PostgreSQL 한정 SQL을 ORM에 넣을 땐 SQLite fallback 또는 env 게이팅 필요.
- **샌드박스는 adversarial-grade 아님.** `judge/sandbox/runner.py`는 import 레이어 차단 + RLIMIT만. 진짜 격리는 별도 레이어.
- **제출 쿨다운** 기본 10s/(user, problem). 테스트는 `_disable_cooldown` autouse fixture로 0으로.
- **3-judge ensemble**은 세 Ollama 태그(`qwen2.5-coder:14b-instruct-q5_K_M`, `deepseek-coder-v2:lite`, `llama3.1:8b`) 필요. 미설치 모델은 startup이 아니라 첫 호출에서 깨짐.
- **Problem variants**는 `ProblemRow.parent_id` 자기참조 FK. 출제 엔진이 persist 시 설정. 수동 문제는 NULL.

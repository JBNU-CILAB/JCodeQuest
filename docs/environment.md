# Environment Setup

JCodeQuest 백엔드는 환경변수를 **자동 로드하지 않는다** — `dotenv` 같은 모듈은 쓰지 않고, 코드는 `os.getenv()`로만 읽는다. 따라서 호출자가 셸에 변수를 export한 뒤 같은 셸에서 서버/스크립트를 띄워야 한다.

팀원 각자가 `backend/env.sh`를 자기 환경에 맞게 작성한 뒤 `source`로 적용한다. 이 파일은 `.gitignore`에 등록돼 있으므로 절대 커밋되지 않는다 — 키가 노출될 일은 없다.

## 위치 / 형식

```
JCodeQuest/
└── backend/
    └── env.sh        # ← 각자 작성, 커밋 금지
```

- 한 줄당 `export KEY=VALUE` 형식의 평범한 bash 스크립트.
- 실행이 아니라 **source** 해야 한다 (`./env.sh`가 아니라 `source env.sh`).
- 같은 변수가 OS 환경에 이미 있다면 export로 덮어씀.
- 따옴표는 값에 공백/특수문자가 있을 때만 — `export X="a b"`.

## 변수 목록

> **인증은 Supabase Auth로 마이그레이션됨.** backend는 더 이상 Google OAuth 플로우(`/auth/login`·`/auth/callback`)를 직접 돌리지 않는다. 프런트가 `supabase.auth.signInWithOAuth`로 Google 로그인을 처리하고, backend는 Supabase가 발급한 Bearer JWT만 검증한다(`src/auth/supabase_jwt.py`). 따라서 `GOOGLE_*`/`SESSION_SECRET_KEY`/`JCQ_AUTH_ALLOWED_HD`/`JCQ_FRONTEND_REDIRECT_URL`은 **더 이상 쓰이지 않는다**. (`src/auth/google.py`는 잔존하지만 라우트에서 호출되지 않음.) 허용 이메일 도메인 `@jbnu.ac.kr`은 `supabase_jwt.py`의 `ALLOWED_EMAIL_DOMAIN` 상수에 하드코딩.

### 필수

| 변수 | 용도 | 비고 |
|------|------|------|
| `JCQ_DB_URL` | Supabase PostgreSQL 접속 URL — `src/storage/db.py`가 import 시점에 읽음 | **기본값 없음 — 미설정 시 부팅 실패.** `postgresql://...`이어야 함(Transaction Pooler URL 권장). 비-Postgres는 `JCQ_ALLOW_NON_POSTGRES=1` 필요 |
| `JCQ_INTERNAL_SECRET` | backend ↔ judge_engine ↔ authoring 내부 라우트(`/internal/*`) Bearer 인증 | **세 서비스가 반드시 동일 값.** 비어 있으면 webhook을 401로 거부. 32B+ 랜덤 |
| `SUPABASE_URL` | Supabase 프로젝트 URL — JWKS(`{url}/auth/v1/.well-known/jwks.json`)로 ES256/RS256 JWT 검증 | ES256/RS256 신규 프로젝트는 이것만으로 충분 |
| `SUPABASE_JWT_SECRET` | HS256 레거시 프로젝트용 공유 시크릿 | ES256/RS256 프로젝트면 불필요. 비밀, 커밋 금지 |

### 선택 (기본값 있음)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `OPENAI_MODEL` | `gpt-5.1` | 튜터 모델 ID — `src/tutor/client.py` |
| `OPENAI_BASE_URL` | (미설정 → OpenAI 공식) | 튜터용 OpenAI 호환 엔드포인트(교내 GPT 게이트웨이 등). **API 키는 env가 아니라 유저별 vault에 저장** — 사용자가 `PUT /me/api-key`로 등록하고, 튜터 호출 시 `get_user_api_key`로 꺼내 쓴다. `OPENAI_API_KEY` 전역 env는 더 이상 쓰지 않음 |
| `JCQ_JUDGE_URL` | `http://127.0.0.1:8002` | 채점 엔진(`judge_engine`) HTTP 주소 — `src/judge/client.py`. 같은 머신에서 `scripts/dev.sh up`으로 띄울 때는 기본값 그대로 |
| `JCQ_SUBMIT_COOLDOWN_S` | `10` | 같은 (user, problem) 두 제출 사이 최소 간격(초). 0이면 비활성 |
| `JCQ_SESSION_DAYS` | `7` | dev-stub 세션 쿠키 만료(일). 로그아웃 시 SessionRow 즉시 삭제 — 진짜 무효화 |
| `JCQ_COOKIE_INSECURE` | (미설정) | truthy면 `jcq_session` 쿠키의 `secure=False`(로컬 http 개발용) |
| `JCQ_AUTH_ALLOW_DEV_STUB` | (미설정) | `1`/`true`/`yes`일 때만 `POST /auth/dev-login` 라우트 등록. **prod 절대 금지** |
| `JCQ_CORS_ORIGINS` | (빈 값) | 콤마 구분 허용 origin 목록 — `src/main.py` CORS |
| `JCQ_CORS_ORIGIN_REGEX` | (미설정) | origin 정규식 매칭(프리뷰 도메인 등) |
| `JCQ_BASE_URL` | `http://127.0.0.1:8000` | 스모크 스크립트가 붙을 서버 주소 — `tests/scripts/smoke_e2e.py` |

> `JCQ_QUEUE_CONCURRENCY`는 채점 큐가 judge_engine으로 이전되면서 **backend에서는 더 이상 읽지 않는다** — judge_engine `.env`에 둔다(아래).

### 테스트 전용

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `JCQ_ALLOW_NON_POSTGRES` | (미설정) | `1`일 때만 비-Postgres `JCQ_DB_URL`(SQLite 등) 허용. `tests/conftest.py`·`scripts/verify_all.py`·`scripts/dump_openapi.py`가 설정. **prod 금지** — 비-Postgres는 vault가 평문 폴백이라 키 노출 |
| `JCQ_RUN_LIVE_LLM` | (미설정) | `1`/`true`/`yes`일 때만 `tests/live/` 슈트가 수집됨. 그 외엔 모듈 단위 skip |

## 작성 예시

`backend/env.sh`를 새로 만들 때 이 템플릿에서 시작한다:

```bash
# ─── 필수 ─────────────────────────────────────────────
export JCQ_DB_URL=postgresql://postgres.<ref>:<pwd>@<host>:6543/postgres  # Supabase Transaction Pooler
export JCQ_INTERNAL_SECRET=change-me-shared-with-judge-and-authoring
export SUPABASE_URL=https://<project-ref>.supabase.co
# export SUPABASE_JWT_SECRET=...   # HS256 레거시 프로젝트만

# ─── 선택 ─────────────────────────────────────────────
# export OPENAI_BASE_URL=https://your-school-gpt.example.com/v1   # 튜터 게이트웨이 (키는 유저별 vault)
# export OPENAI_MODEL=gpt-5.1

# 채점 엔진을 다른 호스트/포트로 띄웠을 때만 덮어쓰기
# export JCQ_JUDGE_URL=http://127.0.0.1:8002
# export JCQ_SUBMIT_COOLDOWN_S=10
# export JCQ_CORS_ORIGINS=http://localhost:5173

# ─── 로컬 dev 편의(운영 금지) ───────────────────────────
# export JCQ_AUTH_ALLOW_DEV_STUB=1
# export JCQ_COOKIE_INSECURE=1

# ─── 테스트 전용(필요 시 주석 해제) ─────────────────────
# export JCQ_RUN_LIVE_LLM=1
# export JCQ_ALLOW_NON_POSTGRES=1   # SQLite 등 비-Postgres URL 쓸 때만
```

값을 넣은 뒤 사용 직전에 source한다:

```bash
source backend/env.sh
.venv/bin/uvicorn src.main:app --reload
```

## 주의사항

- **같은 셸에서 source**: 서버 셸과 스크립트 셸이 다르면 `JCQ_DB_URL`이 어긋나 다른 DB를 보게 된다. 스모크를 돌릴 때 특히 주의.
- **Postgres 강제**: `JCQ_DB_URL`이 `postgresql://`이 아니면 `src/storage/db.py`가 부팅 시 `RuntimeError`로 거부한다. 비-Postgres는 vault가 평문 폴백이라 키가 노출되기 때문 — 테스트/로컬에서만 `JCQ_ALLOW_NON_POSTGRES=1`로 우회. `postgresql://`은 내부적으로 `postgresql+psycopg://`(psycopg v3)로 재작성된다.
- **키 회전**: `env.sh`가 노출되면 키가 그대로 새는 거다. 의심되면 발급처에서 즉시 무효화 후 재발급.
- **테스트는 자체 격리**: `tests/conftest.py`가 임시 SQLite를 만들어 `JCQ_DB_URL`을 덮어쓰고 `JCQ_ALLOW_NON_POSTGRES=1`을 세팅하므로, pytest 실행 시 `env.sh`의 DB는 건드리지 않는다.

## 채점 엔진 (`judge_engine`) 환경

채점 엔진은 backend·authoring과 달리 **`.env` 파일**을 쓴다 — `judge_engine/judge/server.py`가 import 시점에 `python-dotenv`로 자동 로드한다. 호출자가 `source`할 필요 없음.

```
JCodeQuest/
└── judge_engine/
    ├── .env.example   # 템플릿 (커밋됨)
    └── .env           # ← 각자 작성, 커밋 금지
```

`.env` 형식은 `KEY=VALUE`(따옴표/`export` 불요). 변수 목록:

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | 3-judge ensemble(Melchior/Balthasar/Casper) Ollama 엔드포인트. 모델 셋업은 `setup-ollama.md` |
| `JCQ_ENSEMBLE_MODEL_MELCHIOR` | `qwen2.5-coder:14b-instruct-q5_K_M` | Melchior(엄격한 채점관) 모델 태그 — `judge/ensemble.py` |
| `JCQ_ENSEMBLE_MODEL_BALTHASAR` | `deepseek-coder-v2:lite` | Balthasar(코드 리뷰어) 모델 태그 |
| `JCQ_ENSEMBLE_MODEL_CASPER` | `llama3.1:8b` | Casper(출제자 의도 분석가) 모델 태그 |
| `JCQ_SKIP_ENSEMBLE` | (미설정) | `1`/`true`/`yes`면 Ollama 호출을 건너뛰고 stub AC 반환 — `scripts/dev.sh up --no-llm`이 주입. 샌드박스 채점은 정상 |
| `JCQ_BACKEND_URL` | `http://127.0.0.1:8000` | 채점 완료 시 webhook(`/internal/grade-events`)을 칠 backend 주소 |
| `JCQ_INTERNAL_SECRET` | (필수) | webhook Bearer 인증 + `/api/grade`·`/api/sandbox/run` 검증 토큰. backend·authoring과 **동일 값**이어야 함. 비어 있으면 backend가 401로 거부 |
| `JCQ_ADMIN_TOKEN` | (미설정) | judge_engine 자체 admin 라우트(`/api/submissions*`·`/api/stats*`·`/api/users*`) Bearer. 미설정 시 해당 라우트 비활성 |
| `JCQ_DASHBOARD_ORIGIN` | (미설정) | 콤마 구분 CORS origin(admin_dashboard용). 미설정이면 CORS 미들웨어 미부착 |
| `JCQ_QUEUE_CONCURRENCY` | `1` | 채점 워커 코루틴 수 — `judge/server.py` lifespan에서 읽음 (backend에서 이전됨) |
| `LANGSMITH_API_KEY` | (미설정 → 트레이싱 비활성) | LangSmith API 키. 잡혀 있으면 채점 1건당 부모 run(`judge.grade_job`) + 3개 LLM 자식 run이 자동 기록됨. metadata에 submission_id/problem_id 포함 |
| `LANGSMITH_PROJECT` | `jcq-judge` | LangSmith 프로젝트명. authoring과 구분하려면 별도 값 권장 |

> judge_engine은 `python-dotenv`로 import 시점에 `judge_engine/.env`를 자동 로드한다(`judge/server.py`). 바인드 포트는 컨테이너/실행 커맨드(`uvicorn judge.server:app --port 8002`)로 지정하며, `.env.example`의 `JCQ_JUDGE_HOST/PORT`는 코드에서 읽지 않는 잔재다.

DB·세션 시크릿·OAuth 키는 채점 엔진과 무관 — 적지 않는다. (DB 접근 없는 순수 계산 서비스)

### 채점 흐름 (분리 후)

```
client  ─POST /grade───────────▶  backend
                                   │
                                   ├── DB row 생성 (status=queued)
                                   ├── POST /api/grade ──────────▶  judge_engine  (큐잉, 202)
                                   └── 202 응답
                                                                       │
                                                                       ▼ 워커 픽업
client  ◀──SSE/polling ────────  backend  ◀── POST /internal/grade-events {event:running}
                                                                       ▼ 채점 완료
client  ◀──SSE/polling ────────  backend  ◀── POST /internal/grade-events {event:done, ...}
```

webhook은 `Authorization: Bearer ${JCQ_INTERNAL_SECRET}` 헤더로 검증. **이 시크릿이 노출되면 임의 결과 주입이 가능하므로** 운영에서는 reverse proxy 단에서 `/internal/*` 외부 노출을 차단할 것.

webhook 전달 실패 시 judge_engine은 0.5s → 2s → 6s 백오프로 3회 재시도하고, 끝까지 실패하면 ERROR 로그를 남기고 포기한다 — submission이 `queued`/`running` 상태로 남아있을 수 있음 (현재 영속 큐 미구현).

## 파이썬 의존성 부트스트랩 / 동기화

각 서비스는 **자기 venv**를 쓴다. 의존성 집합이 서로 달라서(`authoring`만 `sse-starlette`, `judge`만 `langchain-ollama` 등) 한 venv에 몰면 import가 충돌한다.

```
JCodeQuest/
├── backend/.venv          # FastAPI grading API
├── authoring_engine/.venv # 출제 파이프라인
└── judge_engine/.venv     # 채점 엔진 (샌드박스 + LLM 보팅)
```

```bash
# pip는 jcq-shared의 `@ file:../shared` 상대경로 해석을 위해 23.1+ 필요
for d in backend authoring_engine judge_engine; do
    python3 -m venv "$d/.venv"
    "$d/.venv/bin/pip" install --upgrade pip
done

# backend — requirements.txt의 첫 줄이 `file:../shared` 상대경로라 반드시 backend/에서 실행
cd backend && .venv/bin/pip install -r requirements.txt

# authoring_engine, judge_engine — 둘 다 editable install (pyproject가 jcq-shared를 끌어옴)
cd ../authoring_engine && .venv/bin/pip install -e .
cd ../judge_engine     && .venv/bin/pip install -e .
```

증상별 대응:

- `ModuleNotFoundError: No module named 'itsdangerous'` / `'authlib'` → backend 의존성. `cd backend && .venv/bin/pip install -r requirements.txt`.
- `ModuleNotFoundError: No module named 'sse_starlette'` / `'langgraph'` 등 → authoring_engine. `cd authoring_engine && .venv/bin/pip install -e .`.
- `ModuleNotFoundError: No module named 'langchain_ollama'` (judge 로그) → judge_engine. `cd judge_engine && .venv/bin/pip install -e .`.
- `ModuleNotFoundError: No module named 'httpx'` (backend 로그) → backend 의존성 갱신. backend `pip install -r requirements.txt` 재실행.
- `ImportError: cannot import name 'GradeEngineRequest' from 'jcq_shared.schemas'` → `jcq-shared`가 비-editable로 박혀 있어 새 스키마 미반영. 해당 venv에서 `pip install --force-reinstall --no-deps ../shared` 재실행.
- `ERROR: Invalid requirement: 'jcq-shared @ file:../shared'` → pip가 23.0 이하. `pip install --upgrade pip` 후 재시도.
- backend가 채점 요청에서 `ConnectError`/`ConnectionRefused` → 채점 엔진(:8002) 미기동. `scripts/dev.sh status`로 확인, 없으면 `scripts/dev.sh up`.
- `scripts/dev.sh up` 헬스체크 실패 시 로그는 `.dev-logs/{backend,authoring,judge,frontend}.log`에 남는다 — 첫 트레이스만 보면 원인이 잡힌다.

> 운영 규칙: `git pull` 또는 `git reset --hard origin/main`으로 신규 커밋을 받았다면, 코드를 돌리기 전에 위 세 `pip install` 명령을 한 번 더 실행하는 것을 습관으로 한다. 의존성 매니페스트만 갱신되고 venv가 그대로면 import 단계에서 깨진다.

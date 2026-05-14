# JCodeQuest
Problem solving game for education.

전북대학교 SW경진대회 출품작 - JCodeQuest

## Project Summary
Algorithm Problem Solving을 Game처럼 즐길수 있는 플랫폼 - AI 자동 문제 출제 및 제출 시스템 사용. <br />
단계별 학습 코스 제공, 고도화 채점 시스템을 통한 정확한 채점 제공.

## Requirement
Python 3.14+, Ollama, FastAPI, LangChain, Docker(Linux) 필수. <br />

## Setup — 최초 1회

`scripts/setup.sh`로 venv 생성, 의존성 설치, `.env` 템플릿 복사, DB 마이그레이션까지 한 번에 처리한다.

```bash
scripts/setup.sh             # 모든 단계 (권장 — 최초 1회)
scripts/setup.sh --no-venv   # 기존 venv 재사용, 의존성만 재설치
scripts/setup.sh --force-env # 기존 .env를 .env.example로 덮어쓰기
```

스크립트가 끝나면 `backend/.env`, `authoring_engine/.env`의 값을 실제 값으로 채운 뒤(아래 [.env 템플릿](#env-템플릿) 참고), Ollama가 떠 있고 3개 판사 모델이 pull 되어 있는지 확인하고(`docs/setup-ollama.md`), 아래 Quick Start로 진행한다.

## Quick Start — 로컬 개발 서버 일괄 기동

`scripts/dev.sh`로 백엔드(:8000) + 출제 엔진(:8001) + 프론트엔드(:5500) 세 프로세스를 한 번에 띄울 수 있다. PID/로그는 `.dev-logs/`에 보관되며 깔끔하게 종료된다.

```bash
scripts/dev.sh up        # 기동 + 헬스체크
scripts/dev.sh status    # 떠 있는지 확인 (PID / 포트 / health)
scripts/dev.sh logs backend     # uvicorn 로그 tail -f
scripts/dev.sh logs authoring
scripts/dev.sh logs frontend
scripts/dev.sh restart   # down → up
scripts/dev.sh down      # 모두 종료
```

| 서비스 | 포트 | 헬스 | 비고 |
|--------|------|------|------|
| backend | 8000 | `/health` | 채점 + 학습용 학생 API. dev-login은 `JCQ_AUTH_ALLOW_DEV_STUB=1`일 때만 |
| authoring | 8001 | `/api/health` | 원본/변형 조회 + 출제 파이프라인 트리거 |
| frontend | 5500 | `/index.html` | (테스트)정적 HTML 한 장. 브라우저로 `http://localhost:5500` 접속 |

사전 조건:
- `backend/.env` — `SESSION_SECRET_KEY`, `JCQ_DB_URL`(절대경로), `OPENAI_API_KEY`, `OLLAMA_BASE_URL`. dev-login으로 채점까지 시연하려면 `JCQ_AUTH_ALLOW_DEV_STUB=1`, `JCQ_COOKIE_INSECURE=1` 추가. 자세히는 `docs/environment.md`.
- `authoring_engine/.env` — `JCQ_DB_URL`은 backend와 **동일 파일**. 자세히는 `docs/authoring-engine.md`.
- Ollama 인스턴스가 `OLLAMA_BASE_URL`에서 응답하고 3개 판사 모델이 pull 되어 있어야 채점·출제가 동작 (`docs/setup-ollama.md`).

`scripts/dev.sh up`이 같은 포트가 이미 사용 중이라고 실패하면 다른 프로세스를 종료하거나 `scripts/dev.sh down` 후 재시도.

## .env 템플릿

`backend/.env.example`, `authoring_engine/.env.example`을 각각 `.env`로 복사한 뒤 값만 채우면 된다. `JCQ_DB_URL`은 두 파일에서 **동일한 절대경로**를 가리켜야 한다.

`backend/.env_example`:

```dotenv
# ─── 필수 ─────────────────────────────────────────────
export OPENAI_API_KEY=<your-api-key>
export OLLAMA_BASE_URL=http://localhost:11434         # 또는 팀 공용 호스트

# ─── 선택 ─────────────────────────────────────────────
# export OPENAI_BASE_URL=https://your-proxy.example.com/v1
# export OPENAI_MODEL=gpt-4o-mini

export JCQ_DB_URL=sqlite:////home/<you>/jcq.db        # 절대경로 권장
export JCQ_QUEUE_CONCURRENCY=1
# export JCQ_SUBMIT_COOLDOWN_S=10

# ─── 테스트 전용(필요 시 주석 해제) ─────────────────────
# export JCQ_RUN_LIVE_LLM=1

# ─── 세션/인증 ─────────────────────────────────────────────────────
# 이부분은 그대로 사용 하면
SESSION_SECRET_KEY=nZVfOr4M7L2r2vLYjfu9QG8FPxJOz7Ui6xEPkp-Op5I #아무 문자열 넣은거임
JCQ_AUTH_ALLOW_DEV_STUB=1
JCQ_COOKIE_INSECURE=1
JCQ_AUTH_ALLOWED_HD=

# ─── Supabase ───────────────────────────────────────────────────────
SUPABASE_URL=https://<>.supabase.co
VITE_SUPABASE_ANON_KEY=sb~
```

`authoring_engine/.env.example`:

```dotenv
# ─── 백엔드 공유 (backend/.env와 동일 값 유지) ─────────────────────
OLLAMA_BASE_URL=http://localhost:11434
# 절대경로 권장
JCQ_DB_URL=sqlite:////absolute/path/to/backend/data/jcq.db

# ─── LangSmith 트레이싱 (선택 — 값이 있으면 자동 활성화) ────────────
# LANGSMITH_API_KEY=ls__...
# LANGSMITH_PROJECT=jcq-authoring
# LANGCHAIN_TRACING_V2=true
# LANGCHAIN_ENDPOINT=https://api.smith.langchain.com

# ─── 출제 엔진 튜닝 (기본값으로 동작 가능) ──────────────────────────
# JCQ_AUTHOR_MODEL=qwen2.5-coder:14b-instruct-q5_K_M
# JCQ_VARIANT_COUNT=5
# JCQ_AUTHOR_RETRIES=2
# JCQ_JUDGE_PASS_THRESHOLD=0.7
# JCQ_SOLVER_PASS_MIN_AC=1
```

`frontend/.env.example`:

```dotenv
VITE_SUPABASE_URL=https://<>.supabase.co
VITE_SUPABASE_ANON_KEY=sb~
VITE_API_BASE_URL=http://localhost:8000
```

## API Docs — Swagger / OpenAPI

두 서버 모두 FastAPI라서 Swagger UI/OpenAPI 명세가 자동 생성된다. 별도 빌드 없이 서버만 띄우면 브라우저로 바로 확인 가능.

| 서버 | Swagger UI | ReDoc | OpenAPI JSON (라이브) |
| --- | --- | --- | --- |
| backend | http://localhost:8000/docs | http://localhost:8000/redoc | http://localhost:8000/openapi.json |
| authoring | http://localhost:8001/docs | http://localhost:8001/redoc | http://localhost:8001/openapi.json |

`scripts/dev.sh up` 후 위 URL을 그대로 열면 된다. 인증이 필요한 엔드포인트는 같은 브라우저에서 `/auth/login`(또는 `JCQ_AUTH_ALLOW_DEV_STUB=1`일 때 `POST /auth/dev-login`)을 호출해 두면 쿠키가 유지돼 "Try it out"으로 그대로 호출된다.

### 저장소에 커밋된 정적 명세

서버 없이도 명세를 열람·SDK 생성에 쓸 수 있도록 `docs/`에 정적 JSON을 둔다. `dev-login`은 prod-shape에서 제외된다.

- [`docs/openapi-backend.json`](docs/openapi-backend.json)
- [`docs/openapi-authoring.json`](docs/openapi-authoring.json)
- [`docs/api-overview.md`](docs/api-overview.md) — 외부 SDK 생성 예시·정책 요약

### 갱신 — 라우터/스키마를 바꿨다면

`scripts/dump_openapi.py`가 각 FastAPI 앱의 `app.openapi()`를 직접 호출해 JSON을 떨군다. 서버를 띄우지 않으므로 빠르다.

```bash
# 각 패키지 .venv 의존성이 분리되어 있어 한 번씩 호출
backend/.venv/bin/python           scripts/dump_openapi.py backend
authoring_engine/.venv/bin/python  scripts/dump_openapi.py authoring
```

## Documents
- `docs/setup-ollama.md` — Backend Model Setup 가이드
- `docs/environment.md` — `backend/env.sh` 작성법, 환경변수 목록(필수/선택/테스트 전용)과 주의사항
- `docs/problem-format.md` — 문제·테스트케이스·채점 가이드(IntentRubric) 양식과 4축(자연성/부합성/복잡도/필수요소) 매핑
- `docs/authoring-prompt.md` — 출제 LangGraph의 `draft_problem` / `author_solution` 노드용 LLM 프롬프트 사양
- `docs/authoring-engine.md` — 출제 엔진(CLI/HTTP) 실행 가이드, 환경변수, 단계별 결과 해석법
- `docs/testing.md` — 테스트 계층(단위/통합/라이브/스모크), 실행 방법, 격리·LLM mocking 규약
- `docs/api-overview.md` / `docs/api-backend.md` / `docs/api-authoring-engine.md` — API 요약 + Swagger/OpenAPI 사용법

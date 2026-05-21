# JCodeQuest
Problem solving game for education.

전북대학교 SW경진대회 출품작 - JCodeQuest

## Project Summary
Algorithm Problem Solving을 Game처럼 즐길수 있는 플랫폼 - AI 자동 문제 출제 및 제출 시스템 사용.<br />
단계별 학습 코스 제공, 고도화 채점 시스템을 통한 정확한 채점 제공.

## Architecture
| 서비스 | 포트 | 역할 |
|--------|------|------|
| `frontend` | 5173 | Vite + React SPA. Supabase Auth(Google OIDC) → backend에 Bearer JWT. |
| `backend` | 8000 | FastAPI. 학생/채점/튜터 API, Supabase JWT 검증, DB 접근. |
| `authoring` | 8001 | LangGraph 변형 출제 파이프라인 + 뷰어. backend HTTP API로 DB 접근. |
| `judge` | 8002 | 샌드박스 + Ollama 3-LLM 앙상블 채점. backend로 webhook callback. |
| `dashboard` | 6010 | 관리자용 정적 대시보드(문제·제출 모니터링). Python `http.server`. |

DB - Supabase <br />
Auth - Supabase Auth

### 접속 가이드

| URL | Usage |
|---|---|
| http://localhost:5173 | **메인 화면**. Vite dev server (HMR 켜짐). |
| http://localhost:8000/docs | **backend Swagger UI**|
| http://localhost:8001/docs | **authoring(출제 엔진) Swagger UI** |
| http://localhost:8002/api/health | judge 헬스체크. |
| http://localhost:6010 | **관리자 대시보드** — 문제/제출 모니터링. |

## Requirement

- Docker / Docker Compose
- Supabase 프로젝트 (PostgreSQL + Auth)
- Ollama 인스턴스 + 3개 판사 모델 (`docs/setup-ollama.md`)

## Run with Docker Compose

### 1) `.env.docker` 작성
[`.env.docker.example`](.env.docker.example)을 `.env.docker` 이름으로 복사 후 값을 채워넣아야 한다.

### 2) 빌드 + 기동

```bash
docker compose --env-file .env.docker up --build -d
docker compose --env-file .env.docker ps
docker compose --env-file .env.docker logs -f backend
```

### 3) 종료

```bash
docker compose --env-file .env.docker down              # 컨테이너 정리
docker compose --env-file .env.docker down --rmi local  # 이미지까지 제거
```

## API Docs — Swagger / OpenAPI

| 서버 | Swagger UI | ReDoc | OpenAPI JSON |
| --- | --- | --- | --- |
| backend | http://localhost:8000/docs | http://localhost:8000/redoc | http://localhost:8000/openapi.json |
| authoring | http://localhost:8001/docs | http://localhost:8001/redoc | http://localhost:8001/openapi.json |

통합 명세
- [`docs/api-overview.md`](docs/api-overview.md)

## Documents

내부 개발/운영자용 문서는 `docs/`에 정리되어 있다.

- [`docs/development.md`](docs/development.md) — 로컬 dev 흐름(`scripts/setup.sh`/`dev.sh`), 환경변수 핵심 키, 테스트, OpenAPI 갱신
- [`docs/environment.md`](docs/environment.md) — 환경변수 전체 목록(필수/선택/테스트 전용)
- [`docs/setup-ollama.md`](docs/setup-ollama.md) — Ollama / 3개 판사 모델 셋업
- [`docs/testing.md`](docs/testing.md) — 테스트 계층, LLM mocking 규약
- [`docs/problem-format.md`](docs/problem-format.md) — 문제·테스트케이스·IntentRubric(4축) 양식
- [`docs/authoring-prompt.md`](docs/authoring-prompt.md) — 출제 LangGraph LLM 프롬프트 사양
- [`docs/authoring-engine.md`](docs/authoring-engine.md) — 출제 엔진(CLI/HTTP) 실행 가이드
- [`docs/api-overview.md`](docs/api-overview.md) / [`docs/api-backend.md`](docs/api-backend.md) / [`docs/api-authoring-engine.md`](docs/api-authoring-engine.md) — API 요약

# JCodeQuest
Problem solving game for education.

전북대학교 SW경진대회 출품작 - JCodeQuest

## Project Summary
Algorithm Problem Solving을 Game처럼 즐길수 있는 플랫폼 - AI 자동 문제 출제 및 제출 시스템 사용.<br />
단계별 학습 코스 제공, 고도화 채점 시스템을 통한 정확한 채점 제공.

## Architecture

4종 서비스가 한 Supabase PostgreSQL을 공유한다.

| 서비스 | 포트 | 역할 |
|--------|------|------|
| `backend` | 8000 | FastAPI. 학생/채점/튜터 API, Supabase JWT 검증, DB 접근. |
| `judge` | 8002 | 샌드박스 + Ollama 3-LLM 앙상블 채점. backend로 webhook callback. |
| `authoring` | 8001 | LangGraph 변형 출제 파이프라인. backend HTTP API로 DB 접근. |
| `frontend` | 5173 | Vite + React SPA. Supabase Auth(Google OIDC) → backend에 Bearer JWT. |

DB는 외부(Supabase). 인증은 Supabase Auth가 프런트에서 처리하고 backend는 JWT만 검증. Ollama는 외부 호스트(기본 `host.docker.internal:11434`).

## Requirement

- Docker / Docker Compose
- Supabase 프로젝트 (PostgreSQL + Auth)
- Ollama 인스턴스 + 3개 판사 모델 (`docs/setup-ollama.md`)

## Run with Docker Compose

### 1) `.env.docker` 작성

```bash
cp .env.docker.example .env.docker
# .env.docker의 빈 값을 채운다 — 특히:
#   JCQ_DB_URL              Supabase Transaction Pooler URL
#   SUPABASE_URL            Project URL (JWT JWKS 검증용)
#   VITE_SUPABASE_URL       위와 동일
#   VITE_SUPABASE_ANON_KEY  Supabase anon key
#   JCQ_INTERNAL_SECRET     32B+ 랜덤 (backend↔judge 공유)
#   OPENAI_API_KEY          튜터용
#   OLLAMA_BASE_URL         3-judge ensemble 호스트
```

전체 키 목록·설명은 [`.env.docker.example`](.env.docker.example).

### 2) 빌드 + 기동

```bash
docker compose --env-file .env.docker up --build -d
docker compose --env-file .env.docker ps
docker compose --env-file .env.docker logs -f backend
```

- 호스트 노출: backend `:8000`, authoring `:8001`, frontend `:5173`. judge는 내부 네트워크 전용.
- 프런트엔드는 Vite multi-stage 빌드(`node:20-alpine` → `nginx:1.27-alpine`). `VITE_*` 변수는 빌드 타임에 인라인되므로 값을 바꾸면 `--build`로 재빌드.

### 3) 종료

```bash
docker compose --env-file .env.docker down              # 컨테이너 정리
docker compose --env-file .env.docker down --rmi local  # 이미지까지 제거
```

## API Docs — Swagger / OpenAPI

두 서버 모두 FastAPI라서 OpenAPI 명세가 자동 생성된다.

| 서버 | Swagger UI | ReDoc | OpenAPI JSON |
| --- | --- | --- | --- |
| backend | http://localhost:8000/docs | http://localhost:8000/redoc | http://localhost:8000/openapi.json |
| authoring | http://localhost:8001/docs | http://localhost:8001/redoc | http://localhost:8001/openapi.json |

서버를 안 띄우고 명세만 볼 거면 저장소에 커밋된 정적 JSON:

- [`docs/openapi-backend.json`](docs/openapi-backend.json)
- [`docs/openapi-authoring.json`](docs/openapi-authoring.json)
- [`docs/api-overview.md`](docs/api-overview.md) — 외부 SDK 생성 예시·정책 요약

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

# JCodeQuest
Problem solving game for education.

전북대학교 SW경진대회 출품작 - JCodeQuest

## Project Summary
Algorithm Problem Solving을 Game처럼 즐길 수 있는 플랫폼 - AI 자동 문제 출제, 고도화된 3-judge LLM 앙상블 채점, 실시간 Code Battle, 자동 표절 검사를 제공합니다.<br />
- **자동 문제 출제**: LangGraph 기반 변형 출제 파이프라인 (draft → novelty/RAG → verify → judge → solve → attack/strengthen → compare → persist)
- **고급 채점**: 순수 Python 샌드박스 + Ollama 3-judge 앙상블(투표 기반 판정)
- **Code Battle**: 매일 20시 실시간 경쟁 대전
- **표절 검사**: Dolos + Winnow 기반 자동 표절 감지 (첫 AC 제출 시 자동 트리거)
- **관리자 포렌식**: 문제·제출·실행 추적·표절 현황을 한눈에 모니터링

## Architecture
| 서비스 | 포트 | 역할 |
|--------|------|------|
| `frontend` | 5173 | Vite + React SPA. 학생용 메인 UI(문제 풀이·순위·Code Battle·채점 결과). Supabase Auth(Google OIDC) → backend에 Bearer JWT. |
| `backend` | 8000 | FastAPI. 학생/채점/튜터/경쟁/표절 API, Supabase JWT 검증, DB 접근, 표절 검사 자동 트리거. |
| `authoring` | 8001 | LangGraph 변형 출제 파이프라인 + 뷰어. draft → novelty/RAG → verify → judge(중앙값) → solve → attack/strengthen → compare(hallucination/intent 검증) → persist. LLM 프로바이더 전환 가능(`JCQ_LLM_PROVIDER` — 기본 `ollama` / `openai`). |
| `judge` | 8002 | 순수 Python 샌드박스(socket/subprocess/ctypes 차단) + Ollama 3-LLM 앙상블(Melchior/Balthasar/Casper) 채점. 테스트 실행 → 채점 → webhook callback. (이 앙상블은 항상 Ollama — `JCQ_LLM_PROVIDER`와 무관.) |
| `plagiarism_engine` | 8003 | Dolos + Winnow 기반 표절 검사 서비스. 사용자 쌍 비교 → 4축 점수(novelty/structure/semantic/lexical) → verdict. 비동기 큐 처리. |
| `admin_dashboard` | 6010 | Vite + React 관리자 포렌식 대시보드. 문제/제출/실행 추적, RunsView(node_states), 표절 현황, 통계(KPI 7개+차트 6개). |
| `presentation` | 5180 | React + Framer Motion 심사위원 발표 덱. 백엔드 불필요, 정적 배포 가능(오프라인 가능). |

**DB**: Supabase PostgreSQL (모든 서비스 공유)<br />
**Auth**: Supabase Auth (Google OAuth + dev-only stub)

### 접속 가이드

| URL | 설명 |
|---|---|
| **http://localhost:5173** | **학생 메인 SPA** — 문제 풀이, 순위, Code Battle, 채점 결과. |
| http://localhost:8000/docs | **backend Swagger UI** — 모든 REST API 문서. |
| http://localhost:8001/docs | **authoring 출제 엔진 Swagger UI** — 변형 출제 파이프라인 제어. |
| http://localhost:8002/api/health | **judge 헬스체크** — 채점 엔진 상태. |
| http://localhost:8003/health | **plagiarism_engine 헬스체크** — 표절 검사 엔진 상태. |
| **http://localhost:6010** | **관리자 포렌식 대시보드** — 문제·제출·실행·표절 모니터링, KPI, 통계. |
| **http://localhost:5180** | **심사위원 발표 덱** — 프로젝트 소개 프레젠테이션 (백엔드 불필요). |

## Requirement

- **Docker / Docker Compose** — 모든 서비스 컨테이너화
- **Supabase 프로젝트** (PostgreSQL + Auth) — DB + Google OAuth
- **Ollama 인스턴스** — judge 3-LLM 앙상블(Melchior/Balthasar/Casper) + 임베딩(`bge-m3`, novelty/RAG) (`docs/setup-ollama.md`)
- **(선택) OpenAI 또는 호환 엔드포인트** — 출제 엔진 LLM을 Ollama 대신 쓸 때 (`docs/environment.md` → `JCQ_LLM_PROVIDER=openai`)

### LLM 프로바이더 (출제 엔진)

출제 엔진(`authoring`) 파이프라인의 모든 LLM 노드(draft/verify/judge/solve/attack/compare)는 `JCQ_LLM_PROVIDER` 하나로 전환됩니다. **호출 시점에 env를 읽으므로 재시작 없이 바뀝니다.**

| 값 | 동작 |
|---|---|
| `ollama` (기본) | 노드별 모델 사용 — draft/verify는 `JCQ_AUTHOR_MODEL`, quality-judge의 3명은 `JCQ_ENSEMBLE_MODEL_{MELCHIOR,BALTHASAR,CASPER}`. |
| `openai` | 전 노드가 단일 모델 사용 — `JCQ_OPENAI_MODEL`(기본 `gpt-4o-mini`). `JCQ_OPENAI_BASE_URL`로 호환 엔드포인트(예: `gpt.jbnu.ai`), `JCQ_OPENAI_API_KEY` 또는 `OPENAI_API_KEY`로 인증. |

**주의:**
- `openai` 모드: 3-judge 앙상블이 **같은 모델 3회 투표**로 축소됨(중앙값·2/3 판정은 유지되나 판사 다양성 ↓). 출제 모델과 심사 모델이 동일해짐.
- 임베딩(novelty·RAG): 프로바이더와 무관하게 **항상 Ollama `bge-m3`** 사용(저장 벡터 차원 일치). Ollama 없으면 게이트 fail-open(건너뜀).
- judge 채점 엔진(`:8002`)의 3-judge 앙상블: 이 스위치와 무관하게 **항상 Ollama**. 채점과 출제 LLM은 독립적으로 구성.

## Getting Started

### 1) 환경 변수 설정
[`.env.example`](.env.example)을 참고하여 `.env` 파일을 생성합니다.
```bash
cp .env.example .env
# .env 편집: JCQ_DB_URL, JCQ_SUPABASE_KEY, Ollama 주소 등
```

### 2) 로컬 개발 시작 (권장)
모든 서비스를 순서대로 시작합니다(`judge` → `backend` → `authoring` → `admin_dashboard` → `frontend`).
```bash
scripts/dev.sh up                    # 전체 스택 시작 (Ollama + LLM 앙상블 포함)
scripts/dev.sh up --no-llm           # Ollama/앙상블 스킵 (JCQ_SKIP_ENSEMBLE=1)
scripts/dev.sh up --no-authoring     # 출제 엔진 제외
scripts/dev.sh logs backend          # 실시간 로그
scripts/dev.sh restart               # 재시작
scripts/dev.sh down                  # 종료
```

### 3) Docker Compose로 배포
[`.env.docker.example`](.env.docker.example)을 기반으로 `.env.docker`를 작성합니다.
```bash
docker compose --env-file .env.docker up --build -d   # 빌드 + 시작
docker compose --env-file .env.docker ps              # 상태 확인
docker compose --env-file .env.docker logs -f backend # 로그 보기
docker compose --env-file .env.docker down            # 종료
docker compose --env-file .env.docker down --rmi local
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

# Authoring Engine API Reference (`authoring_engine/`)

FastAPI 출제 파이프라인 + 문제/스팬 조회 서버. 기본 포트 `8001` (시작 명령: `uvicorn authoring.server:app --port 8001`).

- **OpenAPI 명세:** `GET /openapi.json`
- **Swagger UI:** `GET /docs`
- **ReDoc:** `GET /redoc`

백엔드와 **같은 SQLite DB**(`JCQ_DB_URL`)를 공유하며, `backend/src/storage`를 `sys.path`로 끌어다 직접 사용합니다(`authoring/config.py:ensure_backend_on_path()`). 인증은 없음 — 신뢰된 네트워크 내부에서만 운용 전제.

| 그룹 | 경로 | 설명 |
| --- | --- | --- |
| Health | `/api/health` | liveness probe |
| Runs | `/api/runs`, `/api/runs/{id}/events` | LangGraph 파이프라인 실행 + SSE |
| Problems | `/api/problems`, `/api/problems/{id}`, `/api/problems/{id}/children` | 문제 조회 + 원본 직접 등록 |
| Spans | `/api/spans/{trace_id}` | LangSmith 트레이스 조회 |

---

## `/api/health`

### `GET /api/health`
- 응답 `200`: `{ "status": "ok" }`

---

## Runs — 출제 파이프라인 실행

### `POST /api/runs` → `RunResponse`
LangGraph DAG `fetch_problem → generate_variants → verify_candidates → judge_candidates → solve_candidates → persist_approved` 를 백그라운드 스레드로 실행. 즉시 `run_id`/`trace_id` 반환.

- Body (`RunRequest`):
  ```json
  {
    "problem_id": 1,
    "count": 5
  }
  ```
- 응답 `200`:
  ```json
  {
    "run_id": "8c1f...e9",
    "trace_id": "5dc8d3e2-...-..."
  }
  ```
  - `run_id`: 메모리 상의 큐 키 (서버 재시작 시 사라짐).
  - `trace_id`: LangSmith 트레이스 ID (UUID). `/api/spans/{trace_id}`로 추적.

### `GET /api/runs/{run_id}/events` *(SSE)*
실행 진행 이벤트 스트림. `Content-Type: text/event-stream`.

- 이벤트 페이로드 형식:
  ```json
  { "type": "update", "data": { /* langgraph chunk */ } }
  { "type": "done",   "trace_id": "..." }
  { "type": "error",  "message": "ExceptionType: message" }
  ```
- `type in {"done","error"}`이면 스트림 종료 + 서버측에서 `run_id` 해제.
- 에러: `404` `run_id` 없음 (이미 종료되어 해제됐거나 존재하지 않음).

> **주의:** 레지스트리(`_runs`, `_run_traces`)는 프로세스 메모리에 있어 멀티-워커 배포 시 sticky routing이 필요. 단일 워커 운용 전제.

---

## Problems — 문제 조회/등록

### `GET /api/problems`
- Query: `originals_only` (bool, default `true`) — `true`면 `parent_id IS NULL` 행만.
- 응답: 각 행에 변형 통계가 합쳐진 요약 배열.
  ```json
  [
    {
      "id": 1,
      "title": "...",
      "category": "basic",
      "level": "bronze",
      "status": "approved|draft|...",
      "parent_id": null,
      "langsmith_trace_id": "...|null",
      "created_at": "2026-05-12T03:04:05Z",
      "child_count": 4,
      "avg_judge_score": 0.82
    }
  ]
  ```

### `GET /api/problems/{problem_id}`
- 응답: 요약 필드 + 다음 상세 필드.
  ```json
  {
    "...summary fields...": "...",
    "statement": "...",
    "reference_code": "...",
    "intent_rubric": { /* IntentRubric JSON */ },
    "authoring_meta": { /* 자유 형식 메타 */ },
    "points": 100,
    "time_limit_ms": 2000,
    "memory_limit_mb": 256,
    "test_cases": [
      {
        "ordinal": 1,
        "stdin": "...",
        "expected_stdout": "...",
        "is_sample": true
      }
    ]
  }
  ```
- 에러: `404` 미존재.

### `POST /api/problems` — 원본 문제 직접 등록 (출제 엔진 우회)
출제 엔진을 거치지 않고 원본을 직접 `status="approved"`로 삽입. 운영자/시드 용도.

- Body (`CreateOriginalRequest`):
  ```json
  {
    "title": "...",
    "statement": "...",
    "category": "basic",
    "level": "bronze|silver|gold",
    "points": 100,
    "time_limit_ms": 2000,
    "memory_limit_mb": 256,
    "reference_code": "<python source>",
    "one_line_summary": "",
    "expected_approach": "",
    "key_insight": "",
    "expected_complexity": "",
    "must_handle": [],
    "forbidden_patterns": [],
    "test_cases": [
      { "stdin": "...", "expected_stdout": "", "is_sample": false }
    ]
  }
  ```
  - `expected_stdout`이 비어 있으면 `reference_code`를 sandbox에서 실행해 자동 채움.
- 응답 `200`:
  ```json
  {
    "id": 42,
    "autofill": [
      { "ordinal": 1, "elapsed_ms": 12, "expected": "..." }
    ]
  }
  ```
- 에러:
  - `400` `test_cases` 비었거나 `level` 값 부정
  - `422` 자동 채움 실패(non-zero/TLE/RE) — `detail`에 `case <i>: <status>`와 `stderr` 일부 포함

### `GET /api/problems/{problem_id}/children`
- 응답: `parent_id == problem_id` 인 변형 상세 배열 (구조는 `GET /api/problems/{id}` 와 동일).

---

## Spans — LangSmith 트레이스

### `GET /api/spans/{trace_id}`
- 동작: `LANGSMITH_API_KEY` 가 설정되어 있어야 함. `LANGSMITH_PROJECT` (기본 `jcq-authoring`) 안에서 `trace_id`에 묶인 모든 run을 가져와 prompts/IO/tokens/latency/cost를 정리.
- 응답:
  ```json
  {
    "trace_id": "...",
    "project": "jcq-authoring",
    "summary": {
      "span_count": 12,
      "total_tokens": 4321,
      "prompt_tokens": 2100,
      "completion_tokens": 2221,
      "root_latency_seconds": 8.5
    },
    "spans": [
      {
        "id": "...",
        "parent_run_id": "...|null",
        "name": "...",
        "run_type": "llm|chain|tool|...",
        "status": "success|error|...",
        "start_time": "...",
        "end_time": "...",
        "latency_seconds": 1.2,
        "tokens": { "prompt": 0, "completion": 0, "total": 0 },
        "cost": null,
        "inputs": { /* ... */ },
        "outputs": { /* ... */ },
        "error": null,
        "extra": { /* metadata */ },
        "tags": []
      }
    ]
  }
  ```
- 에러:
  - `404` 해당 `trace_id`의 run이 LangSmith에 없음
  - `500` langsmith 클라이언트 import 실패
  - `502` LangSmith API 호출 실패
  - `503` `LANGSMITH_API_KEY` 미설정

---

## 환경 변수 (요약)

| 변수 | 기본값 | 비고 |
| --- | --- | --- |
| `JCQ_DB_URL` | `sqlite:///./data/jcq.db` | **반드시 절대 경로 권장** — CWD-상대면 다른 디렉터리에서 실행 시 별개의 DB가 만들어짐. |
| `LANGSMITH_API_KEY` | (unset) | 설정 시 startup에서 `LANGCHAIN_TRACING_V2`, `LANGCHAIN_ENDPOINT`, `LANGCHAIN_PROJECT` 자동 세팅. 미설정이면 `/api/spans`는 `503`. |
| `LANGSMITH_PROJECT` | `jcq-authoring` | LangSmith 프로젝트 이름. |

전체 목록은 [`docs/environment.md`](environment.md).

---

## CORS

다음 오리진에 대해 credentials 포함 모든 메서드/헤더 허용:
- `http://localhost:5500`, `http://127.0.0.1:5500`
- `http://localhost:8000`, `http://127.0.0.1:8000`

백엔드(`8000`)에서 출제 엔진(`8001`)으로의 호출 또는 frontend(`5500`)에서 직접 호출하는 형상이 기본.

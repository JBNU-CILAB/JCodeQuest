# Authoring Engine API Reference (`authoring_engine/`)

FastAPI 출제 파이프라인 + 문제/공지/스팬 관리 서버. 기본 포트 `8001` (시작 명령: `uvicorn authoring.server:app --port 8001`).

- **OpenAPI 명세:** `GET /openapi.json`
- **Swagger UI:** `GET /docs`
- **ReDoc:** `GET /redoc`

이 서버는 **DB를 직접 보유하지 않는다.** 모든 문제·공지 CRUD는 backend(`JCQ_BACKEND_URL`, 기본 `:8000`)의 `/internal/*`에, 코드 실행은 judge_engine(`JCQ_JUDGE_URL`, 기본 `:8002`)의 `/api/sandbox/run`에 위임한다(`authoring/backend_client.py`). 그 호출 자체는 backend·judge·authoring이 공유하는 `JCQ_INTERNAL_SECRET` Bearer로 인증된다.

| 그룹 | 경로 | 인증 |
| --- | --- | --- |
| Health | `/api/health` | 없음 |
| Runs | `/api/runs`, `/api/runs/{id}/events` | admin |
| Problems | `/api/problems`, `/api/problems/{id}`, `/api/problems/{id}/children` | admin |
| Notices | `/api/notices`, `/api/notices/{id}` | admin |
| Admin Comparison | `/api/admin/problems/{id}/comparison`, `/api/admin/originals/{id}/comparison` | admin |
| Spans | `/api/spans/{trace_id}` | admin |

---

## 인증

`/api/health`를 제외한 모든 라우트는 `Authorization: Bearer <JCQ_ADMIN_TOKEN>`을 요구한다(`authoring/admin_auth.py:require_admin`).

- `JCQ_ADMIN_TOKEN` 미설정 → 모든 라우트 `503 admin endpoint disabled`.
- 헤더 누락/형식 오류 → `401 missing bearer token`.
- 값 불일치 → `401 invalid token` (timing-safe `hmac.compare_digest`).

> **SSE 주의**: 브라우저 `EventSource`는 `Authorization` 헤더를 못 보낸다. `/api/runs/{run_id}/events`를 브라우저에서 직접 구독하려면 query token 방식이나 `fetch`+ReadableStream 폴리필을 별도로 구현해야 한다.

---

## `/api/health`

### `GET /api/health` *(인증 없음)*
- 응답 `200`: `{ "status": "ok" }`

---

## Runs — 출제 파이프라인 실행

### `POST /api/runs` → `RunResponse`
LangGraph DAG `fetch_problem → generate_variants → verify_candidates → judge_candidates → solve_candidates → compare_to_original → persist_approved` 를 백그라운드 스레드로 실행. 즉시 `run_id`/`trace_id` 반환.

- Body (`RunRequest`):
  ```json
  {
    "problem_id": 1,
    "count": 5
  }
  ```
  - `count`: 1~20 (Pydantic 검증).
- 응답 `200`:
  ```json
  {
    "run_id": "8c1f...e9",
    "trace_id": "5dc8d3e2-...-..."
  }
  ```
  - `run_id`: 메모리 상의 큐 키 (서버 재시작 시 사라짐).
  - `trace_id`: LangSmith 트레이스 ID (UUID). 이 값은 `RunnableConfig.run_id`로 LangChain에 주입되며, `persist_approved` 노드가 `ProblemRow.langsmith_trace_id`에도 함께 기록한다. `/api/spans/{trace_id}`로 조회.

### `GET /api/runs/{run_id}/events` *(SSE)*
실행 진행 이벤트 스트림. `Content-Type: text/event-stream`.

- 이벤트 페이로드 형식:
  ```json
  { "type": "update", "data": { /* langgraph chunk: {<node_name>: <node_output_dict>} */ } }
  { "type": "done",   "trace_id": "..." }
  { "type": "error",  "message": "ExceptionType: message" }
  ```
- `type in {"done","error"}`이면 스트림 종료 + 서버 측에서 `run_id` 해제.
- 에러: `404` `run_id` 없음 (이미 종료되어 해제됐거나 존재하지 않음).

> **주의:** 레지스트리(`_runs`, `_run_traces`)는 프로세스 메모리에 있어 멀티 워커 배포 시 sticky routing이 필요. 단일 워커 운용 전제.

---

## Problems — 문제 조회/등록/삭제

모두 backend `/internal/problems/*`에 위임.

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
    "authoring_meta": {
      "judge_score": 0.83,
      "judge_passed": true,
      "judge_rationale": "...",
      "judge_issues": [],
      "solver_results": [...],
      "solver_passed": true,
      "verify_passed": true,
      "verify_error": "",
      "verify_attempts": 1,
      "comparison": {
        "hallucination_score": 0.05,
        "intent_similarity": 0.82,
        "difficulty_similarity": 0.78,
        "rationale": "[Melchior] ...",
        "error": ""
      },
      "issued_iso_week": "2026-W21"
    },
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
출제 엔진의 LangGraph DAG를 거치지 않고 원본을 직접 `status="approved"`로 삽입. 운영자/시드 용도.

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
  - `expected_stdout`이 비어 있으면 judge_engine `POST /api/sandbox/run`을 호출해 `reference_code` 실행 결과로 자동 채움.
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
  - `422` 자동 채움 실패(non-OK status: TLE/MLE/RE 등) — `detail`에 `case <i>: <status>`와 `stderr` 일부 포함

### `GET /api/problems/{problem_id}/children`
- 응답: `parent_id == problem_id` 인 변형 상세 배열 (구조는 `GET /api/problems/{id}` 와 동일).

### `DELETE /api/problems/{problem_id}`
- Query: `cascade_children` (bool, default `true`).
- 동작: backend `DELETE /internal/problems/{id}?cascade_children=…`에 위임. cascade=false인데 자식 변형이 남아 있으면 backend가 FK 위반으로 실패한다.
- 응답: `ProblemDeleteResponse`(backend가 반환한 그대로).
- 에러: `404` 문제 없음.

---

## Notices — 공지 CRUD

모두 backend `/internal/notices*`에 그대로 위임. 응답 형식은 backend의 그것을 통과시킨다.

| 메서드 | 경로 | 비고 |
| --- | --- | --- |
| `GET` | `/api/notices?limit=N` | N은 1~200, 기본 100 |
| `POST` | `/api/notices` | 임의 JSON body — backend 스키마에 맞춰 보낼 것 |
| `PATCH` | `/api/notices/{id}` | 임의 JSON body |
| `DELETE` | `/api/notices/{id}` | — |

---

## Admin Comparison — `compare_to_original` 결과 노출

`compare_to_original` 노드가 `authoring_meta.comparison`에 기록한 3축 정량 점수를 admin 대시보드용 형태로 추출·집계.

- 게이트가 아니다 — persist 통과 여부는 `solver_passed`로만 결정된다. 이 점수는 사후 시각화용.
- `solver_results`가 채워진(=solve_candidates까지 진입한) 변형에만 실행되므로, 그 이전에 떨어진 후보나 수동 등록 원본은 점수가 모두 null로 나온다.

### `GET /api/admin/problems/{problem_id}/comparison` → `ProblemComparisonOut`
```json
{
  "problem_id": 42,
  "parent_id": 1,
  "title": "...",
  "level": "bronze",
  "hallucination_score": 0.05,     // 0=환각 없음, 1=심함
  "intent_similarity": 0.82,        // 0=무관, 1=동일 부류
  "difficulty_similarity": 0.78,    // 0=난이도 차이 큼, 1=거의 동일
  "rationale": "[Melchior] ...",
  "error": "",
  "judge_score": 0.83,
  "solver_passed": true
}
```
- 에러: `404` 문제 없음.

### `GET /api/admin/originals/{original_id}/comparison` → `ComparisonAggregateOut`
한 원본의 모든 자식 변형 점수 + 평균/최소/최대 집계.

```json
{
  "original_id": 1,
  "original_title": "...",
  "variant_count": 4,
  "scored_count": 3,
  "hallucination":         { "count": 3, "mean": 0.07, "min": 0.05, "max": 0.10 },
  "intent_similarity":     { "count": 3, "mean": 0.81, "min": 0.78, "max": 0.85 },
  "difficulty_similarity": { "count": 3, "mean": 0.77, "min": 0.70, "max": 0.82 },
  "variants": [ /* ProblemComparisonOut[] */ ]
}
```
- `scored_count`는 점수가 채워진 변형 수(`hallucination_score is not None`). 그 미만 변형들도 `variants`에 점수=null로 함께 포함.
- 에러: `404` 원본 없음.

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
| `JCQ_BACKEND_URL` | `http://127.0.0.1:8000` | backend 베이스 URL. 모든 DB 경로의 종착점. |
| `JCQ_JUDGE_URL` | `http://127.0.0.1:8002` | judge_engine 베이스 URL. sandbox 실행용. |
| `JCQ_INTERNAL_SECRET` | (unset) | backend·judge·authoring **셋이 공유**해야 하는 Bearer. backend `/internal/*` 인증용. |
| `JCQ_ADMIN_TOKEN` | (unset) | 이 서버의 `/api/*` 보호용. 미설정 시 503. |
| `JCQ_DASHBOARD_ORIGIN` | (unset) | 콤마 구분 origin. CORS preflight 허용 목록. 미설정 시 미들웨어 미부착. |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama 엔드포인트. |
| `LANGSMITH_API_KEY` | (unset) | 설정 시 startup에서 `LANGCHAIN_TRACING_V2`, `LANGCHAIN_ENDPOINT`, `LANGCHAIN_PROJECT` 자동 세팅. 미설정이면 `/api/spans`는 `503`. |
| `LANGSMITH_PROJECT` | `jcq-authoring` | LangSmith 프로젝트 이름. |
| `JCQ_AUTHOR_MODEL` | `qwen2.5-coder:14b-instruct-q5_K_M` | generate/verify 재시도/compare에 사용. |
| `JCQ_VARIANT_COUNT` | `5` | CLI 기본 변형 수. 서버는 요청 바디로 받음. |
| `JCQ_AUTHOR_RETRIES` | `2` | verify 단계 author_solution 재시도 횟수. |
| `JCQ_JUDGE_PASS_THRESHOLD` | `0.7` | judge_candidates 평균 score 임계. |
| `JCQ_SOLVER_PASS_MIN_AC` | `1` | solve_candidates AC 통과 최소 인원. |

전체 목록은 [`docs/environment.md`](environment.md). 동작 흐름은 [`docs/authoring-engine.md`](authoring-engine.md).

---

## CORS

`JCQ_DASHBOARD_ORIGIN` 환경변수에 콤마 구분으로 등록된 origin만 허용. credentials 포함 모든 메서드/헤더 허용. 미설정이면 CORS 미들웨어 자체를 부착하지 않으므로 동일 origin 호출만 가능하다.

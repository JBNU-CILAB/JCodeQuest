# API Reference

JCodeQuest FastAPI 백엔드의 전체 엔드포인트 문서.

- **Swagger UI**: `http://localhost:8000/docs`
- **OpenAPI JSON**: `http://localhost:8000/openapi.json`

---

## 라우터 구성

| 파일 | Prefix | Tags |
|---|---|---|
| `src/api/auth.py` | `/auth` | auth |
| `src/api/me.py` | `/me` | me |
| `src/api/problems.py` | `/problems` | problems |
| `src/api/grading.py` | `/grade` | grading |
| `src/api/tutor.py` | `/tutor` | tutor |

---

## 인증 방식

`get_current_user` 의존성 (`src/auth/deps.py`) — 두 방식을 순서대로 시도한다.

1. **Bearer JWT** (프로덕션): `Authorization: Bearer <Supabase JWT>` 헤더 → 서명 검증 → `sub` / `email` / `user_metadata.full_name` 추출 → provider=`supabase`로 upsert
2. **Session 쿠키** (개발용): `jcq_session` 쿠키 → `SessionRow` DB 조회 → `UserRow` 반환. `JCQ_AUTH_ALLOW_DEV_STUB=1` 환경변수 필요.

---

## 엔드포인트 목록

### Root

#### `GET /health`

헬스체크.

- **Auth**: 없음
- **Response**

```json
{ "status": "ok" }
```

---

### /auth

#### `POST /auth/logout`

현재 세션을 무효화하고 쿠키를 삭제한다.

- **Auth**: 선택적 (`jcq_session` 쿠키)
- **Response**

```json
{ "status": "logged out" }
```

---

#### `POST /auth/dev-login` ⚠️ 개발 전용

OAuth 없이 즉시 로그인. `JCQ_AUTH_ALLOW_DEV_STUB=1` 일 때만 라우터가 등록된다.

- **Auth**: 없음
- **Query Parameters**

| 이름 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `email` | string | ✅ | 사용할 이메일 |
| `name` | string | | 표시 이름 (default: `"dev user"`) |

- **Response**

```json
{ "user_id": 123 }
```

- **Effect**: provider=`dev_stub`으로 유저 upsert + `jcq_session` 쿠키 설정

---

### /me

#### `GET /me`

현재 인증된 유저의 프로필을 반환한다.

- **Auth**: 필수
- **Response**

```json
{
  "id": 1,
  "display_name": "User Name",
  "email": "user@example.com",
  "provider": "supabase",
  "exp": 0,
  "tier": "bronze"
}
```

---

### /problems

#### `GET /problems`

승인된 문제 목록을 조회한다.

- **Auth**: 없음
- **Query Parameters**

| 이름 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `category` | string | | 카테고리 필터 |
| `level` | `"bronze"` \| `"silver"` \| `"gold"` | | 난이도 필터 |

- **Response**: `ProblemSummary[]`

```json
[
  {
    "id": 1,
    "title": "문제 제목",
    "category": "math",
    "level": "bronze",
    "points": 100,
    "one_line_summary": "한 줄 설명"
  }
]
```

- `status = "approved"` 인 문제만 반환한다.

---

#### `GET /problems/{problem_id}`

문제 상세 정보와 샘플 테스트케이스를 반환한다.

- **Auth**: 없음
- **Path Parameters**: `problem_id` (int)
- **Response**: `ProblemDetail`

```json
{
  "id": 1,
  "title": "문제 제목",
  "statement": "문제 본문 (HTML/markdown)",
  "category": "math",
  "level": "bronze",
  "points": 100,
  "time_limit_ms": 2000,
  "memory_limit_mb": 256,
  "one_line_summary": "한 줄 설명",
  "sample_test_cases": [
    { "ordinal": 1, "stdin": "입력", "expected_stdout": "출력" }
  ]
}
```

- `reference_code`, 숨긴 테스트케이스, `intent_rubric` 내부는 응답에서 제외된다.
- **Errors**: `404` — 문제가 없거나 `status != "approved"`

---

### /grade

#### `POST /grade`

코드를 채점 큐에 제출한다. 채점은 비동기로 실행된다.

- **Auth**: 필수
- **Status**: `202 Accepted`
- **Request Body**: `GradeRequest`

```json
{ "problem_id": 1, "code": "def solve(): pass" }
```

- 코드 길이 제한: 1 ~ 65,536 bytes (`MAX_CODE_LENGTH = 64 * 1024`)

- **Response**: `GradeAcceptedResponse`

```json
{ "submission_id": 42, "status": "queued" }
```

- **Errors**

| 코드 | 조건 |
|---|---|
| `404` | 문제 없음 |
| `409` | 이미 AC를 획득한 문제 |
| `429` | 최대 시도 횟수 초과 또는 쿨다운 위반 (기본 10초; `Retry-After` 헤더 포함) |

---

#### `GET /grade/{submission_id}`

제출의 현재 채점 상태와 결과를 반환한다.

- **Auth**: 없음
- **Path Parameters**: `submission_id` (int)
- **Response**: `SubmissionStatusResponse`

```json
{
  "submission_id": 42,
  "status": "done",
  "final_verdict": "AC",
  "test_results": [
    {
      "ordinal": 1,
      "passed": true,
      "status": "OK",
      "actual_stdout": "출력",
      "error": null,
      "elapsed_ms": 50,
      "peak_memory_kb": 2048
    }
  ],
  "ensemble": {
    "final_verdict": "AC",
    "mode": "unanimous",
    "votes": [
      {
        "judge_id": "Melchior",
        "verdict": "AC",
        "intent_match": true,
        "rationale": "설명",
        "confidence": 0.95
      }
    ]
  },
  "points_awarded": 100
}
```

| 필드 | 값 |
|---|---|
| `status` | `"queued"` \| `"running"` \| `"done"` \| `"failed"` |
| `final_verdict` | `"AC"` \| `"SUS"` \| `null` (완료 전) |
| `test_results` | `null` (done/failed 이전) |
| `ensemble` | `null` (done/failed 이전). 3개 Ollama 모델 투표 (2/3 이상 AC → AC) |
| `points_awarded` | `null` (AC 아닌 경우) |

- **Errors**: `404` — 제출 없음

---

#### `GET /grade/{submission_id}/events`

채점 진행 상황을 SSE(Server-Sent Events)로 실시간 스트리밍한다.

- **Auth**: 없음
- **Path Parameters**: `submission_id` (int)
- **Response**: `text/event-stream`
  - 각 프레임: `SubmissionStatusResponse` JSON
  - 15초마다 keep-alive comment 전송
  - `status = "done"` 또는 `"failed"` 도달 시 스트림 종료
- **주의**: 스냅샷(`GET /grade/{id}`) 조회 **전에** 먼저 구독해야 이벤트 누락이 없다. (`src/api/grading.py:stream_grade_events` 참고)
- **Errors**: `404` — 제출 없음

---

### /tutor

#### `POST /tutor/{submission_id}`

AI 튜터 피드백을 요청한다. 캐시된 메시지가 있으면 재사용하고, `regenerate=true`이면 LLM을 재호출한다.

- **Auth**: 없음
- **Path Parameters**: `submission_id` (int)
- **Query Parameters**

| 이름 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `regenerate` | bool | | `true`이면 LLM 재호출 + 새 행 저장 (default: `false`) |

- **Response**: `TutorResponse`

```json
{ "submission_id": 42, "message": "<HTML/markdown 피드백>" }
```

- **Errors**

| 코드 | 조건 |
|---|---|
| `404` | 제출 없음 |
| `409` | 제출이 아직 `status = "done"` 아님 |

---

#### `GET /tutor/{submission_id}/history`

해당 제출에 대한 모든 튜터 메시지 히스토리를 반환한다.

- **Auth**: 없음
- **Path Parameters**: `submission_id` (int)
- **Response**: `TutorHistoryResponse`

```json
{
  "submission_id": 42,
  "messages": [
    { "id": 1, "message": "첫 번째 피드백", "created_at": "2025-05-13T10:30:00Z" },
    { "id": 2, "message": "재생성 피드백",  "created_at": "2025-05-13T10:35:00Z" }
  ]
}
```

- **Errors**: `404` — 제출 없음

---

## Pydantic 스키마 요약

| 스키마 | 위치 | 주요 필드 |
|---|---|---|
| `GradeRequest` | `backend/src/schemas.py` | `problem_id`, `code` |
| `GradeAcceptedResponse` | `backend/src/schemas.py` | `submission_id`, `status` |
| `SubmissionStatusResponse` | `backend/src/schemas.py` | `submission_id`, `status`, `final_verdict`, `test_results`, `ensemble`, `points_awarded` |
| `TestResult` | `backend/src/schemas.py` | `ordinal`, `passed`, `status`, `actual_stdout`, `error`, `elapsed_ms`, `peak_memory_kb` |
| `JudgeVote` | `backend/src/schemas.py` | `judge_id`, `verdict`, `intent_match`, `rationale`, `confidence` |
| `EnsembleResult` | `backend/src/schemas.py` | `final_verdict`, `mode`, `votes[]` |
| `ProblemSummary` | `backend/src/schemas.py` | `id`, `title`, `category`, `level`, `points`, `one_line_summary` |
| `ProblemDetail` | `backend/src/schemas.py` | `ProblemSummary` + `statement`, `time_limit_ms`, `memory_limit_mb`, `sample_test_cases[]` |
| `PublicTestCase` | `backend/src/schemas.py` | `ordinal`, `stdin`, `expected_stdout` |
| `TutorResponse` | `backend/src/schemas.py` | `submission_id`, `message` |
| `TutorHistoryItem` | `backend/src/schemas.py` | `id`, `message`, `created_at` |
| `TutorHistoryResponse` | `backend/src/schemas.py` | `submission_id`, `messages[]` |
| `Problem` | `shared/jcq_shared/schemas.py` | 전체 문제 (reference_code, intent_rubric 포함 — 내부용) |
| `IntentRubric` | `shared/jcq_shared/schemas.py` | `expected_approach`, `expected_complexity`, `must_handle[]`, `forbidden_patterns[]`, `key_insight`, `one_line_summary` |
| `TestCase` | `shared/jcq_shared/schemas.py` | `ordinal`, `stdin`, `expected_stdout`, `is_sample` |

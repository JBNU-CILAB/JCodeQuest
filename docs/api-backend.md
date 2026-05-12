# Backend API Reference (`backend/`)

FastAPI 채점 서버. 기본 포트 `8000`. 모든 응답은 JSON(별도 명시 제외).

- **OpenAPI 명세:** `GET /openapi.json`
- **Swagger UI:** `GET /docs`
- **ReDoc:** `GET /redoc`

FastAPI가 라우터·Pydantic 스키마로부터 위 문서를 자동 생성하므로, 이 파일은 사람이 빠르게 훑기 위한 요약입니다. 응답/요청 필드의 단일 진실 원천은 `backend/src/schemas.py`.

---

## 인증 모델

- 세션 쿠키 이름: `jcq_session` (httponly, `lax`, `secure`는 `JCQ_COOKIE_INSECURE` 미설정 시 true).
- 인증이 필요한 엔드포인트는 표에 **🔒** 로 표시. `get_current_user` 의존성이 쿠키를 검증하고 `UserRow`를 주입.
- 비인증 호출은 `401 Unauthorized`.

| 그룹 | 경로 | 설명 |
| --- | --- | --- |
| `auth` | `/auth/*` | Google OAuth 로그인/로그아웃, dev stub |
| `me` | `/me/*` | 본인 프로필·제출 이력 |
| `problems` | `/problems/*` | 승인된 문제 목록·상세·시도 상태 |
| `grade` | `/grade/*` | 채점 요청·조회·SSE 스트림 |
| `tutor` | `/tutor/*` | 튜터 메시지 생성·이력 |
| (root) | `/health` | liveness probe |

---

## `/health`

### `GET /health`
- 인증: 없음
- 응답 `200`: `{ "status": "ok" }`

---

## `/auth` — 인증

### `GET /auth/login`
- 인증: 없음
- 동작: Google OAuth `authorize_redirect`. state/nonce를 `SessionMiddleware`의 임시 쿠키에 저장.
- 응답: `302` → Google.

### `GET /auth/callback` (name: `auth_callback`)
- 인증: 없음
- 동작: ID 토큰 검증 → `JCQ_AUTH_ALLOWED_HD` (기본 `jbnu.ac.kr`) 검증 → `get_or_create_user` → 세션 발급(`SessionRow`) → `JCQ_FRONTEND_REDIRECT_URL`로 302.
- 에러:
  - `400` OAuth 실패 / `userinfo` 누락 / `sub`·`email` 누락
  - `403` 이메일 미인증 또는 도메인 불일치

### `POST /auth/logout`
- 인증: 쿠키 있으면 해당 `SessionRow` 삭제 후 쿠키 클리어 (없어도 200).
- 응답 `200`: `{ "status": "logged out" }`

### `POST /auth/dev-login` *(dev 전용)*
- **`JCQ_AUTH_ALLOW_DEV_STUB=1` 일 때만 등록되는 라우트.** 프로덕션에서는 라우트 자체가 존재하지 않음.
- Query:
  - `email` (required) — dev_stub 유저 이메일
  - `name` (default `"dev user"`) — 표시 이름
- 응답 `200`: `{ "user_id": <int> }` + `jcq_session` 쿠키 발급.

---

## `/me` — 본인 정보

### `GET /me` 🔒
- 응답 `200`:
  ```json
  {
    "id": 1,
    "display_name": "...",
    "email": "...",
    "provider": "google" | "dev_stub",
    "exp": 0,
    "tier": "..."
  }
  ```

### `GET /me/submissions` 🔒 → `SubmissionListResponse`
본인이 낸 제출들을 최신순으로 반환. `code` 필드는 페이로드 비대해서 제외 — 상세는 `GET /grade/{id}`.

- Query:
  - `problem_id` (int, optional)
  - `verdict` (`AC` | `SUS`, optional) — sandbox-fail은 `SUS`로 묶임
  - `limit` (1–100, default 20)
  - `offset` (≥0, default 0)
- 응답 항목 (`SubmissionListItem`):
  ```json
  {
    "id": 1,
    "problem_id": 1,
    "status": "queued|running|done|failed",
    "final_verdict": "AC|SUS|null",
    "mode": "unanimous|majority|null",
    "points_awarded": 100,
    "max_elapsed_ms": 12,
    "peak_memory_kb": 4096,
    "created_at": "2026-05-12T03:04:05Z"
  }
  ```

---

## `/problems` — 문제

### `GET /problems` → `list[ProblemSummary]`
승인(`status="approved"`)된 문제만 노출.

- 인증: 없음
- Query:
  - `category` (string, optional)
  - `level` (`bronze` | `silver` | `gold`, optional)
- 항목:
  ```json
  {
    "id": 1,
    "title": "...",
    "category": "basic",
    "level": "bronze",
    "points": 100,
    "one_line_summary": "..."
  }
  ```

### `GET /problems/{problem_id}` → `ProblemDetail`
- 인증: 없음
- 동작: `status != "approved"` 또는 미존재면 `404`.
- 응답: statement + 샘플 케이스만 공개. 정답 코드/숨김 케이스/intent rubric 내부는 비공개.
  ```json
  {
    "id": 1,
    "title": "...",
    "statement": "...",
    "category": "basic",
    "level": "bronze",
    "points": 100,
    "time_limit_ms": 2000,
    "memory_limit_mb": 256,
    "one_line_summary": "...",
    "sample_test_cases": [
      { "ordinal": 1, "stdin": "...", "expected_stdout": "..." }
    ]
  }
  ```

### `GET /problems/{problem_id}/attempt-status` 🔒 → `AttemptStatusResponse`
제출 화면이 버튼 활성/비활성을 결정하기 위해 호출.

- 응답:
  ```json
  {
    "problem_id": 1,
    "attempts": 2,
    "remaining": 8,
    "max_attempts": 10,
    "solved": false,
    "cooldown_remaining_s": 4.2,
    "can_submit": false
  }
  ```
- 에러: `404` 미존재 / 미승인 문제.

### `GET /problems/{problem_id}/my-submissions` 🔒 → `SubmissionListResponse`
문제 페이지에서 "내가 이 문제에 낸 시도들"을 보이기 위한 편의 엔드포인트. 파라미터는 `/me/submissions`와 동일하되 `problem_id`가 경로로 고정.

---

## `/grade` — 채점

### `POST /grade` 🔒 → `GradeAcceptedResponse`
제출을 큐에 적재. 즉시 `202`로 반환되고, 결과는 `GET /grade/{id}` 폴링 또는 `GET /grade/{id}/events` SSE로 추적.

- Body (`GradeRequest`):
  ```json
  {
    "problem_id": 1,
    "code": "<= 64 KiB 의 Python 소스>"
  }
  ```
  `user_id`는 세션에서 추출 — body로 받지 않음.
- 응답 `202`:
  ```json
  { "submission_id": 42, "status": "queued" }
  ```
- 에러:
  - `404` 문제 없음
  - `409` 이미 해결한 문제
  - `429` 최대 시도 초과 또는 쿨다운 중 (헤더 `Retry-After` 포함)

### `GET /grade/{submission_id}` → `SubmissionStatusResponse`
스냅샷 조회.

- 응답:
  ```json
  {
    "submission_id": 42,
    "status": "queued|running|done|failed",
    "final_verdict": "AC|SUS|null",
    "test_results": [
      {
        "ordinal": 1,
        "passed": true,
        "status": "OK|TLE|MLE|RE",
        "actual_stdout": "...|null",
        "error": "...|null",
        "elapsed_ms": 10,
        "peak_memory_kb": 4096
      }
    ],
    "ensemble": {
      "final_verdict": "AC|SUS",
      "mode": "unanimous|majority",
      "votes": [
        {
          "judge_id": "Melchior|Balthasar|Casper",
          "verdict": "AC|SUS",
          "intent_match": true,
          "rationale": "...",
          "confidence": 0.0
        }
      ]
    },
    "points_awarded": 100
  }
  ```
- 에러: `404` 미존재.

### `GET /grade/{submission_id}/events` *(SSE)*
서버-전송 이벤트 스트림. `text/event-stream`. 클라이언트는 **스냅샷을 읽기 전에 먼저 구독**해야 중간 이벤트를 놓치지 않음.

- 처음 1회: 현재 스냅샷(`SubmissionStatusResponse`)을 `data:` 페이로드로 푸시.
- 이후: 상태/결과가 바뀔 때마다 동일 페이로드 푸시. 페이로드가 직전과 동일하면 스킵.
- 15초마다 `: keep-alive` 코멘트(no-op) 전송 — 프록시 idle timeout 회피.
- `status in {"done","failed"}`이면 스트림 종료.
- 에러: `404` 미존재.

---

## `/tutor` — 튜터 메시지

### `POST /tutor/{submission_id}` → `TutorResponse`
- Query:
  - `regenerate` (bool, default `false`) — `true`면 캐시 무시하고 새로 생성, 새 행으로 저장.
- 응답:
  ```json
  { "submission_id": 42, "message": "..." }
  ```
- 에러:
  - `404` 제출 없음 / 제출에 매칭된 문제 없음
  - `409` `status != "done"` (튜터링은 채점 종료 후에만)

### `GET /tutor/{submission_id}/history` → `TutorHistoryResponse`
- 응답:
  ```json
  {
    "submission_id": 42,
    "messages": [
      { "id": 7, "message": "...", "created_at": "2026-05-12T03:04:05Z" }
    ]
  }
  ```
- 에러: `404` 제출 없음.

---

## 환경 변수 (요약)

API 동작에 직접 영향이 있는 키만:

| 변수 | 기본값 | 비고 |
| --- | --- | --- |
| `SESSION_SECRET_KEY` | (required) | OAuth state/nonce 쿠키 서명. 미설정 시 부팅 실패. |
| `JCQ_FRONTEND_REDIRECT_URL` | `/` | OAuth 콜백 후 리다이렉트 목적지. |
| `JCQ_AUTH_ALLOWED_HD` | `jbnu.ac.kr` | Google Workspace 도메인 게이트. 빈 문자열이면 해제. |
| `JCQ_AUTH_ALLOW_DEV_STUB` | (unset) | `1`이면 `POST /auth/dev-login` 등록. 프로덕션 금지. |
| `JCQ_SESSION_DAYS` | `7` | 세션 TTL. |
| `JCQ_COOKIE_INSECURE` | (unset) | 트루시면 `secure` 끔(로컬 http 개발용). |
| `JCQ_QUEUE_CONCURRENCY` | `1` | 채점 워커 동시성. |
| `MAX_CODE_LENGTH` | 64 KiB | `GradeRequest.code` 상한 (`schemas.py` 상수). |

전체 목록은 [`docs/environment.md`](environment.md).

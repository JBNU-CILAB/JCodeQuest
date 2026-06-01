# Backend API Reference (`backend/`)

FastAPI 채점 서버. 기본 포트 `8000`. 모든 응답은 JSON(별도 명시 제외).

- **OpenAPI 명세:** `GET /openapi.json`
- **Swagger UI:** `GET /docs`
- **ReDoc:** `GET /redoc`

FastAPI가 라우터·Pydantic 스키마로부터 위 문서를 자동 생성하므로, 이 파일은 사람이 빠르게 훑기 위한 요약입니다. 응답/요청 필드의 단일 진실 원천은 `backend/src/schemas.py`.

---

## 인증 모델

`get_current_user` 의존성(`src/auth/deps.py`)이 두 방식을 순서대로 시도해 `UserRow`를 주입한다:

1. **Supabase Bearer JWT** (운영): `Authorization: Bearer <Supabase access_token>` → JWKS로 ES256/RS256 검증(레거시 HS256은 `SUPABASE_JWT_SECRET`) → `sub`/`email`/`user_metadata` 추출 → `provider="supabase"`로 upsert. 이메일은 `@jbnu.ac.kr`만 허용(`ALLOWED_EMAIL_DOMAIN` 상수).
2. **세션 쿠키** (dev 전용): `jcq_session` (httponly, `lax`, `secure`는 `JCQ_COOKIE_INSECURE` 미설정 시 true) — `POST /auth/dev-login`이 발급하며 `JCQ_AUTH_ALLOW_DEV_STUB=1`일 때만 동작.

- 인증이 필요한 엔드포인트는 표에 **🔒** 로 표시. 비인증/검증 실패는 `401 Unauthorized`.
- **Google OAuth는 프런트(Supabase)가 처리** — backend에는 `/auth/login`·`/auth/callback`이 없다.

| 그룹 | 경로 | 설명 |
| --- | --- | --- |
| `auth` | `/auth/*` | 로그아웃, dev-stub 로그인 |
| `me` | `/me/*` | 본인 프로필·API 키·제출 이력·스트릭 |
| `problems` | `/problems/*` | 승인된 문제 목록·주차별·상세·시도 상태 |
| `grade` | `/grade/*` | 채점 요청·조회·SSE 스트림 |
| `tutor` | `/tutor/*` | 튜터 메시지 생성·이력 (인증 + 유저 API 키 필요) |
| `submissions` | `/submissions/recent` | 전체 사용자 최근 제출(공개) |
| `leaderboard` | `/leaderboard/*` | 누적/주간/학년별 리더보드(공개) |
| `notices` | `/notices/*` | 공지 목록·상세(공개) |
| `reports` | `/reports` | 버그/문제 신고 접수 🔒 |
| `internal` | `/internal/*` | judge_engine·authoring 전용. `JCQ_INTERNAL_SECRET` Bearer. 스키마 비노출(`include_in_schema=False`) |
| (root) | `/health` | liveness probe |

---

## `/health`

### `GET /health`
- 인증: 없음
- 응답 `200`: `{ "status": "ok" }`

---

## `/auth` — 인증

> Google 로그인은 프런트의 `supabase.auth.signInWithOAuth`가 전담한다. backend는 발급된 JWT를 검증할 뿐 OAuth 리다이렉트 라우트(`/auth/login`·`/auth/callback`)를 갖지 않는다.

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

### `GET /me` 🔒 → `MeResponse`
- 응답 `200`:
  ```json
  {
    "id": 1,
    "display_name": "...",
    "email": "...",
    "provider": "supabase" | "dev_stub",
    "exp": 0,
    "tier": "...",
    "has_api_key": false,
    "nickname": "...|null",
    "grade": 3,
    "department": "...|null",
    "is_anonymous": false,
    "avatar_url": "...|null"
  }
  ```

### `PATCH /me` 🔒 → `MeResponse`
프로필 부분 수정. body의 일부 필드만 보내면 그것만 갱신.
- Body: `nickname`, `grade`(1–6), `department`, `is_anonymous`, `avatar_url` (모두 optional)

### `PUT /me/api-key` 🔒
튜터용 교내 GPT API 키를 vault에 등록/갱신. 평문은 응답/로그에 노출되지 않음(`PUT`의 422는 자동 redaction).
- Body (`ApiKeyUpdateRequest`): `{ "api_key": "<20–512 printable ASCII>" }` — 패턴 `^[!-~]{20,512}$`
- 응답 `200`: `{ "has_api_key": true }`

### `GET /me/streak` 🔒 → `StreakResponse`
연속 풀이 스트릭 통계.

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

### `GET /problems/weeks` → `WeeklyProblemBucketsResponse`
- 인증: 없음
- 동작: 문제가 출제된 ISO 주차(`YYYY-Www`)별 개수 버킷을 최신순으로 반환.

### `GET /problems/weeks/{week}` → `list[ProblemSummary]`
- 인증: 없음
- 동작: 특정 ISO 주차(`YYYY-Www`)에 속한 승인 문제 목록.

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

> 문제별 "내 시도" 목록은 별도 라우트가 아니라 `GET /me/submissions?problem_id=<id>`로 조회한다.

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

### `POST /tutor/{submission_id}` 🔒 → `TutorResponse`
인증 필수. 유저가 `PUT /me/api-key`로 등록한 교내 GPT 키(vault)로 호출하므로 **키가 없으면 거부**. 문제당 사용 횟수 상한이 있다(기본 3회).
- Query:
  - `regenerate` (bool, default `false`) — `true`면 캐시 무시하고 새로 생성, 새 행으로 저장.
- 응답:
  ```json
  { "submission_id": 42, "message": "..." }
  ```
- 에러:
  - `404` 제출 없음 / 제출에 매칭된 문제 없음
  - `409` `status != "done"`(채점 종료 후에만) / 유저 API 키 미등록 / 문제당 사용 한도 초과

### `GET /tutor/{submission_id}/history` 🔒 → `TutorHistoryResponse`
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

## `/submissions` — 전체 제출 피드

### `GET /submissions/recent` → `RecentSubmissionsResponse`
- 인증: 없음
- Query: `limit` (1–50, default 20)
- 동작: 모든 사용자의 최근 제출을 최신순으로. 익명 유저는 표시명이 가려진다.

---

## `/leaderboard` — 리더보드

### `GET /leaderboard` → `LeaderboardResponse`
- 인증: 없음
- Query:
  - `period` (`all` | `week`, default `all`) — `all`은 누적 `exp`, `week`는 이번 ISO 주차 `points_awarded` 합.
  - `limit` (1–100)

### `GET /leaderboard/by-grade` → `LeaderboardResponse`
- 인증: 없음
- Query: `grade` (1–4), `limit` — 학년별 리더보드.

---

## `/notices` — 공지

### `GET /notices` → `list[Notice]`
- 인증: 없음
- Query: `limit` (1–50). pinned 우선 정렬.

### `GET /notices/{notice_id}` → `Notice`
- 인증: 없음
- 에러: `404` 미존재.

---

## `/reports` — 신고

### `POST /reports` 🔒 → `BugReportCreateResponse`
버그/문제 신고 접수.
- Body (`BugReportCreateRequest`):
  - `category` (`judging` | `statement` | `sample` | `system` | `other`)
  - `title` (4–200자), `body` (10–10,000자)
  - `problem_id` (optional), `code_snapshot` (optional, ≤ 64 KiB)
- 응답 `200`: `{ "id": <int>, "status": "open" }`

---

## 환경 변수 (요약)

API 동작에 직접 영향이 있는 키만:

| 변수 | 기본값 | 비고 |
| --- | --- | --- |
| `JCQ_DB_URL` | (required) | Supabase PostgreSQL URL. `postgresql://`이 아니면 부팅 거부(`JCQ_ALLOW_NON_POSTGRES=1` 제외). |
| `SUPABASE_URL` | (required) | JWT JWKS 검증용 프로젝트 URL. |
| `SUPABASE_JWT_SECRET` | (unset) | HS256 레거시 프로젝트만. |
| `JCQ_INTERNAL_SECRET` | (unset) | `/internal/*` Bearer. judge·authoring과 동일 값. |
| `JCQ_AUTH_ALLOW_DEV_STUB` | (unset) | `1`이면 `POST /auth/dev-login` 등록. 프로덕션 금지. |
| `JCQ_SESSION_DAYS` | `7` | dev-stub 세션 TTL. |
| `JCQ_COOKIE_INSECURE` | (unset) | 트루시면 `secure` 끔(로컬 http 개발용). |
| `JCQ_CORS_ORIGINS` / `JCQ_CORS_ORIGIN_REGEX` | (unset) | 허용 origin. |
| `OPENAI_MODEL` / `OPENAI_BASE_URL` | `gpt-5.1` / (unset) | 튜터 서버 설정(키는 유저별 vault). |
| `MAX_CODE_LENGTH` | 64 KiB | `GradeRequest.code`·`code_snapshot` 상한 (`schemas.py` 상수). |

> `SESSION_SECRET_KEY`·`JCQ_FRONTEND_REDIRECT_URL`·`JCQ_AUTH_ALLOWED_HD`·`GOOGLE_*`는 Supabase 전환으로 더 이상 쓰지 않는다. `JCQ_QUEUE_CONCURRENCY`는 judge_engine으로 이전. 전체 목록은 [`docs/environment.md`](environment.md).

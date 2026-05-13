# 프론트엔드–백엔드 연동 작업 계획

> 백엔드 API 10개를 React 프론트엔드(`frontend/`)와 연결하는 작업 계획.
> 인증은 이미 Supabase JWT로 마이그레이션 완료된 상태에서 출발.

---

## 1. 현황

### 1.1 백엔드 API (구현 완료, Swagger 노출)

| Method | Path | 인증 | 설명 |
|---|---|---|---|
| GET  | `/me` | 필요 | 내 프로필 (id, display_name, email, provider, exp, tier) |
| GET  | `/problems` | 없음 | 문제 목록 (query: `category`, `level`) |
| GET  | `/problems/{id}` | 없음 | 문제 상세 + 샘플 테스트케이스 |
| POST | `/grade` | 필요 | 코드 제출 → `{submission_id, status:"queued"}` (202) |
| GET  | `/grade/{id}` | 없음 | 제출 결과 스냅샷 |
| GET  | `/grade/{id}/events` | 없음 | SSE 진행 스트림 (`queued → running → done/failed`) |
| POST | `/tutor/{id}` | 없음 | 튜터 피드백 생성 (query: `regenerate`) |
| GET  | `/tutor/{id}/history` | 없음 | 튜터 메시지 이력 |
| POST | `/auth/logout` | 없음 | dev-login 쿠키 세션 무효화 |
| POST | `/auth/dev-login` | 없음 | **dev only** — `JCQ_AUTH_ALLOW_DEV_STUB=1`일 때만 등록 |

### 1.2 프론트엔드 현재 상태

- Vite + React + Tailwind, 단일 페이지 (라우팅 없음)
- 모든 데이터는 `src/data.ts`의 mock
- Supabase Auth 연동 완료 (`signInWithOAuth` / `signOut`)
- 컴포넌트: `Header`, `Hero`, `Dashboard`, `RankingCard`, `RecentSubmissionsCard`, `WeeklyProblemsCard`

### 1.3 백엔드에 없는 API (mock 유지 또는 추후 추가)

- 유저별 제출 목록 (`GET /me/submissions`) — `RecentSubmissionsCard`용
- 랭킹 리스트 (`GET /ranking`) — `RankingCard`용

### 1.4 DB 마이그레이션

**스키마 변경 불필요.** 현재 스키마는 기존 API 10개와 향후 추가될 랭킹/유저 제출 목록 API를 모두 지원한다.

단, Google OAuth → Supabase 전환으로 `user.provider` 값이 `'google'` → `'supabase'`로 바뀌었기 때문에:
- 기존 `provider='google'` 유저가 있다면 Supabase 재로그인 시 새 row가 생긴다 (exp, tier 초기화).
- 데이터 보존이 필요하면 one-shot SQL로 `provider`/`external_id`를 Supabase UUID로 업데이트해야 한다.

---

## 2. Phase 1 — 기반 (API 클라이언트 + 타입 + 라우팅)

### 2.1 API 클라이언트 (`src/lib/api.ts`)

- `fetch` 래퍼 — Supabase 세션에서 `access_token`을 꺼내 `Authorization: Bearer`로 자동 주입
- 공용 에러 처리:
  - 401 → Supabase signOut 호출 + 랜딩으로 이동
  - 4xx/5xx → throw `ApiError`
- 메서드 헬퍼: `apiGet`, `apiPost`, `apiSse` (SSE 전용)

### 2.2 타입 정의 (`src/types.ts` 업데이트)

백엔드 Pydantic 스키마와 1:1 대응:

```ts
export interface UserMe {
  id: number
  display_name: string
  email: string | null
  provider: string
  exp: number
  tier: string
}

export interface ProblemSummary {
  id: number
  title: string
  category: string
  level: 'bronze' | 'silver' | 'gold'
  points: number
  one_line_summary: string
}

export interface ProblemDetail extends ProblemSummary {
  statement: string
  time_limit_ms: number
  memory_limit_mb: number
  sample_test_cases: PublicTestCase[]
}

export interface PublicTestCase {
  ordinal: number
  stdin: string
  expected_stdout: string
}

export type SubmissionStatus = 'queued' | 'running' | 'done' | 'failed'

export interface TestResult {
  ordinal: number
  passed: boolean
  status: string
  actual_stdout: string
  error: string | null
  elapsed_ms: number
  peak_memory_kb: number
}

export interface JudgeVote {
  judge_id: string
  verdict: 'AC' | 'SUS'
  intent_match: boolean
  rationale: string
  confidence: number
}

export interface EnsembleResult {
  final_verdict: 'AC' | 'SUS'
  mode: 'unanimous' | 'majority'
  votes: JudgeVote[]
}

export interface SubmissionStatusResponse {
  submission_id: number
  status: SubmissionStatus
  final_verdict: 'AC' | 'SUS' | null
  test_results: TestResult[] | null
  ensemble: EnsembleResult | null
  points_awarded: number | null
}

export interface TutorResponse {
  submission_id: number
  message: string
}

export interface TutorHistoryItem {
  id: number
  message: string
  created_at: string
}

export interface TutorHistoryResponse {
  submission_id: number
  messages: TutorHistoryItem[]
}
```

기존 mock 타입 (`RankUser`, `WeeklyProblem`, `Submission`)은 mock 카드용으로 유지.

### 2.3 라우팅 (`react-router-dom` 도입)

| Path | 컴포넌트 | 인증 |
|---|---|---|
| `/` | 랜딩 + (로그인 시) 대시보드 | - |
| `/problems` | 문제 목록 페이지 | - |
| `/problems/:id` | 문제 풀기 (지문 + 에디터) | 제출은 필요 |
| `/submissions/:id` | 채점 결과 + 튜터 | - |

`App.tsx`를 `BrowserRouter` 셋업으로 변경.

---

## 3. Phase 2 — 인증 / 유저 프로필

### 3.1 `GET /me` 연동
- 세션이 있을 때 `/me` 호출 → 전역 상태 (Context 또는 zustand) 에 저장
- `Header`의 `🙂` → 실제 Google 프로필 이미지 (Supabase `user_metadata.avatar_url`)
- 닉네임, 티어, exp 배지 표시

### 3.2 인증 가드
- `/problems/:id`의 제출 버튼은 로그인 안 했으면 비활성 + "로그인 필요" 툴팁
- API 401 응답 시 자동 로그아웃 + 랜딩으로 이동 (Phase 1의 공용 에러 처리)

---

## 4. Phase 3 — 문제 목록 페이지 (`/problems`)

### 4.1 `GET /problems` 연동
- 페이지 로드 시 호출 → 카드 그리드로 표시
- 카드: 제목 / 카테고리 칩 / 레벨 칩 / 포인트 / 한줄요약

### 4.2 필터
- 카테고리 select (백엔드에서 distinct category 받아오는 별도 API가 없으니 클라이언트에서 distinct 추출)
- 레벨 토글 (bronze / silver / gold)
- 필터 변경 시 `?category=...&level=...` 쿼리로 재호출

### 4.3 헤더 네비 "문제페이지" 링크 연결

---

## 5. Phase 4 — 문제 풀기 페이지 (`/problems/:id`)

### 5.1 `GET /problems/{id}` 연동
- 좌측: 지문, 시간/메모리 제한, 샘플 입출력
- 우측: 코드 에디터

### 5.2 코드 에디터
- `@monaco-editor/react` 도입
- 언어 Python 3 고정 (현재 백엔드 샌드박스가 Python 전용)
- 기본 코드 템플릿 표시

### 5.3 `POST /grade` 연동
- "제출" 버튼 → `{problem_id, code}` 전송
- 202 응답의 `submission_id` 받아서 `/submissions/:id`로 navigate
- 에러 처리:
  - 401 → 로그인 모달
  - 409 (이미 푼 문제, 쿨다운) → 토스트
  - 422 (코드 길이 초과 등) → 인라인 에러

---

## 6. Phase 5 — 채점 결과 페이지 (`/submissions/:id`)

### 6.1 SSE 진행 표시 (`GET /grade/{id}/events`)
- 페이지 진입 시 SSE 연결
- 상태별 UI: `queued` (대기 중 스피너) / `running` (테스트 진행률) / `done`·`failed` (스트림 종료)
- **순서 주의**: 페이지 들어오자마자 SSE 먼저 subscribe → 그 후 `GET /grade/{id}` snapshot 호출
  (snapshot 먼저 받으면 그 사이의 이벤트를 놓침. CLAUDE.md `api/grading.py:stream_grade_events` 주석 참고)

### 6.2 결과 표시 (`GET /grade/{id}`)
- 최종 verdict (AC / SUS) 큰 배너
- 테스트케이스별 결과 테이블 (pass/fail, 실행시간, 메모리)
- 앙상블 투표 카드 3개 (Melchior / Balthasar / Casper)
  - 각 judge의 verdict, intent_match, rationale, confidence
- 획득 포인트 (`points_awarded`)

### 6.3 튜터 패널
- `GET /tutor/{id}/history`로 기존 메시지 로드
- 비어있고 status가 `done`이면 자동으로 `POST /tutor/{id}` 호출 (선택사항)
- "AI 튜터 다시 묻기" 버튼 → `POST /tutor/{id}?regenerate=true`
- 마크다운 렌더링 (`react-markdown`)

---

## 7. Phase 6 — 대시보드 실데이터 연결

### 7.1 즉시 연동 가능
- `WeeklyProblemsCard` → `GET /problems` 데이터로 대체 (또는 별도 카드로 재구성)
- `Header`의 EXP 배지 → `/me` 데이터

### 7.2 백엔드 추가 필요 (당장은 mock 유지)
- `RecentSubmissionsCard`:
  - **필요 API**: `GET /me/submissions?limit=10`
  - **반환**: `Submission`의 일부 필드 + `Problem.title` join
  - **구현 위치**: `backend/src/api/me.py`에 추가 라우트
- `RankingCard`:
  - **필요 API**: `GET /ranking?limit=20`
  - **반환**: `[{rank, display_name, tier, exp}]`, `user`를 `exp DESC`로 정렬
  - **구현 위치**: 새 `backend/src/api/ranking.py`

이 두 API는 스키마 변경 없이 추가 가능 — Phase 6에서 백엔드 작업으로 분리해서 처리.

---

## 8. 의존성 추가 목록

```bash
# Phase 1
npm install react-router-dom

# Phase 4
npm install @monaco-editor/react

# Phase 5
npm install react-markdown
```

---

## 9. 작업 순서

```
Phase 1 (기반)        → api.ts, types.ts, react-router 셋업
Phase 2 (인증/유저)   → /me 연결, Header 프로필
Phase 3 (목록)        → /problems 페이지
Phase 4 (풀기)        → 에디터 + /grade 제출
Phase 5 (결과)        → SSE + 결과 + 튜터
Phase 6 (대시보드)    → /problems 데이터 + 신규 API 두 개 추가
```

핵심 사용자 시나리오 "문제 풀고 채점 결과 보기"는 Phase 5까지 완료되면 동작. Phase 6의 신규 API는 별도 작업으로 분리.

---

## 10. 주의사항

- **`MAX_CODE_LENGTH = 64KB`**: 에디터에서 클라이언트 측 길이 가드 추가
- **샌드박스 Python 전용**: 언어 선택 UI는 향후 기능으로 보류
- **SSE는 subscribe 먼저, snapshot 나중**: 결과 페이지에서 순서 지킬 것
- **CORS**: 백엔드는 `localhost:5173` 등록 완료 (`backend/src/main.py`)
- **JWT 만료**: Supabase access_token은 1시간 만료. `supabase.auth.onAuthStateChange`의 `TOKEN_REFRESHED` 이벤트로 자동 갱신되므로 매 요청마다 `getSession()`으로 최신 토큰 꺼내 쓸 것 (캐싱 금지)

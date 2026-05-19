# 출제 엔진 동작 가이드

JCodeQuest 출제 엔진(`authoring_engine/`)의 실행 방식과 파이프라인 흐름을 정리한 문서.

진입점은 두 가지 — **CLI**(`python -m authoring.main …`, 사람이 한 번 돌릴 때) / **HTTP 서버**(`uvicorn authoring.server:app …`, 대시보드/프론트에서 호출 + SSE로 진행 상황 스트리밍). 둘 다 결국 `authoring/pipeline/graph.py`의 동일한 LangGraph DAG를 호출한다.

> **핵심 아키텍처 변경**: 출제 엔진은 **DB나 샌드박스를 직접 다루지 않는다.** 문제 CRUD는 backend `/internal/*`로, 코드 실행은 judge_engine `/api/sandbox/run`으로 위임한다. 즉 출제 엔진을 띄우려면 **backend + judge_engine이 먼저 떠 있어야** 하고, 셋 모두 같은 `JCQ_INTERNAL_SECRET`을 공유해야 한다.

관련 문서:
- `docs/api-authoring-engine.md` — HTTP API 레퍼런스(요청/응답 스키마)ㅌ
- `docs/setup-ollama.md` — Ollama + 4모델(출제 1 + 판사 3) 풀 셋업
- `docs/environment.md` — backend 측 환경변수
- `docs/problem-format.md` — `Problem`/`IntentRubric`/`TestCase` 스키마
- `docs/authoring-prompt.md` — `draft_problem`/`author_solution` 프롬프트 사양

---

## 1. 사전 조건

| 항목 | 확인 |
|------|------|
| Python | 3.10+ |
| backend | `JCQ_BACKEND_URL`(기본 `http://127.0.0.1:8000`)로 응답하는 인스턴스가 떠 있어야 한다 (`/health` 200). |
| judge_engine | `JCQ_JUDGE_URL`(기본 `http://127.0.0.1:8002`)로 응답하는 인스턴스가 떠 있어야 한다 (`/api/health` 200). |
| `JCQ_INTERNAL_SECRET` | backend·judge_engine·authoring **셋이 같은 값**을 공유해야 한다. 출제 엔진은 이 토큰으로 backend `/internal/*`와 judge_engine `/api/sandbox/run`을 호출한다. 미설정 시 backend가 503으로 거부. |
| 원본 문제 | 변형의 모태가 될 `original_problem_id`가 backend DB에 존재해야 한다 — 출제 엔진은 fetch 단계에서 backend `/internal/problems/{id}`로 조회한다. |
| Ollama | `OLLAMA_BASE_URL`로 응답 가능. 3개 판사 모델 + 출제 모델 pull 완료. |

필요한 Ollama 모델 — 출제(generate/verify 재시도) + 3-judge 풀(judge_candidates, solve_candidates) + 비교(compare_to_original):

```bash
ollama pull qwen2.5-coder:14b-instruct-q5_K_M    # AUTHOR_MODEL + Melchior (judge/solver/compare)
ollama pull deepseek-coder-v2:lite               # Balthasar
ollama pull llama3.1:8b                          # Casper
```

`compare_to_original`은 Melchior 한 명만 호출하므로 모델은 출제용과 공용.

---

## 2. 설치

```bash
cd authoring_engine
python -m venv .venv
source .venv/bin/activate
pip install -e .                  # pyproject.toml 기반, jcq-shared도 file:로 함께 설치됨
```

shared 패키지(`jcq-shared`)는 `file:../shared`로 editable 설치된다. 출제 엔진은 **backend 소스를 직접 import하지 않으므로** sys.path 주입이나 백엔드 코드와의 동거가 더 이상 필요 없다 — 같은 호스트가 아니어도 `JCQ_BACKEND_URL`/`JCQ_JUDGE_URL`만 가리키면 동작한다.

---

## 3. 환경변수

`authoring_engine/.env`(또는 `env.sh`)에 작성. CLI/서버 진입점이 둘 다 `load_dotenv(authoring_engine/.env)`를 명시 호출하므로 `source` 없이도 `.env`만 있으면 동작은 한다. 백엔드와 같은 셸에서 일관성 있게 쓰려면 `env.sh.example`을 복사해 `source authoring_engine/env.sh`를 권장.

### 3.1 필수 — 내부 서비스 연결

| 변수 | 기본값 | 용도 |
|------|--------|------|
| `JCQ_BACKEND_URL` | `http://127.0.0.1:8000` | backend 베이스 URL. fetch/persist/notice 등 모든 DB 경로가 여기로 간다. |
| `JCQ_JUDGE_URL` | `http://127.0.0.1:8002` | judge_engine 베이스 URL. `verify_candidates`/`solve_candidates`가 `POST /api/sandbox/run` 호출. |
| `JCQ_INTERNAL_SECRET` | — | backend/judge 내부 라우트를 통과하기 위한 Bearer 토큰. **세 서비스가 모두 같은 값**으로 떠야 한다. |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama 엔드포인트. 사내 게이트웨이로 프록시되는 환경이면 `curl $OLLAMA_BASE_URL/api/tags`로 직접 확인한 값을 그대로 박을 것. |

### 3.2 필수(서버 모드 한정) — 관리자 인증/CORS

| 변수 | 기본값 | 용도 |
|------|--------|------|
| `JCQ_ADMIN_TOKEN` | — | `/api/health`를 제외한 모든 라우트(`/api/runs`, `/api/problems`, `/api/notices`, `/api/spans`, `/api/admin/*`)는 `Authorization: Bearer <token>` 요구. 미설정이면 503 fail-closed. |
| `JCQ_DASHBOARD_ORIGIN` | (unset) | 콤마 구분 origin 리스트. 별 도메인 대시보드에서 호출 시 CORS preflight 통과용. 미설정이면 동일 origin만 허용. |

> **SSE 주의**: 브라우저 `EventSource`는 `Authorization` 헤더를 보낼 수 없다. 대시보드에서 `/api/runs/{run_id}/events`를 직접 구독해야 한다면 query token 방식이나 fetch+stream 폴리필이 별도로 필요하다.

### 3.3 선택 — LangSmith 트레이싱

값이 있을 때만 자동 활성화. CLI/서버 진입점이 `LANGCHAIN_*` 환경변수를 setdefault로 채워 LangChain 자동 트레이싱을 켠다.

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `LANGSMITH_API_KEY` | (unset) | 있으면 트레이싱 on. 빈 문자열은 미설정 취급. |
| `LANGSMITH_PROJECT` | `jcq-authoring` | 프로젝트 이름. |

> **두 가지를 구분할 것**:
> - **LangSmith 콘솔에서 trace 보기** — `LANGSMITH_API_KEY`만 있으면 CLI/서버 양쪽 모두 LangChain SDK가 자동 업로드. 콘솔의 프로젝트(`LANGSMITH_PROJECT`)에서 즉시 확인 가능.
> - **`ProblemRow.langsmith_trace_id` 컬럼에 trace ID 기록** — **서버 모드(`POST /api/runs`)에서만** 채워진다. 서버는 매 run마다 `trace_id = uuid4()`를 만들어 `RunnableConfig.run_id`와 state(`langsmith_trace_id`)에 동시에 박고, persist 단계가 그것을 backend로 전달해 DB에 저장한다. CLI는 그 주입을 하지 않아 컬럼은 NULL로 남는다 — 트레이싱 자체는 정상 동작.
> - DB row와 trace를 ID로 연결하고 싶으면 서버 모드를 쓸 것. CLI 결과를 trace와 매칭하려면 LangSmith 콘솔에서 시간·tags(`problem_{N}`)로 수동 매칭.

### 3.4 선택 — 파이프라인 튜닝 (`authoring/config.py`)

| 변수 | 기본값 | 영향 노드 |
|------|--------|-----------|
| `JCQ_AUTHOR_MODEL` | `qwen2.5-coder:14b-instruct-q5_K_M` | `generate_variants`, `verify_candidates`(재시도 시) |
| `JCQ_VARIANT_COUNT` | `5` | CLI `--count` 미지정 시 기본값 |
| `JCQ_AUTHOR_RETRIES` | `2` | `verify_candidates`가 reference_code를 재생성하는 최대 횟수 |
| `JCQ_JUDGE_PASS_THRESHOLD` | `0.7` | `judge_candidates` 통과 임계 (평균 score). 추가로 3 판사 중 2명 이상 `passed=true` 조건 같이 만족해야 함 |
| `JCQ_SOLVER_PASS_MIN_AC` | `1` | `solve_candidates` 통과 — 최소 몇 명의 풀이자가 AC를 받아야 하는지 |

### 3.5 작성 예시 — `authoring_engine/.env`

```bash
# 내부 서비스 (필수)
JCQ_BACKEND_URL=http://127.0.0.1:8000
JCQ_JUDGE_URL=http://127.0.0.1:8002
JCQ_INTERNAL_SECRET=change-me-shared-with-backend-and-judge
OLLAMA_BASE_URL=http://localhost:11434

# 서버 모드 (필수)
JCQ_ADMIN_TOKEN=change-me-admin-token
JCQ_DASHBOARD_ORIGIN=http://localhost:6010

# LangSmith (옵션 — 값이 있으면 자동 활성화)
# LANGSMITH_API_KEY=ls__...
# LANGSMITH_PROJECT=jcq-authoring

# 튜닝 (옵션)
# JCQ_VARIANT_COUNT=5
# JCQ_AUTHOR_RETRIES=2
# JCQ_JUDGE_PASS_THRESHOLD=0.7
# JCQ_SOLVER_PASS_MIN_AC=1
```

`env.sh.example`(`export …` 형식)을 복사해 `source authoring_engine/env.sh`로 적용해도 동일.

---

## 4. 파이프라인 LangGraph DAG

`authoring/pipeline/graph.py`가 컴파일하는 DAG는 7개 노드의 단일 경로:

```
fetch_problem
  → generate_variants
    → verify_candidates
      → judge_candidates
        → solve_candidates
          → compare_to_original
            → persist_approved → END
```

각 노드는 state(`AuthoringState` TypedDict, `authoring/schemas.py`)의 `candidates` 리스트를 갱신해 다음 노드로 넘긴다. 한 후보가 어느 단계에서 떨어지더라도 **state에서 제거되지 않고** "탈락 표식"만 갱신된 채 끝까지 흐른다 — 그래야 결과 표/SSE에서 어디서 떨어졌는지 확인할 수 있다.

### 4.1 `fetch_problem` (`pipeline/nodes/fetch.py`)

- backend `GET /internal/problems/{original_id}`로 원본 문제를, `GET /internal/problems/{id}/seeds?limit=3`으로 같은 카테고리의 approved 시드 최대 3개를 가져온다.
- backend가 이미 카테고리로 필터링하지만 다른 카테고리 시드가 흘러들어오면 변형 다양성 시그널이 오염되므로 여기서도 한 번 더 카테고리 불일치 시드를 거른다.
- 출력: `state["original_problem"]`, `state["seeds"]`.

### 4.2 `generate_variants` (`pipeline/nodes/generate.py`)

- 각 변형마다 **두 번의 LLM 호출**을 직렬 수행: `draft_problem`(문제 설계) → `author_solution`(레퍼런스 코드 + 테스트 stdin 생성). 둘 다 `JCQ_AUTHOR_MODEL`로.
- seed 풀은 `[original, *seeds]`. `i`번째 변형은 `i % len(seeds_all)` 만큼 rotate해서 매번 다른 seed가 첫 자리에 오도록 — 다양성 강화.
- `intent_rubric`은 `jcq_shared.schemas.IntentRubric.model_validate`로 즉시 검증, 실패 시 후보 폐기(state["errors"]에만 기록).
- 후보 dict(`CandidateProblem`)에 `verify_passed=False`, `judge_passed=False`, `solver_passed=False`, `saved_id=None` 등 게이트 플래그 초기화.

### 4.3 `verify_candidates` (`pipeline/nodes/verify.py`)

- `reference_code`를 각 `test_input.stdin`에 대해 judge_engine `POST /api/sandbox/run`으로 실행 → `expected_stdout`를 채움.
- 통과 기준:
  - `test_inputs`가 최소 4개 이상이어야 한다(`_MIN_TEST_CASES = 4`). 미달이면 즉시 fail.
  - 모든 케이스가 sandbox `status == "OK"`.
  - 각 케이스 실행 시간이 **time_limit_ms의 50% 이내**(`_PERF_RATIO = 0.5`). 50%를 넘으면 fail.
- 실패 시 최대 `JCQ_AUTHOR_RETRIES`회 동안 `author_solution` 프롬프트만 재호출해 `reference_code`+`test_inputs`를 재생성한 뒤 재시도. 재시도 횟수는 `c["verify_attempts"]`에 기록.
- 출력: `c["test_cases"]`(채워진 expected_stdout 포함), `c["verify_passed"]`, `c["verify_error"]`.

### 4.4 `judge_candidates` (`pipeline/nodes/judge.py`)

- `verify_passed`된 후보만 처리. 3-judge 앙상블(채점 앙상블과 같은 Melchior/Balthasar/Casper)이 **학생 코드가 아니라 문제 자체**의 품질을 4축 기준(명확성·의도 일관성·테스트 충분성·채점 가능성)으로 평가.
- 각 판사는 `{passed, score, rationale, issues}`를 반환. 통과 조건은 **두 가지를 모두** 만족:
  - 3명 중 2명 이상 `passed=true`
  - 3명 평균 `score >= JCQ_JUDGE_PASS_THRESHOLD`(기본 0.7)
- 한 판사라도 모델이 없거나 호출 실패면 `votes_passed=False`, `votes_score=0.0`로 처리되어 통과 임계 미달이 될 가능성이 커진다.
- 출력: `c["judge_passed"]`, `c["judge_score"]`(평균, 소수 셋째 자리 반올림), `c["judge_rationale"]`(`[Melchior] … | [Balthasar] … | [Casper] …`), `c["judge_issues"]`.

### 4.5 `solve_candidates` (`pipeline/nodes/solver.py`)

- `judge_passed`된 후보만 처리. **품질 심사와 동일한 3 LLM이 이번엔 풀이자 역할**로 문제를 직접 풀고, 그 코드를 judge_engine 샌드박스에서 실제 채점한다.
- 각 LLM은 statement + 샘플 케이스 2개를 받아 Python 코드를 출력. 마크다운 펜스를 자동 제거하고 모든 `test_cases` 케이스를 한 명씩 검증.
- 판정: 모든 케이스 통과면 `AC`, TLE/MLE/RE면 즉시 해당 verdict로 단축 종료, 그 외 한 케이스라도 출력 mismatch면 `FAIL`.
- 통과 조건: AC 받은 풀이자 수가 `JCQ_SOLVER_PASS_MIN_AC`(기본 1) 이상.
- 출력: `c["solver_results"]`(`[{judge_id, verdict, code, rationale}]`), `c["solver_passed"]`.

### 4.6 `compare_to_original` (`pipeline/nodes/compare.py`) — 게이트 아님

- **`solver_results`가 채워진(=solve_candidates까지 진입한) 후보에 한해** 단일 judge(Melchior, `qwen2.5-coder:14b-…`)가 원본과 변형을 비교해 3축 정량 점수를 매긴다. 3-judge 앙상블 아님 — 기록 목적이라 1회만.
- 3축(0.0~1.0 실수):
  - `hallucination_score` — 0=환각 없음, 1=심함. statement와 rubric/test_cases 모순, statement에 없는 제약 사용 등.
  - `intent_similarity` — 0=원본과 의도 무관, 1=동일 부류. 같은 알고리즘 카테고리·풀이 흐름 유지 여부.
  - `difficulty_similarity` — 0=난이도 크게 다름, 1=거의 동일. 복잡도 클래스·입력 범위·제한 비교.
- **persist는 이 결과를 보지 않는다** — 통과/탈락 판정은 오로지 `solver_passed`로만. 점수는 `authoring_meta.comparison`에 그대로 적혀 admin 대시보드용.
- 호출 실패 시 점수는 모두 `None`, `comparison_error`에 메시지 기록.

### 4.7 `persist_approved` (`pipeline/nodes/persist.py`)

- `solver_passed=True`인 후보만 backend `POST /internal/problems`로 `status="approved"`로 저장. 그 외 후보는 state에 남되 저장되지 않는다.
- 저장 시 함께 채워지는 필드:
  - `parent_id` = `original_problem_id`
  - `langsmith_trace_id` = 서버 모드에서 주입된 UUID(CLI 모드는 None)
  - `iso_week` = 파이프라인 진입 시점 한 번 계산된 ISO 주차 라벨(`YYYY-Www`). 노드 진입 시 한 번 계산하므로 자정/주차 경계를 가로질러도 한 배치의 변형은 동일 주차로 묶인다.
  - `authoring_meta` = 후보별 진단 정보 dict (아래 구조)

`authoring_meta` 구조 (저장 시점에 작성, backend에는 opaque JSON):

```json
{
  "candidate_index": 0,
  "judge_score": 0.83,
  "judge_passed": true,
  "judge_rationale": "[Melchior] ... | [Balthasar] ... | [Casper] ...",
  "judge_issues": [...],
  "solver_results": [{"judge_id":"Melchior","verdict":"AC","code":"...","rationale":"6/6 케이스 통과"}, ...],
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
}
```

---

## 5. CLI 실행 — `authoring/main.py`

```bash
cd authoring_engine
python -m authoring.main --problem-id 1 --count 5
```

### 5.1 옵션

| 플래그 | 기본값 | 설명 |
|--------|--------|------|
| `--problem-id` (필수) | — | 원본 문제 ID. backend `/internal/problems/{id}`에 없으면 fetch 단계에서 4xx로 실패 |
| `--count` | `5` | 생성 시도할 변형 수. 모두 통과한다는 보장은 없음 |

### 5.2 실행 단계

1. **Pre-flight 체크** (`_preflight_check`) — 다음을 순서대로 확인하고 하나라도 실패하면 즉시 종료:
   - `JCQ_INTERNAL_SECRET` 환경변수 설정 여부
   - `JCQ_BACKEND_URL/health` 200 응답
   - `JCQ_JUDGE_URL/api/health` 200 응답
   - `OLLAMA_BASE_URL` 환경변수(미설정 시 경고만)
2. **LangSmith 자동 설정** (`_setup_langsmith`) — `LANGSMITH_API_KEY`가 비어있지 않으면 트레이싱 on.
3. **`build_graph().invoke(initial_state)`** — LangGraph DAG를 동기 실행. `RunnableConfig`에 `run_name="authoring_pipeline"`, `tags=["authoring", f"problem_{problem_id}"]` 부착.
4. **결과 출력** (`_print_results`) — Rich 테이블로 각 후보의 단계별 통과 여부 표시:
   ```
   ┌───┬───────────┬──────┬──────┬──────────┬──────────┬─────────┐
   │ # │ 제목      │ 생성 │ 검증 │ 품질심사 │ 풀이검증 │ 저장 ID │
   ├───┼───────────┼──────┼──────┼──────────┼──────────┼─────────┤
   │ 0 │ 거듭제곱  │  ✓   │  ✓   │ ✓ 0.83   │ ✓ 3/3    │   42    │
   │ 1 │ 약수의 합 │  ✓   │  ✗   │   —      │   —      │   —     │
   │ ...                                                          │
   └─────────────────────────────────────────────────────────────┘
   저장 완료: 3개 → problem_id [42, 43, 45]
   ```
   비교 점수(`compare_to_original` 결과)는 콘솔 표에 표시되지 않고 `authoring_meta.comparison`에만 적힌다.

### 5.3 동작 비용 감각

- 변형 1건당 LLM 호출 수:
  - `generate_variants`: 2회 (draft + solution)
  - `verify_candidates`: 0~2회 추가(재시도 시 author_solution만 재호출)
  - `judge_candidates`: 3회 (3 판사)
  - `solve_candidates`: 3회 (3 풀이자)
  - `compare_to_original`: 1회 (Melchior 단독)
  - **합계 ≈ 9~11회** (재시도 없을 때 9회)
- 모델이 이미 로드돼 있는 경우(핫스타트): 변형 1건 ≈ **30~120초**. `--count 5`면 약 **3~10분**.
- 모델 콜드스타트: 14B / 16B-MoE 로딩에 모델당 30s~수 분 추가. 첫 호출만 무겁고 이후는 `keep_alive="30m"` 동안 유지.
- 권장: systemd에서 `OLLAMA_KEEP_ALIVE=24h`를 박아 모델 unload 자체를 막을 것 (`docs/setup-ollama.md` §2).

---

## 6. HTTP 서버 실행 — `authoring/server.py`

```bash
cd authoring_engine
uvicorn authoring.server:app --host 0.0.0.0 --port 8001
```

`scripts/dev.sh up`은 backend(:8000) → judge(:8002) → authoring(:8001) → frontend(:5173) 순으로 자동 기동한다. 출제 엔진을 단독으로 띄울 때는 backend·judge가 이미 떠 있는지 확인.

### 6.1 엔드포인트 요약

| 메서드 | 경로 | 인증 | 설명 |
|--------|------|------|------|
| `GET` | `/api/health` | 없음 | Liveness probe |
| `POST` | `/api/runs` | admin | `{problem_id, count}` → `{run_id, trace_id}` 즉시 반환, 백그라운드 스레드에서 파이프라인 시작 |
| `GET` | `/api/runs/{run_id}/events` | admin (SSE) | LangGraph `graph.stream()` 출력을 `update`/`done`/`error` 이벤트로 푸시 |
| `GET` | `/api/problems` | admin | `originals_only=true|false` 쿼리. 변형 통계 포함 요약 배열 |
| `GET` | `/api/problems/{id}` | admin | 상세(rubric, test_cases, authoring_meta 포함) |
| `POST` | `/api/problems` | admin | 원본 문제 1건 직접 등록(출제 엔진 우회, 운영자/시드 용도). `expected_stdout` 비면 sandbox로 자동 채움 |
| `DELETE` | `/api/problems/{id}` | admin | `cascade_children=true|false`. backend `DELETE /internal/problems/{id}`에 위임 |
| `GET` | `/api/problems/{id}/children` | admin | 해당 원본의 변형 목록(상세) |
| `GET` | `/api/notices` | admin | `limit=1..200`. backend `/internal/notices`에 위임 |
| `POST` `PATCH` `DELETE` | `/api/notices[/{id}]` | admin | 공지 CRUD — backend 위임 |
| `GET` | `/api/admin/problems/{id}/comparison` | admin | 단일 변형의 `comparison` 3축 점수 |
| `GET` | `/api/admin/originals/{id}/comparison` | admin | 한 원본의 모든 변형 비교 점수 + 평균/min/max 집계 |
| `GET` | `/api/spans/{trace_id}` | admin | LangSmith 스팬 트리(prompts/IO/tokens/latency) |

전수 스키마는 `docs/api-authoring-engine.md` 또는 서버의 `/docs` (Swagger UI).

### 6.2 호출 예시

```bash
ADMIN_TOKEN=$JCQ_ADMIN_TOKEN

# 1) 실행 시작
RUN=$(curl -sX POST localhost:8001/api/runs \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H 'content-type: application/json' \
  -d '{"problem_id": 1, "count": 3}')
echo "$RUN"
# {"run_id":"a1b2...","trace_id":"550e8400-e29b-..."}

RUN_ID=$(echo "$RUN" | jq -r .run_id)

# 2) 진행 상황 SSE 수신
curl -N -H "Authorization: Bearer $ADMIN_TOKEN" \
  localhost:8001/api/runs/$RUN_ID/events
# data: {"type":"update","data":{"fetch_problem":{...}}}
# data: {"type":"update","data":{"generate_variants":{...}}}
# ...
# data: {"type":"done","trace_id":"550e8400-..."}

# 3) 저장된 변형 확인
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
  localhost:8001/api/problems/1/children | jq

# 4) 비교 점수 집계
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
  localhost:8001/api/admin/originals/1/comparison | jq
```

### 6.3 SSE 이벤트 페이로드

- `{"type": "update", "data": {<node_name>: <node_output_dict>}}` — LangGraph `graph.stream()`이 매 노드 종료마다 푸시.
- `{"type": "done", "trace_id": "<uuid>"}` — 파이프라인 정상 종료.
- `{"type": "error", "message": "<ExceptionType>: <msg>"}` — 어딘가에서 예외 발생.

run state는 **메모리에만** 보관(`_runs: dict[str, asyncio.Queue]`, `routers/runs.py`). 서버 재시작 시 진행 중 run은 유실 — 저장된 결과만 backend DB에 남는다. 멀티 워커로 띄우면 sticky routing이 없으면 SSE가 다른 워커로 가서 404가 난다.

### 6.4 인증/CORS 동작

- 토큰 검증은 `authoring/admin_auth.py:require_admin`이 담당 — `JCQ_ADMIN_TOKEN` 미설정 시 503 fail-closed, 헤더 누락/형식 오류 401, 값 불일치 401(`hmac.compare_digest` timing-safe).
- CORS는 `JCQ_DASHBOARD_ORIGIN`에 명시된 콤마 구분 origin만 허용. 미설정이면 미들웨어 자체를 부착하지 않으므로 동일 origin 호출만 가능.

---

## 7. `scripts/verify_all.sh`로 한꺼번에 점검

backend + 출제 엔진 + judge_engine 샌드박스까지 E2E로 살아있는지 확인하는 통합 스크립트:

```bash
scripts/verify_all.sh                  # sandbox 경로까지 (LLM 미사용, 빠름)
scripts/verify_all.sh --with-llm       # Ollama 사용하는 경로 포함 — 출제 파이프라인까지
scripts/verify_all.sh --external       # 이미 떠 있는 서버에 attach만
```

기본 모드(`--with-llm` 없음)에선 출제 엔진의 DB 조회 API만 호출하고, 실제 파이프라인 실행은 LLM이 필요하므로 건너뛴다. `--with-llm`에선 `POST /api/runs` + SSE까지 확인.

---

## 8. 결과 확인

### 8.1 backend API로 변형 조회 (권장)

```bash
# 한 원본의 변형 + 비교 점수
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8001/api/problems/1/children | jq

# 비교 점수 집계만
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8001/api/admin/originals/1/comparison | jq
```

### 8.2 DB row의 핵심 필드

`ProblemRow`에 출제 엔진이 채우는 컬럼:

| 필드 | 의미 |
|------|------|
| `parent_id` | 원본 문제 ID. 수동 등록 원본은 NULL |
| `status` | `approved` 고정 (출제 엔진은 다른 상태로 저장하지 않음) |
| `langsmith_trace_id` | 서버 모드일 때만 — `/api/spans/{trace_id}`로 트레이스 조회 가능. CLI 모드는 NULL |
| `iso_week` | `YYYY-Www` (배치당 한 주차로 묶임) |
| `authoring_meta` | JSON — judge_score, judge_rationale, solver_results, verify_attempts, comparison(3축 점수) 등 사후 분석용 메타 |

### 8.3 직접 SQL이 필요한 경우

backend가 Supabase PostgreSQL을 쓰므로 `psql $JCQ_DB_URL` 또는 Supabase 콘솔에서:

```sql
SELECT
  id, parent_id, title,
  (authoring_meta->>'judge_score')::float AS judge_score,
  authoring_meta->'comparison'->>'hallucination_score' AS hallucination,
  authoring_meta->'comparison'->>'intent_similarity'  AS intent_sim,
  authoring_meta->'comparison'->>'difficulty_similarity' AS diff_sim
FROM problem
WHERE parent_id = 1;
```

테스트 모드(SQLite, `tests/conftest.py`가 임시 DB로 치환)일 때는 `JCQ_ALLOW_NON_POSTGRES=1`이 필요 — `backend/src/storage/db.py`가 부팅 시 강제한다.

---

## 9. 자주 부딪히는 함정

- **backend/judge가 안 떠 있다** — 출제 엔진은 더 이상 DB·sandbox를 직접 보지 않으므로 두 서비스가 떠 있지 않으면 fetch/verify/persist가 전부 실패한다. `scripts/dev.sh status`로 확인.
- **`JCQ_INTERNAL_SECRET`이 셋 다 다르다** — backend `/internal/*`는 토큰 불일치 시 401/403. 보통 한쪽 셸만 새로 띄우면서 변수를 빠뜨려 생긴다. `env | grep JCQ_INTERNAL_SECRET`을 backend·judge·authoring 셸 모두에서 같은 값으로.
- **`JCQ_ADMIN_TOKEN` 미설정** — 서버 모드의 `/api/health` 빼고는 모두 503. 토큰 자체를 설정한 뒤 클라이언트도 같은 값을 Bearer로 보내야 한다.
- **SSE가 401** — 브라우저 `EventSource`는 헤더를 못 보낸다. `curl -N -H 'Authorization: …'`나 fetch+ReadableStream 폴리필이 필요.
- **`Problem N not found`** — 원본 문제 ID가 backend DB에 없음. `curl -s -H "Authorization: Bearer $ADMIN_TOKEN" :8001/api/problems | jq` 로 확인.
- **Ollama 모델 누락** — `judge_candidates` / `solve_candidates`는 3 모델을 모두 호출하고, `compare_to_original`은 Melchior 1개만 호출한다. 하나라도 pull 안 돼 있으면 그 판사 표만 0점/`ERROR`로 기록되고 나머지는 그대로 진행 — 결과적으로 통과 임계 미달로 후보가 다 떨어질 수 있다. `ollama list`로 사전 확인.
- **첫 호출이 너무 느림** — 모델 cold start. `keep_alive="30m"`이 코드에 들어있지만 OS 메모리 압박이 있으면 swap된다. systemd로 `OLLAMA_KEEP_ALIVE=24h` 박는 게 안정적.
- **저장된 변형이 0개** — 단계별 로그(Rich 테이블 또는 SSE update 이벤트)로 어디서 떨어지는지 확인. 흔한 패턴:
  - `검증 ✗ test_inputs가 N개로 부족` → author_solution이 4개 미만의 케이스만 만들었다. `JCQ_AUTHOR_MODEL`을 더 큰 모델로 바꾸거나 `JCQ_AUTHOR_RETRIES`를 늘려보기.
  - `검증 ✗ 너무 느림 (Xms > Yms)` → reference_code가 제한시간의 50%를 넘김. complexity가 의도와 어긋난 풀이거나 입력 범위 과대 — 프롬프트 수정.
  - `품질심사 ✗` → 평균 score < 0.7 또는 2명 미만 pass. `JCQ_JUDGE_PASS_THRESHOLD`를 0.6 정도로 일시 완화하거나 프롬프트 튜닝.
  - `풀이검증 ✗ 0/3` → 3 LLM 모두 풀지 못함. 너무 어렵거나 statement가 모호. `JCQ_SOLVER_PASS_MIN_AC=1`인데도 0이면 의미상 풀이 불가능한 문제 — `authoring_meta.solver_results`의 rationale을 읽어보면 LLM이 어디서 막혔는지 보인다.
- **`comparison`이 항상 null** — `compare_to_original` 노드는 `solver_results`가 채워진(=solve_candidates까지 진입한) 후보에만 실행된다. 앞 단계에서 떨어진 후보는 점수가 None으로 남는 게 정상. solver를 통과했는데도 null이면 Melchior 호출이 실패한 것 — `authoring_meta.comparison.error`를 확인.
- **LangSmith가 안 켜짐** — `LANGSMITH_API_KEY`가 빈 문자열이면 진입점이 setdefault만 하고 트레이싱은 활성화하지 않는다. `echo $LANGSMITH_API_KEY`로 확인.
- **서버 모드에서 진행 중 run이 사라짐** — `_runs`는 in-memory dict. 서버 재시작·크래시 시 유실. 장기 실행 보장이 필요하면 `python -m authoring.main`을 별도 프로세스로 띄우는 게 안전.

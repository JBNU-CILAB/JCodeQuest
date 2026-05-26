# LangSmith Tracing Guide

JCodeQuest가 LangSmith로 보내는 트레이스의 구조와, 각 트레이스를 구성하는 단계(span)를 정리한 문서.

## 개요

LLM을 호출하는 서비스는 **judge_engine(채점)** 과 **authoring_engine(출제)** 둘뿐이며, 각각 **별도의 LangSmith 프로젝트**로 트레이싱된다. backend의 튜터(`/tutor`)는 LangChain이 아닌 OpenAI SDK를 직접 쓰므로 **트레이싱되지 않는다**.

| 서비스 | 루트 run 이름 | 프로젝트(기본값) | `.env.docker` 프로젝트 |
|--------|---------------|------------------|------------------------|
| judge_engine | `judge.grade_job` | `jcq-judge` | `JCodeQuestJudgeTrackingDashboard` |
| authoring_engine | `authoring_pipeline` | `jcq-authoring` | `JCodeQuestAuthoringTrackingDashboard` |
| backend (tutor) | — (미추적) | — | — |

두 프로젝트는 완전히 분리되어 있다. 출제 트레이스는 `trace_id`로 DB와 연결되지만(아래 §4), 채점 트레이스는 DB에 연결고리가 없고 LangSmith UI에서 태그/메타데이터(`submission_id`)로만 찾는다.

## 1. 트레이싱 활성화 조건

세 곳 모두 동일한 패턴 — `LANGSMITH_API_KEY`가 **있을 때만** 자동 트레이싱이 켜진다. 키가 없으면 `@traceable`과 LangGraph 트레이싱은 전부 no-op이 되므로, 비활성 환경에서도 코드는 그대로 안전하게 돈다.

- judge_engine: `judge_engine/judge/server.py:36-40` — ensemble import **이전에** 환경변수 세팅
- authoring_engine(서버): `authoring_engine/authoring/server.py:25-29`
- authoring_engine(CLI): `authoring_engine/authoring/main.py:64-74`(`_setup_langsmith`), 진입점에서 호출

```python
if os.getenv("LANGSMITH_API_KEY"):
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")
    os.environ.setdefault("LANGCHAIN_API_KEY", os.environ["LANGSMITH_API_KEY"])
    os.environ.setdefault("LANGCHAIN_PROJECT", os.getenv("LANGSMITH_PROJECT", "jcq-judge"))
```

> **주의(judge_engine)**: `LANGCHAIN_*`는 import 시점에 읽히므로, `server.py`는 위 설정을 **`ensemble`/`jobs` import보다 먼저** 실행한다. 이 순서를 깨면 트레이싱이 누락된다.

`.env.docker`에서는 judge/authoring가 각자 다른 키·프로젝트를 받도록 매핑돼 있다(`docker-compose.yml`):

```yaml
# judge
LANGSMITH_API_KEY: "${LANGSMITH_API_KEY_JUDGE:-}"
LANGSMITH_PROJECT: "${LANGSMITH_PROJECT_JUDGE:-jcq-judge}"
# authoring
LANGSMITH_API_KEY: "${LANGSMITH_API_KEY_AUTHORING:-}"
LANGSMITH_PROJECT: "${LANGSMITH_PROJECT_AUTHORING:-jcq-authoring}"
```

## 2. 채점 트레이스 — `judge.grade_job`

채점 1건(= 제출 1건)이 하나의 트레이스다. 워커가 큐에서 잡을 꺼내 실행할 때 생성된다.

```
judge.grade_job                         (root, run_type=chain)   ← jobs.py:46
├─ (sandbox 실행 — span 아님)            ← jobs.py:53-59
├─ judge.Melchior                        (child, LLM)             ← ensemble.py:_ask
├─ judge.Balthasar                       (child, LLM)
└─ judge.Casper                          (child, LLM)
```

### 루트 span: `judge.grade_job`

`judge_engine/judge/jobs.py:46`의 `@traceable(name="judge.grade_job", run_type="chain")`. 메타데이터/태그는 호출부(`jobs.py:83-94`)에서 `langsmith_extra`로 주입한다.

| 항목 | 값 |
|------|-----|
| name | `judge.grade_job` |
| run_type | `chain` |
| tags | `["judge", "problem:{problem_id}"]` |
| metadata | `submission_id`, `problem_id`, `problem_title` |

### 자식 span: 3-judge 앙상블

`ensemble.py:vote()`가 세 판사를 **순차 호출**하고, 각 `_ask()`가 자식 span 하나를 만든다(`ensemble.py`의 `cfg`). 샌드박스 테스트가 **전부 통과한 경우에만** 호출된다 — 하나라도 실패하면 앙상블은 돌지 않으므로 자식 span이 없다.

| 판사 | span 이름 | 모델(기본값) | 페르소나 |
|------|-----------|--------------|----------|
| Melchior | `judge.Melchior` | `JCQ_ENSEMBLE_MODEL_MELCHIOR` (`qwen2.5-coder:14b-instruct-q5_K_M`) | 엄격한 채점관 |
| Balthasar | `judge.Balthasar` | `JCQ_ENSEMBLE_MODEL_BALTHASAR` (`deepseek-coder-v2:lite`) | 코드 리뷰어 |
| Casper | `judge.Casper` | `JCQ_ENSEMBLE_MODEL_CASPER` (`llama3.1:8b`) | 출제자 의도 분석가 |

각 자식 span에 붙는 정보:
- **tags**: `["judge:{judge_id}", "model:{model}"]` (예: `judge:Melchior`, `model:qwen2.5-coder:14b-instruct-q5_K_M`)
- **metadata**: `judge_id`, `model`, `submission_id`

판정은 2/3 이상 AC면 최종 AC(`AC_RATIO_THRESHOLD = 2/3`). 투표 결과 자체는 각 LLM span의 output에 구조화 JSON(`verdict`/`intent_match`/`rationale`/`confidence`)으로 남는다.

> `JCQ_SKIP_ENSEMBLE=1`이면 앙상블을 건너뛰고 stub AC를 즉시 반환하므로(`jobs.py:_stub_ensemble`), **자식 LLM span이 생성되지 않는다.**

### 추적되지 않는 부분

- **샌드박스 실행**: `asyncio.to_thread(run_all_tests, ...)`(`jobs.py:53`)는 별도 LLM/Runnable이 아니라 워커 스레드의 순수 파이썬 실행이라 독립 span이 아니다. 테스트 결과는 루트 span의 입출력으로만 보인다.

## 3. 출제 트레이스 — `authoring_pipeline`

출제 파이프라인 1회 실행이 하나의 트레이스다. LangGraph가 **노드마다 자동으로 span**을 만들고, 노드 안의 각 `ChatOllama.invoke()`가 그 아래 LLM span으로 묶인다.

루트 span은 그래프 invoke 시 `RunnableConfig`로 지정한다:
- CLI: `authoring/main.py:140-144` — `run_name="authoring_pipeline"`, `tags=["authoring", "problem_{id}"]`
- 서버: `authoring/routers/runs.py:43-64` — 동일 + **`run_id`를 미리 발급한 `trace_id`(UUID)로 고정**(조회용, §4)

```
authoring_pipeline                       (root)
├─ fetch_problem                         (LLM 없음 — 원본 문제 fetch)
├─ retrieve_exemplars                    (LLM 없음 — 카테고리 임베딩 MMR로 grounding 형제 선별)
├─ generate_variants                     (변형당 LLM 2회: draft_problem → author_solution)
├─ verify_candidates                     (샌드박스 검증 + 실패 시 재생성 LLM)
├─ judge_candidates                      (후보당 LLM 3회 — 품질 심사, 점수 중앙값)
│   ├─ judge_quality/Melchior            (JCQ_JUDGE_SAMPLES>1이면 judge_quality/Melchior#1, #2 …)
│   ├─ judge_quality/Balthasar
│   └─ judge_quality/Casper
├─ solve_candidates                      (후보당 LLM 3회 — 풀이 가능성 검증)
├─ attack_candidates                     (후보당 LLM N회 — 테스트 변별력 게이트, Melchior 단독)
│   ├─ attack/naive
│   └─ attack/edge_skip
├─ compare_to_original                   (후보당 LLM 1회 — Melchior 단독, 환각/의도 게이트)
│   └─ compare_to_original/Melchior
└─ persist_approved                      (LLM 없음 — DB 저장 + trace_id 기록)
```

### 노드별 상세

| 노드 | 파일 | LLM 호출 | 자식 span 이름 | 비고 |
|------|------|----------|----------------|------|
| `fetch_problem` | `nodes/fetch.py` | 없음 | — | backend API로 원본 문제 조회 |
| `retrieve_exemplars` | `nodes/retrieve.py` | 없음 | — | 카테고리 임베딩을 MMR로 골라 grounding 형제를 `generate`에 주입 |
| `generate_variants` | `nodes/generate.py` | 변형당 2회 | (명시 이름 없음) | `draft_problem`→`author_solution` 순차 |
| `verify_candidates` | `nodes/verify.py` | 재시도 시에만 | (명시 이름 없음) | reference_code를 샌드박스 실행해 expected_stdout 채움. 실패 시 최대 `JCQ_AUTHOR_RETRIES`회 재생성 |
| `judge_candidates` | `nodes/judge.py` | 후보당 3회 | `judge_quality/{judge_id}` | 문제 품질 4축 심사. 2/3 pass + **중앙값** score ≥ `JCQ_JUDGE_PASS_THRESHOLD` |
| `solve_candidates` | `nodes/solver.py` | 후보당 3회 | (명시 이름 없음) | 3 LLM이 직접 문제를 풀어 풀이 가능성 검증. `JCQ_SOLVER_PASS_MIN_AC`개 이상 AC면 통과 |
| `attack_candidates` | `nodes/attack.py` | 후보당 N회 | `attack/{strategy}` | Melchior 단독. 결함 풀이로 테스트 변별력 검사 — `JCQ_DISCRIMINATION_MIN_REJECT`개 이상 탈락시키면 통과(게이트) |
| `compare_to_original` | `nodes/compare.py` | 후보당 1회 | `compare_to_original/{judge_id}` | Melchior 단독. 원본 대비 hallucination/의도/난이도 유사도 기록 + 환각·의도유사도를 게이트로 적용 |
| `persist_approved` | `nodes/persist.py` | 없음 | — | solver·변별력·compare 3게이트를 모두 통과한 후보를 `parent_id`+`langsmith_trace_id`로 DB 저장 |

- 출제 엔진의 3-LLM 앙상블(`judge`/`solve`)과 `attack`/`compare`(Melchior 단독)는 채점 엔진과 **같은 `JCQ_ENSEMBLE_MODEL_*` 환경변수**를 공유한다(`authoring/config.py:ENSEMBLE_MODELS`). 즉 `.env.docker` 한 곳에서 두 엔진의 판사진을 동시에 제어한다.
- `judge_candidates`·`attack_candidates`·`compare_to_original`만 `RunnableConfig(run_name=...)`로 자식 span 이름을 명시하고, `generate`/`verify`/`solve`의 LLM 호출은 LangGraph 기본 이름으로 잡힌다.
- 샌드박스 실행(`sandbox_run()` → judge_engine HTTP 호출)은 LLM span이 아니라 노드 내부 동작으로만 보인다.

## 4. trace_id 캡처 & 조회

출제 트레이스는 LangSmith UI 밖에서도 추적할 수 있도록 `trace_id`를 문제 레코드에 박아둔다.

**캡처 흐름**:
1. 서버가 실행 시작 시 `trace_id = uuid4()`를 발급(`routers/runs.py:79-89`), 클라이언트에 `RunResponse.trace_id`로 반환.
2. 같은 UUID를 `RunnableConfig(run_id=...)`로 그래프에 고정 → LangSmith 루트 run id와 일치(`routers/runs.py:58`).
3. 동시에 state의 `langsmith_trace_id`로도 주입.
4. `persist_approved`가 그 값을 읽어 `create_problem(..., langsmith_trace_id=trace_id)`로 저장(`nodes/persist.py`).
5. backend의 `ProblemRow.langsmith_trace_id`(인덱스 컬럼)에 영속화.

**조회**: `GET /api/spans/{trace_id}` (`authoring/routers/spans.py`)
- `LANGSMITH_API_KEY`가 없으면 503.
- `langsmith.Client().list_runs(project_name=..., trace_id=...)`로 run 트리를 가져온다. 프로젝트는 `LANGSMITH_PROJECT`(기본 `jcq-authoring`) — 즉 **authoring 프로젝트만** 조회 가능, 채점 트레이스는 다른 프로젝트라 이 엔드포인트로 못 본다.
- 반환 구조:
  - `trace_id`, `project`
  - `summary`: `span_count`, `total_tokens`, `prompt_tokens`, `completion_tokens`, `root_latency_seconds`
  - `spans[]`: span별 `id`, `parent_run_id`, `name`, `run_type`, `status`, `start_time`/`end_time`, `latency_seconds`, `tokens`(prompt/completion/total), `cost`, `inputs`, `outputs`, `error`, `extra`(metadata), `tags` — `start_time` 오름차순 정렬.

## 5. 추적되지 않는 것

| 대상 | 위치 | 이유 |
|------|------|------|
| 튜터 LLM | `backend/src/tutor/client.py`, `api/tutor.py` | OpenAI SDK 직접 호출(LangChain 아님). `@traceable`/`RunnableConfig` 없음. 결과는 DB 이력에만 저장 |
| 샌드박스 채점 실행 | judge_engine `run_all_tests`, authoring `sandbox_run` | LLM/Runnable이 아닌 순수 실행 — 부모 노드 span에 흡수 |

## 빠른 참조

| span | 서비스 | 종류 | 이름 | 트리거 |
|------|--------|------|------|--------|
| `judge.grade_job` | judge | root/chain | 고정 | 제출 채점 1건 |
| `judge.{Melchior\|Balthasar\|Casper}` | judge | LLM child | per-judge | 전 테스트 통과 시 |
| `authoring_pipeline` | authoring | root | 고정 | 출제 파이프라인 1회 |
| `generate_variants` | authoring | node | 고정 | 변형 생성(LLM 2회/변형) |
| `judge_quality/{judge_id}` | authoring | LLM child | per-judge | 품질 심사(점수 중앙값) |
| `attack/{strategy}` | authoring | LLM child | Melchior | 테스트 변별력 검사 |
| `compare_to_original/{judge_id}` | authoring | LLM child | Melchior | 원본 비교(환각/의도 게이트) |

## 관련 문서

- `docs/authoring-engine.md` — 출제 파이프라인 전체 동작
- `docs/setup-ollama.md` — 앙상블 Ollama 모델 설정
- `docs/environment.md` — `LANGSMITH_*` 환경변수

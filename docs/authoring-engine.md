# 출제 엔진 실행 가이드

JCodeQuest 출제 엔진(`authoring_engine/`)을 실행하는 방법과 그 흐름을 정리한 문서.

진입점은 두 가지 — **CLI**(사람이 직접 한 번 돌리는 용) / **HTTP 서버**(프론트엔드에서 호출 + SSE로 진행 상황 스트리밍). 둘 다 결국 `pipeline/graph.py`의 동일한 LangGraph DAG를 호출한다.

관련 문서:
- `docs/setup-ollama.md` — Ollama + 3-judge 모델 풀 셋업
- `docs/environment.md` — 백엔드 측 환경변수
- `docs/problem-format.md` — `Problem`/`IntentRubric`/`TestCase` 스키마
- `docs/authoring-prompt.md` — `draft_problem`/`author_solution` 프롬프트 사양

---

## 1. 사전 조건

| 항목 | 확인 |
|------|------|
| Python | 3.10+ (백엔드는 3.14+ 권장 — README 참조) |
| Ollama | 11434 포트로 떠 있고, 3개 판사 모델 + 출제 모델 pull 완료 |
| 백엔드 DB | `backend/data/jcq.db`가 이미 만들어져 있고 `Problem` 한 건 이상 시드됨 |
| 원본 문제 | 변형의 모태가 될 `original_problem_id`가 DB에 존재해야 함 |

DB가 없으면 백엔드를 한 번 띄워 `init_db()`를 돌리거나(`uvicorn src.main:app` 한 번 실행 후 종료), `python backend/migrate.py`로 마이그레이션 적용.

필요한 모델 (`authoring/config.py`, `pipeline/nodes/judge.py`, `pipeline/nodes/solver.py`):

```bash
ollama pull qwen2.5-coder:14b-instruct-q5_K_M    # AUTHOR_MODEL + Melchior
ollama pull deepseek-coder-v2:lite               # Balthasar
ollama pull llama3.1:8b                          # Casper
```

---

## 2. 설치

```bash
cd authoring_engine
python -m venv .venv
source .venv/bin/activate
pip install -e .                  # pyproject.toml 기반, jcq-shared도 file: 로 함께 설치됨
```

백엔드와 venv를 공유해도 무방하다 — `pyproject.toml`의 의존성은 백엔드와 충돌하지 않게 맞춰져 있다. 다만 출제 엔진은 백엔드의 `src.storage`/`src.judge.sandbox`를 `sys.path` 주입으로 직접 import하므로, 백엔드 코드가 같은 트리에 존재해야 한다.

---

## 3. 환경변수

`authoring_engine/.env`(또는 `env.sh`)에 작성. 백엔드와 달리 출제 엔진은 **진입 시점에 `load_dotenv()`를 직접 호출**하므로 `source` 없이도 `.env`만 있으면 동작은 하지만, 백엔드와 같은 셸에서 일관성 있게 쓰려면 `env.sh.example`을 복사해 source하는 쪽이 안전하다.

### 필수

| 변수 | 용도 | 비고 |
|------|------|------|
| `JCQ_DB_URL` | 백엔드와 **반드시 같은** SQLite 경로 | 절대경로 권장 (`sqlite:////abs/path/jcq.db`). 미설정 시 `config.ensure_backend_on_path()`가 `backend/data/jcq.db` 절대경로를 자동 주입 |
| `OLLAMA_BASE_URL` | Ollama 엔드포인트 | Ollama 기본 포트는 `11434`지만 환경에 따라 다를 수 있다(예: 사내 게이트웨이가 `:8080`으로 프록시). **`curl $OLLAMA_BASE_URL/api/tags`로 직접 확인**한 값을 그대로 박을 것 |

### 선택 — LangSmith 트레이싱

값이 있을 때만 자동 활성화. CLI/서버 진입점이 `LANGCHAIN_*` 환경변수를 setdefault로 채워 LangChain 자동 트레이싱을 켠다.

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `LANGSMITH_API_KEY` | (미설정) | 있으면 트레이싱 on |
| `LANGSMITH_PROJECT` | `jcq-authoring` | 프로젝트 이름 |

> **두 가지를 구분할 것**:
> - **LangSmith 콘솔에서 trace 보기** — `LANGSMITH_API_KEY`만 있으면 CLI/서버 양쪽 모두 LangChain SDK가 자동 업로드. 콘솔의 프로젝트(`LANGSMITH_PROJECT`)에서 즉시 확인 가능.
> - **`ProblemRow.langsmith_trace_id` 컬럼에 trace ID 기록** — **서버 모드(`POST /api/runs`)에서만** 채워진다. 서버는 매 run마다 `trace_id = uuid4()`를 만들어 `RunnableConfig.run_id`와 state에 동시에 박고, persist 단계가 그걸 DB에 저장한다. CLI는 그 주입을 하지 않아 컬럼은 NULL로 남는다 — 트레이싱 자체는 정상 동작.
> - DB row와 trace를 ID로 연결하고 싶으면 서버 모드를 쓸 것. CLI 결과를 trace와 매칭하려면 LangSmith 콘솔에서 시간·tags(`problem_{N}`)로 수동 매칭.

### 선택 — 파이프라인 튜닝 (`authoring/config.py`)

| 변수 | 기본값 | 영향 노드 |
|------|--------|-----------|
| `JCQ_AUTHOR_MODEL` | `qwen2.5-coder:14b-instruct-q5_K_M` | `generate_variants`, `verify_candidates`(재시도 시) |
| `JCQ_VARIANT_COUNT` | `5` | CLI `--count` 미지정 시 기본값 |
| `JCQ_AUTHOR_RETRIES` | `2` | `verify_candidates`가 reference_code를 재생성하는 최대 횟수 |
| `JCQ_JUDGE_PASS_THRESHOLD` | `0.7` | `judge_candidates` 통과 임계 (평균 score) |
| `JCQ_SOLVER_PASS_MIN_AC` | `1` | `solve_candidates` 통과 — 최소 몇 명의 풀이자가 AC를 받아야 하는지 |

### 작성 예시 — `authoring_engine/.env`

```bash
JCQ_DB_URL=sqlite:////home/<you>/JCodeQuest/backend/data/jcq.db
OLLAMA_BASE_URL=http://localhost:11434

# LangSmith (옵션 — 값이 있으면 자동 활성화)
# LANGSMITH_API_KEY=ls__...
# LANGSMITH_PROJECT=jcq-authoring

# 튜닝 (옵션)
# JCQ_VARIANT_COUNT=5
# JCQ_JUDGE_PASS_THRESHOLD=0.7
# JCQ_SOLVER_PASS_MIN_AC=1
```

`env.sh.example` 형식으로 쓰고 싶으면 그쪽 템플릿을 복사해서 `source authoring_engine/env.sh`로 적용.

---

## 4. CLI 실행 — `authoring/main.py`

원본 문제 한 건을 받아 변형 N개를 만들고, 통과한 것만 DB에 `approved`로 저장한다.

```bash
cd authoring_engine
python -m authoring.main --problem-id 1 --count 5
```

### 옵션

| 플래그 | 기본값 | 설명 |
|--------|--------|------|
| `--problem-id` (필수) | — | 원본 문제 ID. DB에 없으면 즉시 종료 |
| `--count` | `5` | 생성 시도할 변형 수. 모두 통과한다는 보장은 없음 |

### 실행 단계

1. **Pre-flight 체크** (`_preflight_check`)
   - `JCQ_DB_URL`이 상대경로면 경고, 파일 없으면 fail-fast.
   - `OLLAMA_BASE_URL` 미설정 시 경고 (기본값 사용).
2. **LangSmith 자동 설정** (`_setup_langsmith`) — `LANGSMITH_API_KEY`가 있으면 트레이싱 on.
3. **`build_graph().invoke(initial_state)`** — LangGraph DAG를 동기 실행.
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

### 동작 비용 감각

- 변형 1건당 LLM 호출: `draft_problem` 1회 + `author_solution` 1~3회(재시도) + `judge_candidates` 3회 + `solve_candidates` 3회 ≈ **8~10회**.
- 모델이 이미 로드돼 있는 경우(핫스타트): 변형 1건 ≈ **30~90초**. `--count 5`면 약 **3~8분**.
- 모델이 내려가 있는 경우(콜드스타트): 14B / 16B-MoE 로딩에 **모델당 30s~수 분** 추가. 첫 호출만 무겁고 이후는 keep_alive(`30m`) 동안 유지됨.
- 권장: systemd에서 `OLLAMA_KEEP_ALIVE=24h` 박아 모델 unload 자체를 막을 것 (`docs/setup-ollama.md` §2).

---

## 5. HTTP 서버 실행 — `authoring/server.py`

프론트엔드에서 출제를 트리거하고 SSE로 진행 상황을 받으려면 서버 모드로 띄운다.

```bash
cd authoring_engine
uvicorn authoring.server:app --host 0.0.0.0 --port 8001
```

백엔드 메인 서버(`8000`)와 포트가 겹치지 않게 다른 포트 사용. `verify_all.sh`는 자동으로 두 서버를 다른 포트로 띄운다.

### 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET`  | `/api/health` | 헬스체크 |
| `POST` | `/api/runs` | `{problem_id, count}` → `{run_id, trace_id}` 즉시 반환, 백그라운드 스레드에서 파이프라인 시작 |
| `GET`  | `/api/runs/{run_id}/events` | SSE — `{type: "update" \| "done" \| "error", ...}` 이벤트 스트림 |
| `GET`  | `/api/problems?originals_only=true` | 원본 문제 목록 + 자식(변형) 통계 |
| `GET`  | `/api/problems/{id}` | 문제 상세 (intent_rubric, test_cases, authoring_meta 포함) |
| `GET`  | `/api/problems/{id}/children` | 해당 원본의 변형 목록 |
| `GET`  | `/api/spans/{trace_id}` | LangSmith 스팬 트리 (prompts/IO/tokens/latency) |

### 호출 예시

```bash
# 1) 실행 시작
RUN=$(curl -sX POST localhost:8001/api/runs \
  -H 'content-type: application/json' \
  -d '{"problem_id": 1, "count": 3}')
echo "$RUN"
# {"run_id":"a1b2...","trace_id":"550e8400-e29b-..."}

RUN_ID=$(echo "$RUN" | jq -r .run_id)

# 2) 진행 상황 SSE 수신
curl -N localhost:8001/api/runs/$RUN_ID/events
# event: message
# data: {"type":"update","data":{"fetch_problem":{...}}}
# event: message
# data: {"type":"update","data":{"generate_variants":{...}}}
# ...
# event: message
# data: {"type":"done","trace_id":"550e8400-..."}

# 3) 저장된 변형 확인
curl -s localhost:8001/api/problems/1/children | jq
```

### SSE 이벤트 페이로드

- `{"type": "update", "data": {<node_name>: <node_output_dict>}}` — LangGraph `graph.stream()`이 매 노드 종료마다 푸시.
- `{"type": "done", "trace_id": "<uuid>"}` — 파이프라인 정상 종료.
- `{"type": "error", "message": "<ExceptionType>: <msg>"}` — 어딘가에서 예외 발생.

run state는 **메모리에만** 보관(`_runs: dict[str, asyncio.Queue]`). 서버 재시작 시 진행 중 run은 유실 — 저장된 결과만 DB에 남는다.

---

## 6. `scripts/verify_all.sh`로 한꺼번에 점검

백엔드 + 출제 엔진 + 샌드박스 채점까지 E2E로 살아있는지 확인하는 통합 스크립트:

```bash
scripts/verify_all.sh                  # sandbox 경로까지 (LLM 미사용, 빠름)
scripts/verify_all.sh --with-llm       # Ollama/OpenAI 사용하는 경로 포함
scripts/verify_all.sh --external       # 이미 떠 있는 서버에 attach만
```

기본 모드(`--with-llm` 없음)에선 출제 엔진의 DB 조회 API만 호출하고, 실제 파이프라인 실행은 LLM이 필요하므로 건너뛴다. `--with-llm`에선 `POST /api/runs` + SSE까지 확인.

---

## 7. 결과 확인

### DB에 저장된 변형 찾기

저장된 row는 `ProblemRow`에 다음 필드가 채워져 있다:

| 필드 | 의미 |
|------|------|
| `parent_id` | 원본 문제 ID (수동 등록 문제는 NULL) |
| `status` | `approved` (출제 엔진은 항상 approved로 저장) |
| `langsmith_trace_id` | 서버 모드일 때만 — `/api/spans/{trace_id}`로 트레이스 조회 가능 |
| `authoring_meta` | JSON — judge_score, judge_rationale, solver_results, verify_attempts 등 사후 분석용 메타 |

SQLite로 직접 확인:

```bash
# sqlite3 CLI가 설치돼 있으면
sqlite3 backend/data/jcq.db \
  "SELECT id, parent_id, title, json_extract(authoring_meta, '$.judge_score') AS score \
   FROM problem WHERE parent_id = 1;"
```

`sqlite3` 바이너리가 없다면(많은 컨테이너/미니멀 환경에서 기본 부재) `apt install sqlite3` 또는 Python 폴백 사용:

```bash
.venv/bin/python -c "
import json, sqlite3
cur = sqlite3.connect('backend/data/jcq.db').cursor()
cur.execute('SELECT id, parent_id, title, authoring_meta FROM problem WHERE parent_id = 1;')
for pid, parent, title, meta in cur.fetchall():
    score = (json.loads(meta) if meta else {}).get('judge_score')
    print(f'{pid}\tparent={parent}\tscore={score}\t{title}')
"
```

### 자식 변형 조회 API

```bash
curl -s localhost:8001/api/problems/1/children | jq
```

---

## 8. 자주 부딪히는 함정

- **다른 DB를 보고 있음** — `JCQ_DB_URL`을 상대경로(`sqlite:///./data/jcq.db`)로 두면 셸 CWD에 따라 다른 파일을 만든다. 백엔드와 출제 엔진이 같은 절대경로를 가리키는지 매번 확인. `ensure_backend_on_path()`가 자동 fallback을 제공하지만, env에 명시적으로 박는 게 안전.
- **`Problem N not found`** — 원본 문제 ID가 DB에 없음. `sqlite3 ... "SELECT id, title FROM problem;"`로 확인.
- **Ollama 모델 누락** — `judge_candidates` / `solve_candidates`는 3개 모델을 모두 호출한다. 하나라도 pull 안 돼 있으면 그 판사 표만 0점/`ERROR`로 기록되고 나머지는 그대로 진행 — 결과적으로 통과 임계 미달로 후보가 다 떨어질 수 있다. `ollama list`로 사전 확인.
- **첫 호출이 너무 느림** — 모델 cold start. `keep_alive="30m"`이 코드에 들어있지만 OS 메모리 압박이 있으면 swap된다. systemd로 `OLLAMA_KEEP_ALIVE=24h` 박는 게 안정적.
- **저장된 변형이 0개** — 단계별 로그(Rich 테이블 또는 SSE update 이벤트)로 어디서 떨어지는지 확인. 흔한 패턴:
  - `검증 ✗` → reference_code가 timeout(제한시간의 50% 초과)이거나 stderr 발생. `JCQ_AUTHOR_MODEL`을 더 큰 모델로 바꾸거나 `JCQ_AUTHOR_RETRIES`를 늘려보기.
  - `품질심사 ✗` → 평균 score < 0.7. `JCQ_JUDGE_PASS_THRESHOLD`를 0.6 정도로 일시 완화하거나 프롬프트 튜닝.
  - `풀이검증 ✗ 0/3` → 문제가 너무 어렵거나 statement가 모호. `JCQ_SOLVER_PASS_MIN_AC=1`인데도 0이면 의미상 풀이 불가능한 문제 — `authoring_meta.solver_results`의 rationale을 읽어보면 LLM이 어디서 막혔는지 보인다.
- **LangSmith가 안 켜짐** — `LANGSMITH_API_KEY`가 빈 문자열이면 진입점이 setdefault만 하고 트레이싱은 활성화하지 않는다. `echo $LANGSMITH_API_KEY`로 확인.
- **서버 모드에서 진행 중 run이 사라짐** — `_runs`는 in-memory dict. 서버 재시작·크래시 시 유실. 장기 실행 보장이 필요하면 `python -m authoring.main`을 별도 프로세스로 띄우는 게 안전.

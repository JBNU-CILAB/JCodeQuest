# Testing Guide

JCodeQuest 백엔드 테스트의 구조와 실행 방법을 정리한 문서.

## 디렉터리 구조

```
backend/
├── pytest.ini               # asyncio_mode=auto, testpaths=tests
└── tests/
    ├── conftest.py          # 임시 SQLite DB 부트스트랩, 쿨다운 0 fixture, sample_problem
    ├── test_sandbox.py      # 샌드박스 단위(러너/리소스 한도/표준입출력)
    ├── test_storage.py      # 스토리지 단위(SubmissionRow CRUD, attempt_status)
    ├── test_jobqueue.py     # JobQueue 단위(워커 1, 워커 N, 종료)
    ├── test_cooldown.py     # 쿨다운 계산 단위 + API 429/Retry-After
    ├── test_pipeline.py     # POST /grade → 큐 → DB → GET/SSE E2E (LLM mock)
    ├── test_tutor.py        # POST /tutor/{id} 흐름 (OpenAI mock)
    ├── live/                # 실 Ollama·OpenAI 라이브 슈트 (gated)
    │   ├── conftest.py      # JCQ_RUN_LIVE_LLM gate, JSONL/MD 아티팩트 레코더
    │   ├── test_live_ensemble.py
    │   └── test_live_tutor.py
    ├── scripts/
    │   └── smoke_e2e.py     # 살아있는 uvicorn에 붙는 스모크 (pytest 아님)
    └── artifacts/           # 라이브 슈트 산출물 (.gitkeep만 추적)
```

## 테스트 계층

| 계층 | 위치 | 외부 의존 | 실행 |
|------|------|-----------|------|
| 단위 | `tests/test_*.py` 中 단위 케이스 | 없음 | `pytest -q` |
| 통합 | `tests/test_pipeline.py`, `tests/test_tutor.py` 등 | FastAPI TestClient + 임시 SQLite | `pytest -q` |
| 라이브 LLM | `tests/live/` | Ollama / OpenAI 실 호출 | `JCQ_RUN_LIVE_LLM=1 pytest tests/live` |
| 스모크 | `tests/scripts/smoke_e2e.py` | 떠있는 uvicorn + LLM | `python tests/scripts/smoke_e2e.py` |

## 실행

환경변수는 자동 로드되지 않으므로 호출 전에 `backend/env.sh`를 source해야 한다 — 작성법은 `docs/environment.md` 참조.

기본 슈트 (외부 의존 없음, 빠름):

```bash
cd backend
source env.sh
.venv/bin/pytest -q
```

라이브 LLM 슈트 (느림, 비결정적):

```bash
source backend/env.sh
JCQ_RUN_LIVE_LLM=1 .venv/bin/pytest tests/live -v -s
```

라이브 슈트는 `JCQ_RUN_LIVE_LLM` 환경변수가 1이고 Ollama 엔드포인트가 살아있을 때만 수집된다 — 그 외엔 모듈 단위로 skip되므로 일반 `pytest` 실행에 영향 없음.

스모크 (살아있는 서버 대상):

```bash
# 터미널 A
source backend/env.sh
.venv/bin/uvicorn src.main:app

# 터미널 B — **같은 env.sh를 source한 셸**이어야 DB 위치가 일치
source backend/env.sh
.venv/bin/python backend/tests/scripts/smoke_e2e.py
```

## 격리 규약

테스트 슈트가 의존하는 fixture들은 `tests/conftest.py`에 모여있다.

- **임시 SQLite**: `_bootstrap_db` (session, autouse)가 `JCQ_DB_URL`을 임시 파일로 박고 `init_db()` 호출. 슈트 종료 후 unlink.
- **쿨다운 무력화**: `_disable_cooldown` (autouse)가 `SUBMISSION_COOLDOWN_S=0`으로 monkeypatch. 쿨다운 자체를 검증하는 케이스는 자기 fixture에서 다시 켠다(`test_cooldown.py` 참조).
- **시드 문제**: `sample_problem` (Problem 객체) / `seeded_problem_id` (DB에 INSERT 후 id 반환).

## LLM 의존 제거 패턴

통합 테스트는 LLM 호출을 monkeypatch로 갈아끼운다. 패치 대상은 **호출자 모듈**(`src.judge.jobs.grading`, `src.tutor.client` 등)에 import된 심볼이지, 정의 모듈이 아니다.

```python
import src.judge.jobs.grading as grading_mod
async def fake_vote(problem, code, test_results, base_url=None):
    return _fake_ac()
monkeypatch.setattr(grading_mod, "vote", fake_vote)
```

## 라이브 슈트 아티팩트

`tests/live/` 슈트는 매 시나리오를 즉시 flush해서 `tests/artifacts/`에 기록한다.

- `live_llm_<timestamp>.jsonl` — 시나리오별 raw 레코드. 중간에 죽어도 직전까지의 결과가 디스크에 남음.
- `live_llm_<timestamp>.md` — 사람이 읽는 요약 표 + 판사 의견 상세. 세션 종료 시 자동 생성.

LLM 응답은 비결정적이라 `expected_verdict`와 어긋나면 fail로 표시되되 markdown에는 `UNEXPECTED` 라벨로 분리해 사후 분석 대상으로 남긴다.

## 새 테스트 추가 가이드

- **단위**: 외부 의존 없이 함수/클래스 단위로 검증. `tests/test_<module>.py`.
- **API 통합**: TestClient + LLM monkeypatch. `tests/test_pipeline.py` 또는 새 파일.
- **라이브**: 시나리오 추가 시 `LiveRunRecorder`/`LiveTutorRecorder`에 레코드를 push해 아티팩트에 누적되게 한다. expected와 actual이 다를 가능성을 전제로 작성.
- **스모크**: 보통 추가하지 않음. 배포 전 사람이 한 번 돌려보는 용도.

## 자주 쓰는 명령

```bash
.venv/bin/pytest -q                        # 전체(라이브 제외)
.venv/bin/pytest -x -q                     # 첫 실패에서 멈춤
.venv/bin/pytest tests/test_pipeline.py    # 파일 단위
.venv/bin/pytest -k cooldown               # 키워드 매칭
.venv/bin/pytest -v -s tests/live          # 라이브 (출력 캡처 끔)
```

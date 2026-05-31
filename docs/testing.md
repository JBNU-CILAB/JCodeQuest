# Testing Guide

JCodeQuest 백엔드 테스트의 구조와 실행 방법을 정리한 문서.

## 디렉터리 구조

> 샌드박스·잡큐가 judge_engine으로 분리되면서 `test_sandbox.py`·`test_jobqueue.py`는 **`judge_engine/tests/`** 로 이동했다. backend `tests/`는 API·스토리지·통합 위주.

```
backend/
├── pytest.ini               # asyncio_mode=auto, testpaths=tests
└── tests/
    ├── conftest.py          # 임시 SQLite DB 부트스트랩 + 환경 플래그, 쿨다운 0 fixture, sample_problem
    ├── test_auth.py         # Supabase JWT / dev-stub 인증
    ├── test_storage.py      # 스토리지 단위(SubmissionRow CRUD, attempt_status)
    ├── test_cooldown.py     # 쿨다운 계산 단위 + API 429/Retry-After
    ├── test_pipeline.py     # POST /grade → judge 위임 → webhook → GET/SSE E2E (submit_to_engine mock)
    ├── test_tutor.py        # POST /tutor/{id} 흐름 (OpenAI mock + 유저 API 키)
    ├── test_me_api_key.py   # PUT /me/api-key (vault)
    ├── test_me_submissions.py
    ├── test_problems_api.py # /problems, /problems/weeks
    ├── test_leaderboard.py  # /leaderboard, by-grade
    ├── test_stats.py        # /internal/stats/*
    ├── test_users.py / test_admin_users.py
    ├── test_internal_runs.py / test_internal_embeddings.py
    ├── live/                # 실 Ollama·OpenAI 라이브 슈트 (gated)
    │   ├── conftest.py      # JCQ_RUN_LIVE_LLM gate, JSONL/MD 아티팩트 레코더
    │   ├── test_live_ensemble.py
    │   └── test_live_tutor.py
    ├── scripts/
    │   └── smoke_e2e.py     # 살아있는 uvicorn에 붙는 스모크 (pytest 아님)
    └── artifacts/           # 라이브 슈트 산출물 (.gitkeep만 추적)

judge_engine/
└── tests/
    ├── test_sandbox.py      # 샌드박스 단위(러너/리소스 한도/표준입출력)
    └── test_jobqueue.py     # JobQueue 단위(워커 1, 워커 N, 종료)
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
- **환경 플래그**: conftest import 시점에 `JCQ_ALLOW_NON_POSTGRES=1`(SQLite 허용), `JCQ_AUTH_ALLOW_DEV_STUB=1`, `JCQ_COOKIE_INSECURE=1`, `SUPABASE_JWT_SECRET`(테스트용 더미), `JCQ_SKIP_ENSEMBLE=""`를 세팅한다.
- **쿨다운 무력화**: `_disable_cooldown` (autouse)가 `SUBMISSION_COOLDOWN_S=0`으로 monkeypatch. 쿨다운 자체를 검증하는 케이스는 자기 fixture에서 다시 켠다(`test_cooldown.py` 참조).
- **시드 문제**: `sample_problem` (Problem 객체) / `seeded_problem_id` (DB에 INSERT 후 id 반환).

## LLM 의존 제거 패턴

통합 테스트는 외부 호출을 monkeypatch로 갈아끼운다. 패치 대상은 **호출자 모듈**(정의 모듈이 아님)에 import된 심볼이다.

채점은 이제 judge_engine으로 위임되므로(3-judge `vote`는 judge_engine에 있음), backend 통합 테스트는 backend→judge HTTP 호출인 `submit_to_engine`을 가짜로 갈아끼우고 webhook(`apply_grading_event`)을 직접 호출해 결과를 주입한다. 패치 대상은 **API 라우터가 import한 심볼**(`src.api.grading.submit_to_engine`)이다:

```python
import src.api.grading as grading_api
async def _fake_submit(submission_id, problem, code, *a, **kw):
    ...  # 채점을 큐에 넣는 대신 테스트가 직접 webhook을 흉내냄
monkeypatch.setattr(grading_api, "submit_to_engine", _fake_submit)
```

튜터 LLM은 `src.tutor.client`의 호출 심볼을 patch한다. judge_engine 자체 테스트는 `vote`를 그 importer 모듈에서 patch한다.

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

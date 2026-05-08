# Environment Setup

JCodeQuest 백엔드는 환경변수를 **자동 로드하지 않는다** — `dotenv` 같은 모듈은 쓰지 않고, 코드는 `os.getenv()`로만 읽는다. 따라서 호출자가 셸에 변수를 export한 뒤 같은 셸에서 서버/스크립트를 띄워야 한다.

팀원 각자가 `backend/env.sh`를 자기 환경에 맞게 작성한 뒤 `source`로 적용한다. 이 파일은 `.gitignore`에 등록돼 있으므로 절대 커밋되지 않는다 — 키가 노출될 일은 없다.

## 위치 / 형식

```
JCodeQuest/
└── backend/
    └── env.sh        # ← 각자 작성, 커밋 금지
```

- 한 줄당 `export KEY=VALUE` 형식의 평범한 bash 스크립트.
- 실행이 아니라 **source** 해야 한다 (`./env.sh`가 아니라 `source env.sh`).
- 같은 변수가 OS 환경에 이미 있다면 export로 덮어씀.
- 따옴표는 값에 공백/특수문자가 있을 때만 — `export X="a b"`.

## 변수 목록

### 필수

| 변수 | 용도 | 비고 |
|------|------|------|
| `OPENAI_API_KEY` | 튜터 LLM 호출 — `src/tutor/client.py` | 비밀. 절대 커밋 금지 |
| `OLLAMA_BASE_URL` | 채점 ensemble의 Ollama 엔드포인트 — `src/judge/ensemble.py` | 예: `http://localhost:11434`. 모델 셋업은 `setup-ollama.md` 참조 |

### 선택 (기본값 있음)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `OPENAI_BASE_URL` | (미설정 → OpenAI 공식) | OpenAI 호환 엔드포인트 (vLLM, LM Studio, Azure-proxy 등) |
| `OPENAI_MODEL` | `gpt-5.1` | 튜터 모델 ID |
| `JCQ_DB_URL` | `sqlite:///./data/jcq.db` | SQLAlchemy URL. 절대경로 권장 — 서버와 스크립트가 같은 DB를 가리키도록 |
| `JCQ_QUEUE_CONCURRENCY` | `1` | 채점 워커 코루틴 수. 단일 프로세스 |
| `JCQ_SUBMIT_COOLDOWN_S` | `10` | 같은 (user, problem) 두 제출 사이 최소 간격(초). 0이면 비활성 |
| `JCQ_BASE_URL` | `http://127.0.0.1:8000` | 스모크 스크립트가 붙을 서버 주소 — `tests/scripts/smoke_e2e.py` |

### 테스트 전용

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `JCQ_RUN_LIVE_LLM` | (미설정) | `1`/`true`/`yes`일 때만 `tests/live/` 슈트가 수집됨. 그 외엔 모듈 단위 skip |

## 작성 예시

`backend/env.sh`를 새로 만들 때 이 템플릿에서 시작한다:

```bash
# ─── 필수 ─────────────────────────────────────────────
export OPENAI_API_KEY=sk-...                          # 본인 키
export OLLAMA_BASE_URL=http://localhost:11434         # 또는 팀 공용 호스트

# ─── 선택 ─────────────────────────────────────────────
# export OPENAI_BASE_URL=https://your-proxy.example.com/v1
# export OPENAI_MODEL=gpt-4o-mini

export JCQ_DB_URL=sqlite:////home/<you>/jcq.db        # 절대경로 권장
export JCQ_QUEUE_CONCURRENCY=1
# export JCQ_SUBMIT_COOLDOWN_S=10

# ─── 테스트 전용(필요 시 주석 해제) ─────────────────────
# export JCQ_RUN_LIVE_LLM=1
```

값을 넣은 뒤 사용 직전에 source한다:

```bash
source backend/env.sh
.venv/bin/uvicorn src.main:app --reload
```

## 주의사항

- **같은 셸에서 source**: 서버 셸과 스크립트 셸이 다르면 `JCQ_DB_URL`이 어긋나 다른 DB를 보게 된다. 스모크/마이그레이션을 돌릴 때 특히 주의.
- **상대경로 DB의 함정**: `sqlite:///./data/jcq.db`는 셸의 현재 디렉터리 기준으로 잡히므로, 다른 위치에서 돌리면 새 DB가 생긴다. 절대경로를 권장.
- **키 회전**: `env.sh`가 노출되면 키가 그대로 새는 거다. 의심되면 발급처에서 즉시 무효화 후 재발급.
- **테스트는 자체 격리**: `tests/conftest.py`가 임시 SQLite를 만들어 `JCQ_DB_URL`을 덮어쓰므로, pytest 실행 시 `env.sh`의 DB는 건드리지 않는다.

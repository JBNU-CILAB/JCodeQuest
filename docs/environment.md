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
| `GOOGLE_CLIENT_ID` | Google OAuth 클라이언트 ID — `src/auth/google.py` | Google Cloud Console에서 발급 |
| `GOOGLE_CLIENT_SECRET` | Google OAuth 클라이언트 시크릿 | 비밀. 절대 커밋 금지 |
| `SESSION_SECRET_KEY` | OAuth 핸드셰이크용 임시 쿠키 서명 (Starlette `SessionMiddleware`) | 32B+ 랜덤. 사용자 세션은 DB 측에 저장됨 — 이 키와 무관 |

### 선택 (기본값 있음)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `OPENAI_BASE_URL` | (미설정 → OpenAI 공식) | OpenAI 호환 엔드포인트 (vLLM, LM Studio, Azure-proxy 등) |
| `OPENAI_MODEL` | `gpt-5.1` | 튜터 모델 ID |
| `JCQ_DB_URL` | `sqlite:///./data/jcq.db` | SQLAlchemy URL. 절대경로 권장 — 서버와 스크립트가 같은 DB를 가리키도록 |
| `JCQ_QUEUE_CONCURRENCY` | `1` | 채점 워커 코루틴 수. 단일 프로세스 |
| `JCQ_SUBMIT_COOLDOWN_S` | `10` | 같은 (user, problem) 두 제출 사이 최소 간격(초). 0이면 비활성 |
| `JCQ_BASE_URL` | `http://127.0.0.1:8000` | 스모크 스크립트가 붙을 서버 주소 — `tests/scripts/smoke_e2e.py` |
| `GOOGLE_REDIRECT_URI` | `{request base}/auth/callback` | Google Cloud Console의 등록된 redirect URI와 정확히 일치해야 함 |
| `JCQ_AUTH_ALLOWED_HD` | `jbnu.ac.kr` | 허용할 Google Workspace 도메인. 콜백에서 ID token의 `hd` claim과 정확 비교. 비우면 모든 도메인 허용 (비권장) |
| `JCQ_SESSION_DAYS` | `7` | 서버 측 세션 만료(일). 로그아웃 시 SessionRow 즉시 삭제 — 진짜 무효화 |
| `JCQ_FRONTEND_REDIRECT_URL` | `/` | 로그인 성공 후 302로 보낼 곳. 프론트가 별 도메인이면 절대 URL로 |
| `JCQ_AUTH_ALLOW_DEV_STUB` | (미설정) | `1`/`true`/`yes`일 때만 `POST /auth/dev-login` 라우트 등록. **prod 절대 금지** |

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

## 파이썬 의존성 부트스트랩 / 동기화

`scripts/dev.sh`는 backend와 authoring_engine을 **같은 venv (`backend/.venv`)** 로 실행한다 — 두 패키지의 의존성을 한 venv에 모두 설치해야 한다. `git pull`/`git reset`으로 새 커밋을 받은 직후에는 `requirements.txt` / `pyproject.toml`도 함께 갱신됐을 수 있으므로 venv 동기화를 같이 돌리는 것을 기본 절차로 삼는다.

```bash
# 최초 부트스트랩 (venv 없을 때)
cd backend && python3 -m venv .venv
.venv/bin/pip install --upgrade pip          # ★ jcq-shared의 `@ file:../shared` 상대 경로는 pip 23.1+에서만 동작

# backend 의존성 + jcq-shared (editable)
cd backend && .venv/bin/pip install -r requirements.txt    # ★ requirements.txt의 첫 줄이 `file:../shared` 상대경로라 반드시 backend/에서 실행

# authoring_engine 의존성 (같은 venv에 editable로 추가)
cd ../authoring_engine && /Users/<you>/JCodeQuest/backend/.venv/bin/pip install -e .
```

증상별 대응:

- `ModuleNotFoundError: No module named 'itsdangerous'` / `'authlib'` → backend가 `requirements.txt`에 새로 추가된 OAuth 의존성. backend `pip install -r requirements.txt` 재실행.
- `ModuleNotFoundError: No module named 'sse_starlette'` / `'langgraph'` 등 → authoring_engine 의존성. `pip install -e authoring_engine/` 재실행 (같은 backend venv 대상).
- `ERROR: Invalid requirement: 'jcq-shared @ file:../shared'` → pip가 23.0 이하. `pip install --upgrade pip` 후 재시도.
- `scripts/dev.sh up` 헬스체크 실패 시 로그는 `.dev-logs/{backend,authoring}.log`에 남는다 — 첫 트레이스만 보면 원인이 잡힌다.

> 운영 규칙: `git pull` 또는 `git reset --hard origin/main`으로 신규 커밋을 받았다면, 코드를 돌리기 전에 위 두 `pip install` 명령을 한 번 더 실행하는 것을 습관으로 한다. 의존성 매니페스트만 갱신되고 venv가 그대로면 import 단계에서 깨진다.

#!/usr/bin/env bash
# JCodeQuest — 최초 1회 셋업 스크립트.
#
# 무엇을 하는가:
#   1) python3 (3.10+) / node (20+) 확인
#   2) backend/.venv, authoring_engine/.venv 생성
#   3) backend/requirements.txt, authoring_engine(editable) 설치 — jcq-shared도 함께 설치됨
#   4) frontend/ npm 의존성 설치 (Vite + React + Tailwind)
#   5) backend/.env, authoring_engine/.env가 없으면 .env.example에서 복사
#   6) backend/data/ 디렉터리 + DB 마이그레이션 실행
#   7) 다음 단계 안내 (값 채우기 → scripts/dev.sh up)
#
# 사용법:
#   scripts/setup.sh              # 모든 단계
#   scripts/setup.sh --no-venv    # venv 생성 건너뛰고 의존성만 재설치 (기존 venv 재사용)
#   scripts/setup.sh --skip-frontend  # 프런트엔드 npm install 건너뛰기
#   scripts/setup.sh --force-env  # 기존 .env를 덮어쓰며 .env.example로 재생성
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

NO_VENV=0
FORCE_ENV=0
SKIP_FRONTEND=0
for arg in "$@"; do
    case "$arg" in
        --no-venv)        NO_VENV=1 ;;
        --force-env)      FORCE_ENV=1 ;;
        --skip-frontend)  SKIP_FRONTEND=1 ;;
        -h|--help)
            sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *) echo "알 수 없는 옵션: $arg" >&2; exit 2 ;;
    esac
done

# ── 출력 유틸 ───────────────────────────────────────────────────────────────
_use_color=$([[ -t 1 ]] && echo 1 || echo 0)
c() { [[ $_use_color = 1 ]] && printf "\033[%sm%s\033[0m" "$1" "$2" || printf "%s" "$2"; }
ok()      { echo "  [$(c 32 ' OK ')] $*"; }
fail()    { echo "  [$(c 31 'FAIL')] $*"; }
info()    { echo "  [$(c 36 'INFO')] $*"; }
warn()    { echo "  [$(c 33 'WARN')] $*"; }
section() { echo; c "1;36" "── $* ──────────────────"; echo; }

# ── 1) 런타임 확인 (Python + Node) ─────────────────────────────────────────
section "1. 런타임 확인"
SYS_PY="$(command -v python3 || true)"
if [[ -z "$SYS_PY" ]]; then
    fail "python3가 PATH에 없습니다. Python 3.10+ 설치 필요."
    exit 1
fi
PY_VER="$($SYS_PY -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
ok "python3=$SYS_PY (버전 $PY_VER)"
if ! $SYS_PY -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)'; then
    fail "Python 3.10 이상이 필요합니다. 현재 $PY_VER"
    exit 1
fi

if [[ $SKIP_FRONTEND = 1 ]]; then
    info "Node 확인 생략 — --skip-frontend"
else
    SYS_NODE="$(command -v node || true)"
    SYS_NPM="$(command -v npm || true)"
    if [[ -z "$SYS_NODE" || -z "$SYS_NPM" ]]; then
        fail "node/npm이 PATH에 없습니다. Node.js 20+ 설치 필요 (https://nodejs.org)."
        fail "프런트엔드 셋업만 건너뛰려면 --skip-frontend 로 다시 실행하세요."
        exit 1
    fi
    NODE_VER="$($SYS_NODE -v | sed 's/^v//')"
    NODE_MAJOR="${NODE_VER%%.*}"
    ok "node=$SYS_NODE (버전 $NODE_VER) · npm=$SYS_NPM"
    if (( NODE_MAJOR < 20 )); then
        fail "Node.js 20 이상이 필요합니다. 현재 $NODE_VER"
        exit 1
    fi
fi

# ── 2) venv 생성 ───────────────────────────────────────────────────────────
create_venv() {
    local dir="$1" venv_path="$1/.venv"
    if [[ -x "$venv_path/bin/python" ]]; then
        ok "venv 이미 존재: $venv_path"
        return 0
    fi
    info "venv 생성: $venv_path"
    "$SYS_PY" -m venv "$venv_path"
    ok "venv 생성 완료: $venv_path"
}

if [[ $NO_VENV = 1 ]]; then
    section "2. venv 생성 (생략 — --no-venv)"
else
    section "2. venv 생성"
    create_venv "$REPO_ROOT/backend"
    create_venv "$REPO_ROOT/authoring_engine"
fi

BACKEND_PY="$REPO_ROOT/backend/.venv/bin/python"
AUTHORING_PY="$REPO_ROOT/authoring_engine/.venv/bin/python"

[[ -x "$BACKEND_PY"   ]] || { fail "backend venv 없음: $BACKEND_PY"; exit 1; }
[[ -x "$AUTHORING_PY" ]] || { fail "authoring venv 없음: $AUTHORING_PY"; exit 1; }

# ── 3) 의존성 설치 ─────────────────────────────────────────────────────────
section "3. 의존성 설치"

info "backend: pip + requirements.txt"
"$BACKEND_PY" -m pip install --upgrade pip > /dev/null
"$BACKEND_PY" -m pip install -r "$REPO_ROOT/backend/requirements.txt"
ok "backend 의존성 설치 완료 (jcq-shared 포함)"

info "authoring_engine: pip + editable install"
"$AUTHORING_PY" -m pip install --upgrade pip > /dev/null
"$AUTHORING_PY" -m pip install -e "$REPO_ROOT/authoring_engine"
ok "authoring_engine 의존성 설치 완료 (jcq-shared 포함)"

# ── 4) 프런트엔드 의존성 설치 ──────────────────────────────────────────────
if [[ $SKIP_FRONTEND = 1 ]]; then
    section "4. 프런트엔드 의존성 (생략 — --skip-frontend)"
else
    section "4. 프런트엔드 의존성 설치"
    FRONTEND_DIR="$REPO_ROOT/frontend"
    if [[ ! -f "$FRONTEND_DIR/package.json" ]]; then
        warn "frontend/package.json 없음 — 프런트엔드 셋업 건너뜀"
    else
        info "frontend: npm install (Vite + React + Tailwind)"
        if [[ -f "$FRONTEND_DIR/package-lock.json" ]]; then
            (cd "$FRONTEND_DIR" && npm ci --no-audit --no-fund)
        else
            (cd "$FRONTEND_DIR" && npm install --no-audit --no-fund)
        fi
        ok "frontend 의존성 설치 완료 ($FRONTEND_DIR/node_modules)"
    fi
fi

# ── 5) .env 셋업 ───────────────────────────────────────────────────────────
section "5. .env 파일 준비"

copy_env() {
    local target="$1" example="$2"
    if [[ ! -f "$example" ]]; then
        warn ".env.example 없음: $example (건너뜀)"
        return 0
    fi
    if [[ -f "$target" && $FORCE_ENV != 1 ]]; then
        ok "이미 존재: $target (덮어쓰려면 --force-env)"
        return 0
    fi
    cp "$example" "$target"
    ok "생성: $target  ←  $(basename "$example")"
}

copy_env "$REPO_ROOT/backend/.env"          "$REPO_ROOT/backend/.env.example"
copy_env "$REPO_ROOT/authoring_engine/.env" "$REPO_ROOT/authoring_engine/.env.example"

# ── 6) data 디렉터리 + 마이그레이션 ─────────────────────────────────────────
section "6. DB 마이그레이션"
mkdir -p "$REPO_ROOT/backend/data"
ok "backend/data/ 준비"

if (cd "$REPO_ROOT/backend" && "$BACKEND_PY" migrate.py); then
    ok "migrate.py 실행 완료"
else
    fail "migrate.py 실패 — backend/.env의 JCQ_DB_URL이 절대경로인지 확인"
    exit 1
fi

# ── 7) 안내 ────────────────────────────────────────────────────────────────
section "다음 단계"
cat <<EOF
  1) backend/.env, authoring_engine/.env 의 값을 채우세요.
     - OPENAI_API_KEY, OLLAMA_BASE_URL
     - JCQ_DB_URL: 두 파일에서 동일한 **절대경로** (예: $REPO_ROOT/backend/data/jcq.db)
     - 로컬 시연용: SESSION_SECRET_KEY, JCQ_AUTH_ALLOW_DEV_STUB=1, JCQ_COOKIE_INSECURE=1

  2) Ollama가 떠 있고 3개 판사 모델이 pull 되어 있는지 확인 — docs/setup-ollama.md

  3) 개발 서버 일괄 기동:
        scripts/dev.sh up

  4) 프런트엔드만 단독으로 띄우려면:
        cd frontend && npm run dev          # http://localhost:5173

  $(c 32 '✓') 셋업 완료
EOF

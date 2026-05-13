#!/usr/bin/env bash
# JCodeQuest — 최초 1회 셋업 스크립트.
#
# 무엇을 하는가:
#   1) python3 확인 (3.10+ 필요)
#   2) backend/.venv, authoring_engine/.venv, judge_engine/.venv 생성
#   3) backend/requirements.txt, authoring_engine/judge_engine(editable) 설치 — jcq-shared도 함께 설치됨
#   4) backend/.env, authoring_engine/.env, judge_engine/.env가 없으면 .env.example에서 복사
#   5) backend/data/ 디렉터리 + DB 마이그레이션 실행
#   6) 다음 단계 안내 (값 채우기 → scripts/dev.sh up)
#
# 사용법:
#   scripts/setup.sh            # 모든 단계
#   scripts/setup.sh --no-venv  # venv 생성 건너뛰고 의존성만 재설치 (기존 venv 재사용)
#   scripts/setup.sh --force-env  # 기존 .env를 덮어쓰며 .env.example로 재생성
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

NO_VENV=0
FORCE_ENV=0
for arg in "$@"; do
    case "$arg" in
        --no-venv)    NO_VENV=1 ;;
        --force-env)  FORCE_ENV=1 ;;
        -h|--help)
            sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'
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

# ── 1) python 확인 ─────────────────────────────────────────────────────────
section "1. Python 확인"
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
    create_venv "$REPO_ROOT/judge_engine"
fi

BACKEND_PY="$REPO_ROOT/backend/.venv/bin/python"
AUTHORING_PY="$REPO_ROOT/authoring_engine/.venv/bin/python"
JUDGE_PY="$REPO_ROOT/judge_engine/.venv/bin/python"

[[ -x "$BACKEND_PY"   ]] || { fail "backend venv 없음: $BACKEND_PY"; exit 1; }
[[ -x "$AUTHORING_PY" ]] || { fail "authoring venv 없음: $AUTHORING_PY"; exit 1; }
[[ -x "$JUDGE_PY"     ]] || { fail "judge venv 없음: $JUDGE_PY"; exit 1; }

# ── 3) 의존성 설치 ─────────────────────────────────────────────────────────
section "3. 의존성 설치"

info "backend: pip + requirements.txt"
"$BACKEND_PY" -m pip install --upgrade pip > /dev/null
# requirements.txt 안의 `jcq-shared @ file:../shared`는 pip의 CWD 기준으로 풀리므로
# backend 디렉터리에서 실행해야 ../shared 가 올바르게 해석된다.
(cd "$REPO_ROOT/backend" && "$BACKEND_PY" -m pip install -r requirements.txt)
ok "backend 의존성 설치 완료 (jcq-shared 포함)"

info "authoring_engine: pip + editable install"
"$AUTHORING_PY" -m pip install --upgrade pip > /dev/null
# pyproject.toml의 `jcq-shared @ file:../shared`도 pip CWD 기준이라 같은 cd 트릭 필요.
(cd "$REPO_ROOT/authoring_engine" && "$AUTHORING_PY" -m pip install -e .)
ok "authoring_engine 의존성 설치 완료 (jcq-shared 포함)"

info "judge_engine: pip + editable install"
"$JUDGE_PY" -m pip install --upgrade pip > /dev/null
(cd "$REPO_ROOT/judge_engine" && "$JUDGE_PY" -m pip install -e .)
ok "judge_engine 의존성 설치 완료 (jcq-shared 포함)"

# 각 pyproject/requirements는 jcq-shared를 `@ file:../shared`로 끌어다 쓰는데
# 이건 비-editable 설치라 shared 스키마를 고칠 때마다 force-reinstall이 필요해진다.
# 모든 venv에 jcq-shared만 editable로 덮어씌워 한 번 build하면 그 뒤로 동기 자동 반영.
info "jcq-shared를 모든 venv에 editable로 재설치 (스키마 동기화)"
for PY in "$BACKEND_PY" "$AUTHORING_PY" "$JUDGE_PY"; do
    "$PY" -m pip install --quiet -e "$REPO_ROOT/shared"
done
ok "jcq-shared editable 설치 완료 (3개 venv)"

# ── 4) .env 셋업 ───────────────────────────────────────────────────────────
section "4. .env 파일 준비"

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
copy_env "$REPO_ROOT/judge_engine/.env"     "$REPO_ROOT/judge_engine/.env.example"

# webhook 공유 시크릿이 비어있으면 자동 생성 후 양쪽 .env에 동일하게 박는다.
# 한쪽만 채워져 있으면 그 값을 다른 쪽으로 복제 (양쪽 일치 보장).
sync_internal_secret() {
    local backend_env="$REPO_ROOT/backend/.env"
    local judge_env="$REPO_ROOT/judge_engine/.env"
    [[ -f "$backend_env" && -f "$judge_env" ]] || return 0

    local b j secret
    b="$(grep -E '^JCQ_INTERNAL_SECRET=' "$backend_env" 2>/dev/null | head -1 | cut -d= -f2-)"
    j="$(grep -E '^JCQ_INTERNAL_SECRET=' "$judge_env"   2>/dev/null | head -1 | cut -d= -f2-)"

    if [[ -n "$b" && "$b" == "$j" ]]; then
        ok "JCQ_INTERNAL_SECRET 양쪽 일치"
        return 0
    fi
    if [[ -n "$b" ]]; then
        secret="$b"
    elif [[ -n "$j" ]]; then
        secret="$j"
    else
        secret="$("$SYS_PY" -c 'import secrets; print(secrets.token_urlsafe(48))')"
        info "JCQ_INTERNAL_SECRET 신규 생성"
    fi

    # backend/.env: export 접두어가 있을 수 있어 두 패턴 모두 처리
    if grep -qE '^(export[[:space:]]+)?JCQ_INTERNAL_SECRET=' "$backend_env"; then
        sed -i -E "s|^(export[[:space:]]+)?JCQ_INTERNAL_SECRET=.*|JCQ_INTERNAL_SECRET=${secret}|" "$backend_env"
    else
        echo "JCQ_INTERNAL_SECRET=${secret}" >> "$backend_env"
    fi
    if grep -qE '^JCQ_INTERNAL_SECRET=' "$judge_env"; then
        sed -i -E "s|^JCQ_INTERNAL_SECRET=.*|JCQ_INTERNAL_SECRET=${secret}|" "$judge_env"
    else
        echo "JCQ_INTERNAL_SECRET=${secret}" >> "$judge_env"
    fi
    ok "JCQ_INTERNAL_SECRET 동기화 완료"
}
sync_internal_secret

# ── 5) data 디렉터리 + 마이그레이션 ─────────────────────────────────────────
section "5. DB 마이그레이션"
mkdir -p "$REPO_ROOT/backend/data"
ok "backend/data/ 준비"

if (cd "$REPO_ROOT/backend" && "$BACKEND_PY" migrate.py); then
    ok "migrate.py 실행 완료"
else
    fail "migrate.py 실패 — backend/.env의 JCQ_DB_URL이 절대경로인지 확인"
    exit 1
fi

# ── 6) 안내 ────────────────────────────────────────────────────────────────
section "다음 단계"
cat <<EOF
  1) backend/.env, authoring_engine/.env, judge_engine/.env 의 값을 채우세요.
     - backend/.env: OPENAI_API_KEY, SESSION_SECRET_KEY (로컬 시연용으로 JCQ_AUTH_ALLOW_DEV_STUB=1, JCQ_COOKIE_INSECURE=1)
     - authoring_engine/.env: OPENAI_API_KEY, OLLAMA_BASE_URL
     - judge_engine/.env: OLLAMA_BASE_URL  (채점 엔진은 DB 비접근)
     - JCQ_DB_URL: backend·authoring 양쪽에서 동일한 **절대경로** (예: $REPO_ROOT/backend/data/jcq.db)
     - JCQ_INTERNAL_SECRET: backend·judge_engine 양쪽에 자동 동기화됨 (위 단계 4에서 처리)

  2) Ollama가 떠 있고 3개 판사 모델이 pull 되어 있는지 확인 — docs/setup-ollama.md

  3) 개발 서버 일괄 기동:
        scripts/dev.sh up

  $(c 32 '✓') 셋업 완료
EOF
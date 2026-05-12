#!/usr/bin/env bash
# JCodeQuest 개발 환경 — backend(:8000) + authoring(:8001) + frontend(:5500)을
# 한 번에 띄우고 내리는 진입점.
#
# 사용법:
#   scripts/dev.sh up       # 3개 서버 기동 + 헬스체크
#   scripts/dev.sh down     # 떠 있는 서버 종료
#   scripts/dev.sh status   # 현재 상태 (PID, 포트, /health 응답)
#   scripts/dev.sh logs <backend|authoring|frontend>
#   scripts/dev.sh restart  # down → up
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$REPO_ROOT/.dev-logs"
mkdir -p "$LOG_DIR"

# 각 서비스가 자기 venv를 쓰도록 분리 — backend와 authoring은 의존성 집합이 달라
# (예: authoring만 sse-starlette를 요구) 같은 uvicorn으로 띄우면 ModuleNotFoundError.
BACKEND_VENV_BIN="$REPO_ROOT/backend/.venv/bin"
AUTHORING_VENV_BIN="$REPO_ROOT/authoring_engine/.venv/bin"

# 일반 python — migrate.py 실행, frontend의 http.server 등 venv 의존성이 없는 작업용.
# backend venv를 우선 사용 (sqlmodel 등 migrate.py가 쓰는 모듈을 갖고 있음).
PY=""
for cand in "$BACKEND_VENV_BIN/python" \
            "$REPO_ROOT/.venv/bin/python" \
            "$(command -v python3 || true)"; do
    if [[ -x "$cand" ]]; then PY="$cand"; break; fi
done
[[ -z "$PY" ]] && { echo "python을 찾을 수 없습니다"; exit 1; }

# ── 서비스 정의 (이름 / 포트 / 헬스 경로 / cwd / 실행 인자) ──────────────────
SERVICES=("backend" "authoring" "frontend")

backend_port=8000;   backend_health="/health"
authoring_port=8001; authoring_health="/api/health"
frontend_port=5500;  frontend_health="/index.html"

# ── 출력 유틸 ───────────────────────────────────────────────────────────────
_use_color=$([[ -t 1 ]] && echo 1 || echo 0)
c() { [[ $_use_color = 1 ]] && printf "\033[%sm%s\033[0m" "$1" "$2" || printf "%s" "$2"; }
ok()   { echo "  [$(c 32 ' OK ')] $*"; }
fail() { echo "  [$(c 31 'FAIL')] $*"; }
info() { echo "  [$(c 36 'INFO')] $*"; }
section() { echo; c "1;36" "── $* ──────────────────"; echo; }

# ── 공통 헬퍼 ──────────────────────────────────────────────────────────────
pidfile() { echo "$LOG_DIR/$1.pid"; }
logfile() { echo "$LOG_DIR/$1.log"; }

port_of()   { local v="${1}_port";   echo "${!v}"; }
health_of() { local v="${1}_health"; echo "${!v}"; }

is_running() {
    local pid_file
    pid_file="$(pidfile "$1")"
    [[ -f "$pid_file" ]] || return 1
    local pid
    pid="$(cat "$pid_file")"
    [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

port_listening() {
    local port="$1"
    # bash /dev/tcp는 listen 검사가 아니라 connect 검사 — 충분히 빠르고 의존 없음.
    (echo > "/dev/tcp/127.0.0.1/$port") 2>/dev/null
}

wait_health() {
    local name="$1" port health url
    port="$(port_of "$name")"
    health="$(health_of "$name")"
    url="http://127.0.0.1:${port}${health}"
    for _ in $(seq 1 30); do
        if curl -sf --max-time 2 "$url" > /dev/null 2>&1; then return 0; fi
        sleep 0.5
    done
    return 1
}

# ── 시작 로직 ──────────────────────────────────────────────────────────────
start_backend() {
    cd "$REPO_ROOT/backend"
    nohup "$BACKEND_VENV_BIN/uvicorn" src.main:app \
        --host 127.0.0.1 --port "$backend_port" \
        > "$(logfile backend)" 2>&1 &
    echo $! > "$(pidfile backend)"
}

start_authoring() {
    cd "$REPO_ROOT/authoring_engine"
    nohup "$AUTHORING_VENV_BIN/uvicorn" authoring.server:app \
        --host 127.0.0.1 --port "$authoring_port" \
        > "$(logfile authoring)" 2>&1 &
    echo $! > "$(pidfile authoring)"
}

start_frontend() {
    cd "$REPO_ROOT/frontend"
    nohup "$PY" -m http.server "$frontend_port" --bind 127.0.0.1 \
        > "$(logfile frontend)" 2>&1 &
    echo $! > "$(pidfile frontend)"
}

start_one() {
    local name="$1" port
    port="$(port_of "$name")"

    if is_running "$name"; then
        ok "$name 이미 떠있음 (pid=$(cat "$(pidfile "$name")"))"
        return 0
    fi

    if port_listening "$port"; then
        fail "$name :${port} 가 이미 사용 중 (다른 프로세스). 'scripts/dev.sh status' 확인"
        return 1
    fi

    info "$name 기동 중..."
    "start_${name}"
    if wait_health "$name"; then
        ok "$name pid=$(cat "$(pidfile "$name")") :${port}"
    else
        fail "$name 헬스체크 실패 — 로그: $(logfile "$name")"
        tail -n 15 "$(logfile "$name")" | sed 's/^/    /'
        return 1
    fi
}

# ── 마이그레이션 ────────────────────────────────────────────────────────────
run_migrations() {
    local mlog="$LOG_DIR/migrate.log"
    info "DB 마이그레이션 실행 중 (backend/migrate.py)..."
    if (cd "$REPO_ROOT/backend" && "$PY" migrate.py) > "$mlog" 2>&1; then
        ok "migrate 완료 (로그: $mlog)"
    else
        fail "migrate 실패 — 로그: $mlog"
        tail -n 20 "$mlog" | sed 's/^/    /'
        return 1
    fi
}

# ── 종료 로직 ──────────────────────────────────────────────────────────────
stop_one() {
    local name="$1" pid_file
    pid_file="$(pidfile "$name")"

    if [[ ! -f "$pid_file" ]]; then
        info "$name pid 파일 없음 — 이미 정리됨"
        return 0
    fi

    local pid
    pid="$(cat "$pid_file")"
    if ! kill -0 "$pid" 2>/dev/null; then
        info "$name pid=$pid 이미 종료됨"
        rm -f "$pid_file"
        return 0
    fi

    kill "$pid" 2>/dev/null || true
    for _ in $(seq 1 20); do
        kill -0 "$pid" 2>/dev/null || break
        sleep 0.2
    done
    if kill -0 "$pid" 2>/dev/null; then
        kill -9 "$pid" 2>/dev/null || true
        sleep 0.3
    fi
    rm -f "$pid_file"
    ok "$name pid=$pid 종료"
}

# ── 서브커맨드 ─────────────────────────────────────────────────────────────
cmd_up() {
    section "JCodeQuest dev — 기동"
    info "python: $PY"
    info "log dir: $LOG_DIR"
    run_migrations || exit 1
    local rc=0
    for s in "${SERVICES[@]}"; do
        start_one "$s" || rc=1
    done
    echo
    if [[ $rc = 0 ]]; then
        echo "  $(c 32 '✓') 모두 떠있음"
        echo "     frontend  http://localhost:${frontend_port}"
        echo "     backend   http://localhost:${backend_port}  (인증: dev-login)"
        echo "     authoring http://localhost:${authoring_port}"
    else
        echo "  $(c 31 '✗') 일부 서비스 기동 실패 — 위 로그 참고"
        exit 1
    fi
}

cmd_down() {
    section "JCodeQuest dev — 종료"
    for s in "${SERVICES[@]}"; do
        stop_one "$s"
    done
}

cmd_status() {
    section "JCodeQuest dev — 상태"
    for s in "${SERVICES[@]}"; do
        local port health url state pid
        port="$(port_of "$s")"
        health="$(health_of "$s")"
        url="http://127.0.0.1:${port}${health}"
        if is_running "$s"; then
            pid="$(cat "$(pidfile "$s")")"
            if curl -sf --max-time 2 "$url" > /dev/null 2>&1; then
                state="$(c 32 'UP')"
            else
                state="$(c 33 'PID alive, health failing')"
            fi
            printf "  %-10s %s pid=%s :%s\n" "$s" "$state" "$pid" "$port"
        else
            printf "  %-10s %s :%s\n" "$s" "$(c 90 'DOWN')" "$port"
        fi
    done
}

cmd_logs() {
    local svc="${1:-}"
    if [[ -z "$svc" ]]; then
        echo "사용법: scripts/dev.sh logs <backend|authoring|frontend>" >&2
        exit 2
    fi
    case "$svc" in
        backend|authoring|frontend) ;;
        *) echo "알 수 없는 서비스: $svc" >&2; exit 2 ;;
    esac
    local lf
    lf="$(logfile "$svc")"
    [[ -f "$lf" ]] || { echo "로그 없음: $lf" >&2; exit 1; }
    exec tail -n 100 -f "$lf"
}

cmd_restart() {
    cmd_down
    cmd_up
}

# ── 디스패치 ───────────────────────────────────────────────────────────────
case "${1:-up}" in
    up)      cmd_up ;;
    down)    cmd_down ;;
    status)  cmd_status ;;
    logs)    shift; cmd_logs "${1:-}" ;;
    restart) cmd_restart ;;
    -h|--help|help)
        sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
        ;;
    *)
        echo "알 수 없는 명령: $1" >&2
        echo "사용법: scripts/dev.sh {up|down|status|logs|restart}" >&2
        exit 2
        ;;
esac

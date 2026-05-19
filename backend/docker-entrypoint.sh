#!/bin/sh
set -e

# ORM 기준 스키마 보장 (postgres·sqlite 공통, idempotent).
# 컨테이너 부팅 직후 docker bridge NAT 셋업 전에 외부 Supabase pooler로 가는
# 첫 SYN이 드롭돼 psycopg ConnectionTimeout이 발생하는 경우가 있다.
# restart 정책으로 race가 무한 반복되지 않도록 짧은 backoff로 재시도.
attempt=1
max_attempts=10
sleep_s=1
until python -c 'from src.storage import init_db; init_db()'; do
    if [ "$attempt" -ge "$max_attempts" ]; then
        echo "[entrypoint] init_db ${max_attempts}회 실패 — 종료" >&2
        exit 1
    fi
    echo "[entrypoint] init_db attempt ${attempt} 실패 — ${sleep_s}s 후 재시도" >&2
    sleep "$sleep_s"
    attempt=$((attempt + 1))
    if [ "$sleep_s" -lt 5 ]; then
        sleep_s=$((sleep_s + 1))
    fi
done

# migrate.py는 SQLite 전용 incremental ALTER. Supabase(postgresql://)면 스킵 —
# 스키마는 Supabase 대시보드/CLI로 관리한다고 가정.
case "${JCQ_DB_URL:-}" in
    postgresql://*|postgres://*|postgresql+*://*)
        echo "[entrypoint] postgres URL 감지 — migrate.py 스킵"
        ;;
    *)
        python migrate.py
        ;;
esac

exec uvicorn src.main:app --host 0.0.0.0 --port 8000

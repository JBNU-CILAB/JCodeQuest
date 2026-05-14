#!/bin/sh
set -e

# ORM 기준 스키마 보장 (postgres·sqlite 공통, idempotent).
python -c 'from src.storage import init_db; init_db()'

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

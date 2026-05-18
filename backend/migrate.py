"""스키마 마이그레이션 스크립트.

Postgres(운영, Supabase)와 SQLite(테스트) 양쪽 dialect를 지원한다.
JCQ_DB_URL이 가리키는 DB를 SQLAlchemy engine으로 열고, dialect별 DDL을 실행한다.

실행:
    # SQLite (기본 경로 backend/data/jcq.db) — 그냥 호출
    python migrate.py

    # Postgres — env.sh 가 JCQ_DB_URL 을 export 한 셸에서
    source backend/env.sh
    python backend/migrate.py

dev.sh는 Postgres URL 감지 시 자동 마이그레이션을 스킵한다(운영 DB 변경은
의식적으로 손으로 돌리도록). 운영 스키마 변경이 필요할 때만 위처럼 호출하라.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError

# src.storage.db는 import 시점에 JCQ_DB_URL을 KeyError 없이 요구한다.
# 단독 실행(`python backend/migrate.py`) 호환을 위해 backend/.env를 먼저 로드.
load_dotenv(Path(__file__).parent / ".env")

from src.storage.db import engine  # noqa: E402  — env 로딩 후에 import

dialect = engine.dialect.name
is_pg = dialect.startswith("postgres")
print(f"Dialect: {dialect}  URL: {engine.url.render_as_string(hide_password=True)}")

# 각 항목: (라벨, Postgres DDL, SQLite DDL)
# Postgres는 IF NOT EXISTS로 idempotent, SQLite는 duplicate-column 예외로 처리.
migrations: list[tuple[str, str, str]] = [
    (
        "problem.parent_id",
        "ALTER TABLE problem ADD COLUMN IF NOT EXISTS parent_id INTEGER REFERENCES problem(id)",
        "ALTER TABLE problem ADD COLUMN parent_id INTEGER REFERENCES problem(id)",
    ),
    (
        "problem.langsmith_trace_id",
        "ALTER TABLE problem ADD COLUMN IF NOT EXISTS langsmith_trace_id TEXT",
        "ALTER TABLE problem ADD COLUMN langsmith_trace_id TEXT",
    ),
    (
        "problem.authoring_meta",
        "ALTER TABLE problem ADD COLUMN IF NOT EXISTS authoring_meta TEXT",
        "ALTER TABLE problem ADD COLUMN authoring_meta TEXT",
    ),
    (
        "problem.iso_week",
        "ALTER TABLE problem ADD COLUMN IF NOT EXISTS iso_week TEXT",
        "ALTER TABLE problem ADD COLUMN iso_week TEXT",
    ),
    (
        "user.api_key_secret_id",
        # "user"는 Postgres 예약어 — 따옴표 필수.
        'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS api_key_secret_id TEXT',
        'ALTER TABLE "user" ADD COLUMN api_key_secret_id TEXT',
    ),
    (
        "user.avatar_url",
        'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS avatar_url TEXT',
        'ALTER TABLE "user" ADD COLUMN avatar_url TEXT',
    ),
    (
        "tutor_message.is_user_requested",
        "ALTER TABLE tutor_message ADD COLUMN IF NOT EXISTS is_user_requested BOOLEAN DEFAULT FALSE",
        "ALTER TABLE tutor_message ADD COLUMN is_user_requested BOOLEAN DEFAULT FALSE",
    ),
]


def _is_duplicate(err: Exception) -> bool:
    msg = str(err).lower()
    return "duplicate column" in msg or "already exists" in msg


# created_at/updated_at/expires_at 컬럼들을 TIMESTAMPTZ로 통일.
# SQLite는 TIMESTAMP/TIMESTAMPTZ 구분이 없어 적용 불필요. PG에서만 실행.
# 기존 naive 값은 session timezone(Supabase 기본 UTC) 기준으로 해석된다.
# 같은 ALTER를 두 번 돌려도 PG는 타입이 이미 timestamptz면 에러 없이 통과.
tz_migrations: list[tuple[str, str]] = [
    ('user.created_at',         'ALTER TABLE "user" ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE \'UTC\''),
    ('user.updated_at',         'ALTER TABLE "user" ALTER COLUMN updated_at TYPE TIMESTAMPTZ USING updated_at AT TIME ZONE \'UTC\''),
    ('problem.created_at',      "ALTER TABLE problem ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC'"),
    ('submission.created_at',   "ALTER TABLE submission ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC'"),
    ('session.created_at',      "ALTER TABLE session ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC'"),
    ('session.expires_at',      "ALTER TABLE session ALTER COLUMN expires_at TYPE TIMESTAMPTZ USING expires_at AT TIME ZONE 'UTC'"),
    ('tutor_message.created_at', "ALTER TABLE tutor_message ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC'"),
    ('notice.created_at',       "ALTER TABLE notice ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC'"),
    ('notice.updated_at',       "ALTER TABLE notice ALTER COLUMN updated_at TYPE TIMESTAMPTZ USING updated_at AT TIME ZONE 'UTC'"),
]


with engine.begin() as conn:
    for label, pg_sql, sqlite_sql in migrations:
        sql = pg_sql if is_pg else sqlite_sql
        try:
            conn.execute(text(sql))
            print(f"  OK  {label}")
        except (OperationalError, ProgrammingError) as e:
            if _is_duplicate(e):
                print(f"SKIP  {label} (이미 존재)")
            else:
                raise

    for idx_sql in (
        "CREATE INDEX IF NOT EXISTS ix_problem_parent_id ON problem (parent_id)",
        "CREATE INDEX IF NOT EXISTS ix_problem_langsmith_trace_id ON problem (langsmith_trace_id)",
        "CREATE INDEX IF NOT EXISTS ix_problem_iso_week ON problem (iso_week)",
    ):
        conn.execute(text(idx_sql))

    # TIMESTAMPTZ 일괄 변환 — PG에서만. 이미 timestamptz 이면 PG가 no-op로 통과.
    if is_pg:
        for label, sql in tz_migrations:
            try:
                conn.execute(text(sql))
                print(f"  OK  {label} → TIMESTAMPTZ")
            except (OperationalError, ProgrammingError) as e:
                # 같은 타입으로의 재변환은 PG가 조용히 통과하지만, 일부 버전이
                # "cannot cast" 같은 메시지를 낼 수 있어 방어적으로 무시.
                msg = str(e).lower()
                if "timestamp with time zone" in msg or "already" in msg:
                    print(f"SKIP  {label} (이미 timestamptz)")
                else:
                    raise

    # iso_week 백필 — SQLite strftime의 %V 지원이 일관되지 않아 Python으로 계산.
    rows = conn.execute(
        text(
            "SELECT id, created_at FROM problem "
            "WHERE iso_week IS NULL OR iso_week = ''"
        )
    ).all()
    backfilled = 0
    for pid, created_at in rows:
        if isinstance(created_at, datetime):
            dt = created_at
        elif isinstance(created_at, str):
            try:
                dt = datetime.fromisoformat(created_at)
            except ValueError:
                continue
        else:
            continue
        y, w, _ = dt.isocalendar()
        conn.execute(
            text("UPDATE problem SET iso_week = :w WHERE id = :id"),
            {"w": f"{y:04d}-W{w:02d}", "id": pid},
        )
        backfilled += 1
    if backfilled:
        print(f"  OK  iso_week 백필 {backfilled}건")

print("마이그레이션 완료")

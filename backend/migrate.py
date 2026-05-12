"""SQLite 스키마 마이그레이션 스크립트.

실행:
    python migrate.py

JCQ_DB_URL 환경변수가 설정되어 있으면 그 경로를 사용하고,
없으면 backend/data/jcq.db 기본값을 사용한다.
"""
import os
import sqlite3
from pathlib import Path

raw_url = os.getenv("JCQ_DB_URL", "")
if raw_url.startswith("sqlite:///"):
    db_path = raw_url.removeprefix("sqlite:///")
else:
    db_path = str(Path(__file__).parent / "data" / "jcq.db")

print(f"DB: {db_path}")

if not Path(db_path).exists():
    print("DB 파일이 없습니다. 서버를 먼저 한 번 실행해 init_db()를 수행하세요.")
    raise SystemExit(1)

conn = sqlite3.connect(db_path)
cur = conn.cursor()

migrations: list[tuple[str, str]] = [
    (
        "problem.parent_id",
        "ALTER TABLE problem ADD COLUMN parent_id INTEGER REFERENCES problem(id)",
    ),
    (
        "problem.langsmith_trace_id",
        "ALTER TABLE problem ADD COLUMN langsmith_trace_id TEXT",
    ),
    (
        "problem.authoring_meta",
        "ALTER TABLE problem ADD COLUMN authoring_meta TEXT",
    ),
]

for col, sql in migrations:
    try:
        cur.execute(sql)
        print(f"  OK  {col}")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print(f"SKIP  {col} (이미 존재)")
        else:
            raise

# parent_id 인덱스 (별도 생성 — ALTER TABLE로는 인덱스 불가)
cur.execute(
    "CREATE INDEX IF NOT EXISTS ix_problem_parent_id ON problem (parent_id)"
)
cur.execute(
    "CREATE INDEX IF NOT EXISTS ix_problem_langsmith_trace_id ON problem (langsmith_trace_id)"
)

conn.commit()
conn.close()
print("마이그레이션 완료")

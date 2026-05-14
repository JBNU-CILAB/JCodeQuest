import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

DB_URL = os.getenv("JCQ_DB_URL", "sqlite:///./data/jcq.db")

# SQLAlchemy 2.x는 `postgresql://`를 psycopg2 드라이버로 해석한다. 우리는 psycopg(v3)만
# 의존성에 두므로, 명시적 dialect가 없는 postgres URL은 `postgresql+psycopg://`로 재기재.
if DB_URL.startswith("postgresql://"):
    DB_URL = "postgresql+psycopg://" + DB_URL[len("postgresql://") :]

engine = create_engine(
    DB_URL,
    connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {},
)


@event.listens_for(engine, "connect")
def _sqlite_pragma(dbapi_conn, _):
    if not DB_URL.startswith("sqlite"):
        return
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.close()


def init_db() -> None:
    if DB_URL.startswith("sqlite:///"):
        path = Path(DB_URL.removeprefix("sqlite:///"))
        path.parent.mkdir(parents=True, exist_ok=True)
    from . import models  # noqa: F401  -- register tables

    SQLModel.metadata.create_all(engine)


@contextmanager
def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session

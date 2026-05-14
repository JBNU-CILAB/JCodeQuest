import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlmodel import Session, SQLModel, create_engine

DB_URL = os.environ["JCQ_DB_URL"]

# SQLAlchemy 2.x는 `postgresql://`를 psycopg2 드라이버로 해석한다. 우리는 psycopg(v3)만
# 의존성에 두므로, 명시적 dialect가 없는 postgres URL은 `postgresql+psycopg://`로 재기재.
if DB_URL.startswith("postgresql://"):
    DB_URL = "postgresql+psycopg://" + DB_URL[len("postgresql://") :]

engine = create_engine(DB_URL)


def init_db() -> None:
    from . import models  # noqa: F401  -- register tables

    SQLModel.metadata.create_all(engine)


@contextmanager
def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session

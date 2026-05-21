import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

DB_URL = os.environ["JCQ_DB_URL"]

# SQLAlchemy 2.x는 `postgresql://`를 psycopg2 드라이버로 해석한다. 우리는 psycopg(v3)만
# 의존성에 두므로, 명시적 dialect가 없는 postgres URL은 `postgresql+psycopg://`로 재기재.
if DB_URL.startswith("postgresql://"):
    DB_URL = "postgresql+psycopg://" + DB_URL[len("postgresql://") :]

# Supabase Transaction Pooler(PgBouncer transaction mode)는 서버 연결을 클라이언트
# 사이에 재사용하므로 psycopg3가 자동 생성하는 prepared statement(`_pg3_0` 등)가
# 충돌한다(`DuplicatePreparedStatement`). prepare_threshold=None으로 비활성화한다.
#
# connect_timeout + TCP keepalive: PgBouncer가 TCP는 받았는데 응답이 끊긴 상태에서
# psycopg가 OS 기본(분 단위) 타임아웃까지 ep_poll에서 무한 대기하는 경우가 있다
# (특히 컨테이너 부팅 직후). 짧은 timeout으로 끊고 entrypoint의 retry 루프가 돌게 한다.
_connect_args: dict[str, object] = {}
if DB_URL.startswith("postgresql+psycopg://"):
    _connect_args["prepare_threshold"] = None
    _connect_args["connect_timeout"] = 10
    _connect_args["keepalives"] = 1
    _connect_args["keepalives_idle"] = 30
    _connect_args["keepalives_interval"] = 10
    _connect_args["keepalives_count"] = 3

# 운영에서 비-Postgres DB로 떨어지면 storage/vault.py가 plaintext fallback으로
# 사용자 API 키를 그대로 저장한다(테스트 격리용 코드 경로). 명시적 우회 플래그
# (JCQ_ALLOW_NON_POSTGRES=1) 없이는 모듈 로드를 거부한다.
if not DB_URL.startswith("postgresql") and os.environ.get("JCQ_ALLOW_NON_POSTGRES") != "1":
    _scheme = DB_URL.split(":", 1)[0]
    raise RuntimeError(
        f"JCQ_DB_URL must point to PostgreSQL (got '{_scheme}://...'). "
        "Non-Postgres backends trigger vault plaintext fallback — refusing to boot. "
        "Set JCQ_ALLOW_NON_POSTGRES=1 only for tests/local dev with no real secrets."
    )

engine = create_engine(DB_URL, connect_args=_connect_args)


# 서버 사이드 hang을 cap. CREATE TABLE 한 발도 30초 이상 걸리면 비정상 — pooler가
# 응답을 안 주거나, 다른 세션이 catalog lock을 들고 있는 상태다. 둘 다 부팅을 막느니
# 빠르게 죄어서 entrypoint retry로 넘기는 게 낫다.
if DB_URL.startswith("postgresql+psycopg://"):
    @event.listens_for(engine, "connect")
    def _set_statement_timeout(dbapi_conn, _record):  # type: ignore[no-untyped-def]
        with dbapi_conn.cursor() as cur:
            cur.execute("SET statement_timeout = '30s'")


def init_db() -> None:
    from . import models  # noqa: F401  -- register tables

    SQLModel.metadata.create_all(engine)


@contextmanager
def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session

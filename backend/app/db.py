from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def make_engine(database_path: str) -> Engine:
    url = "sqlite://" if database_path == ":memory:" else f"sqlite:///{database_path}"
    kwargs = {"connect_args": {"check_same_thread": False}}
    if database_path == ":memory:":
        from sqlalchemy.pool import StaticPool

        kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.close()

    return engine


class Database:
    def __init__(self, database_path: str):
        self.engine = make_engine(database_path)
        self.sessionmaker = sessionmaker(self.engine, expire_on_commit=False)

    def session(self) -> Iterator[Session]:
        with self.sessionmaker() as s:
            yield s

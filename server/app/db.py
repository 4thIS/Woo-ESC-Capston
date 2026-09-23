"""SQLite 하나. WAL + busy_timeout 5 s (spec §2.1)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def make_engine(path: str) -> Engine:
    eng = create_engine(
        f"sqlite:///{path}",
        connect_args={"timeout": 5, "check_same_thread": False},
        hide_parameters=True,
    )

    @event.listens_for(eng, "connect")
    def _pragma(conn, _rec):
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")

    return eng


def make_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(engine, expire_on_commit=False)

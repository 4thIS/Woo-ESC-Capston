from sqlalchemy import create_engine, inspect

from app.db import Base
from tests.test_migrations import _upgrade

TABLES = ("assistant_conversations", "assistant_turns", "assistant_previews", "assistant_changes")


def test_web_assistant_migration_creates_tables(tmp_path):
    names = _upgrade(tmp_path / "ai.db")
    assert set(TABLES) <= names


def test_models_match_migration(tmp_path):
    import app.assistant.models  # noqa: F401 — Base.metadata 에 등록

    db = tmp_path / "m.db"
    _upgrade(db)
    insp = inspect(create_engine(f"sqlite:///{db}"))
    for t in TABLES:
        migrated = {c["name"]: c["nullable"] for c in insp.get_columns(t)}
        model = {c.name: c.nullable for c in Base.metadata.tables[t].columns}
        assert migrated == model, t

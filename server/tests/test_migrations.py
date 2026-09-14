from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command

SERVER = Path(__file__).resolve().parents[1]


def _upgrade(db):
    cfg = Config(str(SERVER / "alembic.ini"))
    cfg.set_main_option("script_location", str(SERVER / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    command.upgrade(cfg, "head")
    return set(inspect(create_engine(f"sqlite:///{db}")).get_table_names())


def test_lora_migration_creates_tables(tmp_path):
    names = _upgrade(tmp_path / "m.db")
    assert {
        "outbox",
        "modems",
        "room_versions",
        "terminal_status",
        "pending_devices",
        "lora_log",
    } <= names


def test_web_migration_creates_tables(tmp_path):
    names = _upgrade(tmp_path / "w.db")
    assert {"schools", "buildings", "rooms", "slots", "reservations", "exam_periods"} <= names

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


def test_slot_source_column(tmp_path):
    db = tmp_path / "s.db"
    _upgrade(db)
    cols = {c["name"]: c for c in inspect(create_engine(f"sqlite:///{db}")).get_columns("slots")}
    assert cols["source"]["nullable"] is False
    assert str(cols["source"]["default"]).strip("'") == "2"


def test_web_auth_migration(tmp_path):
    db = tmp_path / "a.db"
    names = _upgrade(db)
    assert {"users", "email_tokens"} <= names
    eng = create_engine(f"sqlite:///{db}")
    with (
        eng.connect() as c
    ):  # 조용한 롤백 감지 — env.py 가 트랜잭션을 먼저 열면 버전이 비어 있다 (r2 🔴2)
        assert c.exec_driver_sql("SELECT version_num FROM alembic_version").scalar()
    insp = inspect(eng)
    cols = lambda t: {c["name"] for c in insp.get_columns(t)}
    assert {
        "email",
        "school_id",
        "role",
        "status",
        "name",
        "student_no",
        "pw_hash",
        "token_version",
        "created_at",
        "approved_at",
        "approved_by",
        "reject_reason",
    } <= cols("users")
    assert {"token_hash", "email", "purpose", "created_at", "expires_at", "used_at"} <= cols(
        "email_tokens"
    )
    uq = {i["name"]: i for i in insp.get_indexes("users")}["uq_users_school_student_no"]
    assert uq["unique"] and uq["column_names"] == ["school_id", "student_no"]
    assert insp.get_foreign_keys("email_tokens") == []  # verify 토큰은 users 행보다 먼저 생긴다
    assert "email_domain" in cols("schools") and "reservable" in cols("rooms")
    assert "school_id" in cols("modems")


def _cfg(db):
    from alembic.config import Config

    cfg = Config(str(SERVER / "alembic.ini"))
    cfg.set_main_option("script_location", str(SERVER / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    return cfg


def test_web_auth_backfills_modem_school(tmp_path):
    """건물에 이미 배정된 모뎀은 그 건물의 학교로 채운다 (S4a §7)."""
    from sqlalchemy import text

    from alembic import command

    db = tmp_path / "b.db"
    command.upgrade(_cfg(db), "6b47ab194f9a")  # web_auth 직전
    eng = create_engine(f"sqlite:///{db}")
    with eng.begin() as c:
        c.execute(text("INSERT INTO modems (modem_id, token_hash, connected) VALUES ('m1','x',0)"))
        c.execute(text("INSERT INTO schools (id, name, net_id) VALUES (1,'명지',75)"))
        c.execute(
            text("INSERT INTO buildings (school_id, name, bld, modem_id) VALUES (1,'공','E','m1')")
        )
    command.upgrade(_cfg(db), "head")
    with eng.connect() as c:
        assert c.execute(text("SELECT school_id FROM modems WHERE modem_id='m1'")).scalar() == 1


def test_web_auth_refuses_bld_shared_across_schools(tmp_path):
    """bld 는 학교 간 전역 유일(S4a §3.3) — 겹치는 기존 DB 는 마이그레이션이 멈춘다."""
    import pytest
    from sqlalchemy import text

    from alembic import command

    db = tmp_path / "c.db"
    command.upgrade(_cfg(db), "6b47ab194f9a")
    with create_engine(f"sqlite:///{db}").begin() as c:
        c.execute(text("INSERT INTO schools (id, name, net_id) VALUES (1,'a',75), (2,'b',76)"))
        c.execute(
            text("INSERT INTO buildings (school_id, name, bld) VALUES (1,'x','E'), (2,'y','E')")
        )
    with pytest.raises(RuntimeError, match="bld"):
        command.upgrade(_cfg(db), "head")


def test_rejected_row_does_not_hold_student_no(tmp_path):
    """부분 유일 인덱스 — 거절 행은 학번을 잡지 않고, 대기·활성·정지 행끼리는 막는다 (r2 🟡)."""
    import pytest
    import sqlalchemy.exc
    from sqlalchemy import text

    db = tmp_path / "d.db"
    _upgrade(db)
    eng = create_engine(f"sqlite:///{db}")
    row = "INSERT INTO users (email, school_id, role, status, name, student_no, pw_hash, token_version, created_at) VALUES ('{e}', 1, 'student', '{st}', 'n', '7', 'h', 0, '2026-09-23')"
    with eng.begin() as c:
        c.execute(text("INSERT INTO schools (id, name, net_id) VALUES (1, 'a', 75)"))
        c.execute(text(row.format(e="x@a.kr", st="rejected")))
        c.execute(text(row.format(e="y@a.kr", st="pending_approval")))  # 거절 행과 같은 학번 OK
    with pytest.raises(sqlalchemy.exc.IntegrityError), eng.begin() as c:
        c.execute(text(row.format(e="z@a.kr", st="active")))

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


def test_web_auth_refuses_modem_shared_across_schools(tmp_path):
    """모뎀 하나가 두 학교 건물에 배정되면 school_id 를 하나로 정할 수 없다 (S4a §3.3, cw 리뷰)."""
    import pytest
    from sqlalchemy import text

    from alembic import command

    db = tmp_path / "f.db"
    command.upgrade(_cfg(db), "6b47ab194f9a")
    with create_engine(f"sqlite:///{db}").begin() as c:
        c.execute(text("INSERT INTO modems (modem_id, token_hash, connected) VALUES ('m1','x',0)"))
        c.execute(text("INSERT INTO schools (id, name, net_id) VALUES (1,'a',75), (2,'b',76)"))
        c.execute(
            text(
                "INSERT INTO buildings (school_id, name, bld, modem_id)"
                " VALUES (1,'x','E','m1'), (2,'y','F','m1')"
            )
        )
    with pytest.raises(RuntimeError, match="모뎀"):
        command.upgrade(_cfg(db), "head")


def test_downgrade_keeps_rooms_check_constraint(tmp_path):
    """리뷰: CHECK table_args 는 테이블을 재생성하는 downgrade 쪽에 둬야 실제로 효과가 있다."""
    import pytest
    import sqlalchemy.exc
    from sqlalchemy import text

    from alembic import command

    db = tmp_path / "g.db"
    _upgrade(db)
    command.downgrade(_cfg(db), "-1")
    eng = create_engine(f"sqlite:///{db}")
    with eng.begin() as c:
        c.execute(text("INSERT INTO schools (id, name, net_id) VALUES (1,'a',75)"))
        c.execute(text("INSERT INTO buildings (school_id, name, bld) VALUES (1,'x','E')"))
    with pytest.raises(sqlalchemy.exc.IntegrityError), eng.begin() as c:
        c.execute(text("INSERT INTO rooms (building_id, room, units) VALUES (1, 0, 1)"))


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


def test_resv_checkout_column(tmp_path):
    db = tmp_path / "c.db"
    _upgrade(db)
    eng = create_engine(f"sqlite:///{db}")
    cols = {c["name"]: c for c in inspect(eng).get_columns("reservations")}
    assert cols["checked_out_at"]["nullable"] is True
    # batch 재생성이 기존 CHECK 를 잃지 않았다 — 상태·id 범위 제약이 그대로
    checks = {c["name"] for c in inspect(eng).get_check_constraints("reservations")}
    assert {"ck_resv_id", "ck_resv_status"} <= checks


def test_roles_migration_keeps_users_and_adds_building_admin(tmp_path):
    """#160 — role CHECK 에 building_admin, user_buildings · role_changes 표. 기존 행·학번 유일성은 그대로."""
    import sqlite3

    db = tmp_path / "r.db"
    cfg = Config(str(SERVER / "alembic.ini"))
    cfg.set_main_option("script_location", str(SERVER / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    command.upgrade(cfg, "4c0a9f71e19d")  # #160 직전
    c = sqlite3.connect(db)
    c.execute(
        "INSERT INTO schools (id, name, net_id, email_domain) VALUES (1, '명지', 75, 'mju.ac.kr')"
    )
    for email, role, no in [("a@mju.ac.kr", "admin", None), ("s@mju.ac.kr", "student", "S1")]:
        c.execute(
            "INSERT INTO users (email, school_id, role, status, name, student_no, pw_hash,"
            " token_version, created_at) VALUES (?, 1, ?, 'active', 'n', ?, 'x', 0, '2026-11-17')",
            (email, role, no),
        )
    c.commit()
    c.close()

    command.upgrade(cfg, "head")
    names = set(inspect(create_engine(f"sqlite:///{db}")).get_table_names())
    assert {"user_buildings", "role_changes"} <= names
    c = sqlite3.connect(db)
    assert c.execute("SELECT email, role FROM users ORDER BY email").fetchall() == [
        ("a@mju.ac.kr", "admin"),
        ("s@mju.ac.kr", "student"),
    ]
    c.execute("UPDATE users SET role = 'building_admin' WHERE email = 's@mju.ac.kr'")
    try:
        c.execute("UPDATE users SET role = 'root' WHERE email = 's@mju.ac.kr'")
        raise AssertionError("role CHECK 가 사라졌다")
    except sqlite3.IntegrityError:
        pass
    # 학번 부분 유일 인덱스가 남아 있다
    c.execute(
        "INSERT INTO users (email, school_id, role, status, name, student_no, pw_hash,"
        " token_version, created_at) VALUES ('t@mju.ac.kr', 1, 'student', 'active', 'n', 'S2', 'x', 0, '2026-11-17')"
    )
    try:
        c.execute("UPDATE users SET student_no = 'S1' WHERE email = 't@mju.ac.kr'")
        raise AssertionError("학번 유일 인덱스가 사라졌다")
    except sqlite3.IntegrityError:
        pass
    try:
        c.execute("UPDATE users SET status = 'weird' WHERE email = 't@mju.ac.kr'")
        raise AssertionError("status CHECK 가 사라졌다")
    except sqlite3.IntegrityError:
        pass
    c.close()


def test_roles_migration_downgrade_round_trip(tmp_path):
    import sqlite3

    db = tmp_path / "d.db"
    cfg = Config(str(SERVER / "alembic.ini"))
    cfg.set_main_option("script_location", str(SERVER / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "4c0a9f71e19d")
    names = set(inspect(create_engine(f"sqlite:///{db}")).get_table_names())
    assert "user_buildings" not in names and "role_changes" not in names
    command.upgrade(cfg, "head")
    sql = (
        sqlite3.connect(db)
        .execute("SELECT sql FROM sqlite_master WHERE name='users'")
        .fetchone()[0]
    )
    assert sql.count("ck_users_role") == 1 and "building_admin" in sql
    assert sql.count("ck_users_status") == 1

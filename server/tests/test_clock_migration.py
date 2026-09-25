import datetime as dt
import json

from sqlalchemy import create_engine, inspect

from app.domain import clock
from app.domain.models import Reservation
from tests.test_migrations import _upgrade


def test_clock_conversions():
    u = dt.datetime(2026, 9, 22, 16, 30)  # noqa: DTZ001 — naive UTC (app.db.utcnow)
    l = clock.to_local(u)
    assert l == dt.datetime(2026, 9, 23, 1, 30) and l.tzinfo is None  # noqa: DTZ001
    assert clock.to_utc(l) == u
    assert clock.week_start(dt.date(2026, 9, 23)) == dt.date(2026, 9, 21)  # 수 → 월
    assert clock.week_start(dt.date(2026, 9, 21)) == dt.date(2026, 9, 21)
    assert clock.local_dt(dt.date(2026, 9, 23), 9, 5) == dt.datetime(2026, 9, 23, 9, 5)  # noqa: DTZ001


def test_local_today_uses_now_utc(monkeypatch):
    monkeypatch.setattr(clock, "now_utc", lambda: dt.datetime(2026, 9, 22, 16, 30))  # noqa: DTZ001
    assert clock.local_today() == dt.date(2026, 9, 23)
    assert clock.local_now() == dt.datetime(2026, 9, 23, 1, 30)  # noqa: DTZ001


def test_web_student_migration(tmp_path):
    db = tmp_path / "s.db"
    names = _upgrade(db)
    assert "job_runs" in names
    cols = {
        c["name"] for c in inspect(create_engine(f"sqlite:///{db}")).get_columns("reservations")
    }
    assert {
        "status",
        "requested_by",
        "requested_at",
        "decided_at",
        "decided_by",
        "reject_reason",
        "checked_in_at",
        "cancelled_at",
        "pushed_at",
    } <= cols


def test_put_resv_window_is_local_date(client, app, school, students, monkeypatch):
    """UTC 22 일 16:30 = KST 23 일 01:30. KST 30 일은 창 안(+7), UTC 기준이면 +8 로 창 밖이 됐을 것."""
    monkeypatch.setattr(clock, "now_utc", lambda: dt.datetime(2026, 9, 22, 16, 30))  # noqa: DTZ001
    from app.domain.models import Building, Room

    with app.state.Session() as s, s.begin():
        b = Building(school_id=1, name="E동", bld="E")
        s.add(b)
        s.flush()
        r = Room(building_id=b.id, room=101, units=1)
        s.add(r)
        s.flush()
        rid = r.id
    body = {
        "date": "2026-09-30",
        "s_h": 9,
        "s_m": 0,
        "e_h": 10,
        "e_m": 0,
        "type": 6,
        "subject": "r",
        "professor": "",
    }
    res = client.post(f"/api/rooms/{rid}/reservations", json=body)
    assert (
        res.status_code == 200 and res.json()["outbox_ids"]
    )  # E 동은 모뎀 없음 → api.enqueue 는 modem_id None 이어도 행 생성
    assert (
        client.post(f"/api/rooms/{rid}/reservations", json={**body, "date": "2026-10-01"}).json()[
            "outbox_ids"
        ]
        == []
    )
    # 학생 신청(requested) 행은 id 지정 upsert 로 못 고친다 — 미승인 RESV_SET 방지 (리뷰 🔴4a)
    with app.state.Session() as s, s.begin():
        s.add(
            Reservation(
                id=50,
                room_id=rid,
                date=dt.date(2026, 9, 24),
                s_h=9,
                s_m=0,
                e_h=10,
                e_m=0,
                type=6,
                subject="신청",
                professor="",
                status="requested",
                requested_by="s1@mju.ac.kr",
            )
        )
    assert client.post(f"/api/rooms/{rid}/reservations", json={**body, "id": 50}).status_code == 409


def test_record_provider_only_approved_and_local_window(app, students, monkeypatch):
    """FILE 재동기에 신청·취소 예약이 실리지 않고, 창은 KST 오늘 기준 (리뷰 🔴6)."""
    from app.domain.models import Building, Room
    from app.domain.topology import record_provider

    monkeypatch.setattr(clock, "now_utc", lambda: dt.datetime(2026, 9, 22, 19, 0))  # noqa: DTZ001 — KST 9/23 04:00
    with app.state.Session() as s, s.begin():
        b = Building(school_id=1, name="E동", bld="E")
        s.add(b)
        s.flush()
        r = Room(building_id=b.id, room=101, units=1)
        s.add(r)
        s.flush()
        for i, (d, st) in enumerate(
            [
                (dt.date(2026, 9, 30), "approved"),
                (dt.date(2026, 9, 24), "requested"),
                (dt.date(2026, 9, 24), "cancelled"),
                (dt.date(2026, 9, 23), "approved"),
            ],
            start=1,
        ):
            s.add(
                Reservation(
                    id=i,
                    room_id=r.id,
                    date=d,
                    s_h=9,
                    s_m=0,
                    e_h=10,
                    e_m=0,
                    type=6,
                    subject="x",
                    professor="",
                    status=st,
                    requested_by="s1@mju.ac.kr" if st != "approved" else None,
                )
            )
    recs = record_provider(app.state.Session)("E", 101, "resv")
    assert sorted(x.resv_id for x in recs) == [1, 4]  # 9/30 = KST 오늘+7 포함, 신청·취소 제외


def test_record_provider_subject_hides_requester(app, students):
    """학생이 신청해 승인된 예약도 문 앞 e-Paper 엔 과목 대신 '학생 예약' 만 나간다."""
    from app.domain.models import Building, Room
    from app.domain.topology import record_provider

    with app.state.Session() as s, s.begin():
        b = Building(school_id=1, name="E동", bld="E")
        s.add(b)
        s.flush()
        r = Room(building_id=b.id, room=101, units=1)
        s.add(r)
        s.flush()
        s.add(
            Reservation(
                id=1,
                room_id=r.id,
                date=clock.local_today(),
                s_h=9,
                s_m=0,
                e_h=10,
                e_m=0,
                type=6,
                subject="비밀 과목",
                professor="",
                status="approved",
                requested_by="s1@mju.ac.kr",
            )
        )
    recs = record_provider(app.state.Session)("E", 101, "resv")
    assert len(recs) == 1 and recs[0].subject == "학생 예약"


def test_record_provider_limits_to_node_resv_max(app, students):
    """방의 창 안 approved 예약이 24 개를 넘으면 (date, s_h, s_m) 순 앞 24 개만 — STORE_FAIL 방지."""
    from app.domain.models import Building, Room
    from app.domain.topology import NODE_RESV_MAX, record_provider

    today = clock.local_today()
    with app.state.Session() as s, s.begin():
        b = Building(school_id=1, name="E동", bld="E")
        s.add(b)
        s.flush()
        r = Room(building_id=b.id, room=101, units=1)
        s.add(r)
        s.flush()
        s.add_all(
            [
                Reservation(
                    id=i,
                    room_id=r.id,
                    date=today,
                    s_h=8,
                    s_m=i,
                    e_h=9,
                    e_m=0,
                    type=6,
                    subject="x",
                    professor="",
                    status="approved",
                )
                for i in range(1, 26)
            ]
        )
    recs = record_provider(app.state.Session)("E", 101, "resv")
    assert NODE_RESV_MAX == 24
    assert [x.resv_id for x in recs] == list(range(1, 25))  # s_m 오름차순 = id 1..24, 25 는 잘림


def test_resv_id_check_survives_migration(tmp_path):
    import pytest
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import IntegrityError

    db = tmp_path / "c.db"
    _upgrade(db)
    with create_engine(f"sqlite:///{db}").begin() as c:
        c.execute(text("INSERT INTO schools (id, name, net_id) VALUES (1,'a',75)"))
        c.execute(text("INSERT INTO buildings (id, school_id, name, bld) VALUES (1,1,'x','E')"))
        c.execute(text("INSERT INTO rooms (id, building_id, room, units) VALUES (1,1,101,1)"))
    with (
        pytest.raises(IntegrityError),
        create_engine(f"sqlite:///{db}").begin() as c,
    ):  # batch 재생성 뒤에도 CHECK 유지
        c.execute(
            text(
                "INSERT INTO reservations (id, room_id, date, s_h, s_m, e_h, e_m, type, subject, professor)"
                " VALUES (70000, 1, '2026-09-24', 9, 0, 10, 0, 6, 'x', '')"
            )
        )


def test_backfill_pushed_at_needs_resv_set_history(tmp_path):
    """오늘~+7 인 예약이라도 RESV_SET 이력(outbox)이 없으면 pushed_at 을 채우지 않는다 — 채우면
    첫 일일 승격이 노드에 한 번도 나간 적 없는 예약을 건너뛰어 영영 안 실린다 (fix round 1, item 1)."""
    from sqlalchemy import create_engine, text

    from alembic import command
    from tests.test_migrations import _cfg

    db = tmp_path / "p.db"
    command.upgrade(_cfg(db), "1739aef3234e")  # web_student 직전 (web_auth head)
    today = (dt.datetime.now(dt.UTC) + dt.timedelta(hours=9)).date().isoformat()
    with create_engine(f"sqlite:///{db}").begin() as c:
        c.execute(text("INSERT INTO schools (id, name, net_id) VALUES (1,'a',75)"))
        c.execute(text("INSERT INTO buildings (id, school_id, name, bld) VALUES (1,1,'x','E')"))
        c.execute(text("INSERT INTO rooms (id, building_id, room, units) VALUES (1,1,101,1)"))
        c.execute(
            text(
                "INSERT INTO reservations (id, room_id, date, s_h, s_m, e_h, e_m, type, subject, professor)"
                " VALUES (1,1,:d,9,0,10,0,6,'a',''), (2,1,:d,9,0,10,0,6,'b','')"
            ),
            {"d": today},
        )
        # id=1 만 RESV_SET 으로 이미 나간 이력이 있다 (id=2 는 없음 — 창 밖에서 만들어졌던 예약).
        # id=2 의 RESV_SET 은 같은 id 를 쓰던 옛(다른 날짜) 예약의 것 — id 재사용에 속지 않는다
        y, m, d = map(int, today.split("-"))
        old = dt.date(y, m, d) - dt.timedelta(days=30)
        ins = text(
            "INSERT INTO outbox (bld, room, unit, type, payload, priority, state, attempts,"
            " created_at) VALUES ('E', 101, 1, 'RESV_SET', :p, 1, 'queued', 0, CURRENT_TIMESTAMP)"
        )
        for rid, day in ((1, dt.date(y, m, d)), (2, old)):
            p = {"resv_id": rid, "year": day.year, "month": day.month, "day": day.day}
            c.execute(ins, {"p": json.dumps(p)})
    command.upgrade(_cfg(db), "head")
    with create_engine(f"sqlite:///{db}").connect() as c:
        rows = dict(c.execute(text("SELECT id, pushed_at FROM reservations")).fetchall())
    assert rows[1] is not None
    assert rows[2] is None

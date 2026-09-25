import datetime as dt

from app.domain.models import Building, ExamPeriod, Reservation, Room, Slot
from app.lora_service.models import Modem, Outbox


def _building(app, school_id, bld, rooms=((101, 1), (102, 1))):
    with app.state.Session() as s, s.begin():
        b = Building(school_id=school_id, name=f"{bld}동", bld=bld)
        s.add(b)
        s.flush()
        ids = {}
        for room, units in rooms:
            r = Room(building_id=b.id, room=room, units=units)
            s.add(r)
            s.flush()
            ids[room] = r.id
        bid = b.id
    return bid, ids


def _outbox(app, bld, room, *, unit=1, state="queued", modem_id=None, finished_at=None):
    now = dt.datetime(2026, 9, 25)  # noqa: DTZ001 — 앱 전역이 naive UTC (app.db.utcnow)
    with app.state.Session() as s, s.begin():
        o = Outbox(
            modem_id=modem_id,
            bld=bld,
            room=room,
            unit=unit,
            type="CMD",
            payload="{}",
            priority=5,
            state=state,
            created_at=now,
            finished_at=finished_at,
        )
        s.add(o)
        s.flush()
        oid = o.id
    return oid


def _seed_rows(app, ids):
    with app.state.Session() as s, s.begin():
        s.add_all(
            [
                Slot(
                    room_id=ids[102],
                    day=2,
                    s_h=9,
                    s_m=0,
                    e_h=10,
                    e_m=0,
                    type=1,
                    subject="b",
                    professor="",
                ),
                Slot(
                    room_id=ids[101],
                    day=1,
                    s_h=13,
                    s_m=0,
                    e_h=14,
                    e_m=0,
                    type=1,
                    subject="a2",
                    professor="",
                ),
                Slot(
                    room_id=ids[101],
                    day=1,
                    s_h=9,
                    s_m=0,
                    e_h=10,
                    e_m=0,
                    type=1,
                    subject="a1",
                    professor="",
                ),
                Reservation(
                    id=5,
                    room_id=ids[102],
                    date=dt.date(2026, 9, 25),
                    s_h=9,
                    s_m=0,
                    e_h=10,
                    e_m=0,
                    type=6,
                    subject="r2",
                    professor="",
                ),
                Reservation(
                    id=3,
                    room_id=ids[101],
                    date=dt.date(2026, 9, 24),
                    s_h=9,
                    s_m=0,
                    e_h=10,
                    e_m=0,
                    type=6,
                    subject="r1",
                    professor="",
                ),
                ExamPeriod(
                    id=7,
                    room_id=ids[101],
                    date_start=dt.date(2026, 10, 19),
                    date_end=dt.date(2026, 10, 23),
                ),
            ]
        )


def test_building_reads_join_room_id_and_sort(client, app, school):
    bid, ids = _building(app, 1, "E")
    _seed_rows(app, ids)
    r = client.get(f"/api/buildings/{bid}/slots")
    assert r.status_code == 200
    assert [(x["room_id"], x["day"], x["s_h"], x["subject"]) for x in r.json()] == [
        (ids[101], 1, 9, "a1"),
        (ids[101], 1, 13, "a2"),
        (ids[102], 2, 9, "b"),
    ]
    r = client.get(f"/api/buildings/{bid}/reservations")
    assert [(x["room_id"], x["id"]) for x in r.json()] == [(ids[101], 3), (ids[102], 5)]
    r = client.get(f"/api/buildings/{bid}/exams")
    assert [(x["room_id"], x["id"]) for x in r.json()] == [(ids[101], 7)]


def test_building_reads_scoped_404(client, app, school, other_admin_hdr):
    bid, _ = _building(app, 2, "F")
    for path in ("slots", "reservations", "exams", "outbox"):
        assert client.get(f"/api/buildings/{bid}/{path}").status_code == 404, path
    assert client.get(f"/api/buildings/{bid}/slots", headers=other_admin_hdr).status_code == 200


def test_building_outbox_filters_state_and_joins(client, app, school):
    bid, ids = _building(app, 1, "E")
    _building(app, 1, "G", rooms=((101, 1),))  # 같은 학교 다른 건물, 같은 호수 — 섞이면 안 됨
    a = _outbox(app, "E", 101, state="queued", finished_at=None)
    b = _outbox(app, "E", 102, state="acked")
    _outbox(app, "G", 101, state="queued", finished_at=None)
    r = client.get(f"/api/buildings/{bid}/outbox")
    assert [x["id"] for x in r.json()] == [b, a]  # id desc
    assert r.json()[0]["room_id"] == ids[102] and r.json()[0]["building"] == "E동"
    r = client.get(f"/api/buildings/{bid}/outbox?state=queued&limit=1")
    assert [x["id"] for x in r.json()] == [a]
    assert client.get(f"/api/buildings/{bid}/outbox?limit=501").status_code == 422
    assert client.get(f"/api/buildings/{bid}/outbox?state=bogus").status_code == 422  # #48 🟡3


def test_building_outbox_excludes_other_school_modem_on_bld_reuse(client, app, school):
    """건물 삭제·재생성으로 bld 글자가 재사용되면, 옛 학교(모뎀이 다른 학교 소속) 행이
    같은 (bld, room) 을 우연히 물고 있어도 보이면 안 된다 (/api/lora/outbox 와 같은 규칙)."""
    bid, ids = _building(app, 1, "E")
    with app.state.Session() as s, s.begin():
        s.add(Modem(modem_id="m2", token_hash="x", school_id=2))
    stale = _outbox(app, "E", 101, modem_id="m2")  # 학교 2 소유 모뎀의 옛 행
    mine = _outbox(app, "E", 101, modem_id=None)
    r = client.get(f"/api/buildings/{bid}/outbox")
    assert [x["id"] for x in r.json()] == [mine]
    assert stale not in [x["id"] for x in r.json()]
    assert ids  # 방 조인이 실제로 쓰였는지(참고용)


def test_reservation_reads_carry_status_requester_pushed_at(
    client, app, school, students, other_admin_hdr, student_hdr
):
    bid, ids = _building(app, 1, "E")
    pushed = dt.datetime(2026, 9, 23, 1, 30)  # noqa: DTZ001 — 앱 전역이 naive UTC
    with app.state.Session() as s, s.begin():
        s.add_all(
            [
                Reservation(
                    id=1,
                    room_id=ids[101],
                    date=dt.date(2026, 9, 24),
                    s_h=9,
                    s_m=0,
                    e_h=10,
                    e_m=0,
                    type=6,
                    subject="행사",
                    professor="학생처",
                    pushed_at=pushed,
                ),
                Reservation(
                    id=2,
                    room_id=ids[101],
                    date=dt.date(2026, 9, 24),
                    s_h=13,
                    s_m=0,
                    e_h=14,
                    e_m=0,
                    type=6,
                    subject="스터디",
                    professor="",
                    status="requested",
                    requested_by="s1@mju.ac.kr",
                ),
                Reservation(
                    id=3,
                    room_id=ids[102],
                    date=dt.date(2026, 12, 1),
                    s_h=9,
                    s_m=0,
                    e_h=10,
                    e_m=0,
                    type=6,
                    subject="창 밖",
                    professor="",
                ),
            ]
        )
    s1 = {"email": "s1@mju.ac.kr", "name": "학생1", "student_no": "S1"}
    got = client.get(f"/api/buildings/{bid}/reservations").json()
    assert [(x["id"], x["status"], x["requester"], x["pushed_at"]) for x in got] == [
        (1, "approved", None, "2026-09-23T01:30:00"),
        (2, "requested", s1, None),
        (3, "approved", None, None),  # 창 밖 — pushed_at NULL 이 '예정' 배지
    ]
    got = client.get(f"/api/rooms/{ids[101]}/reservations").json()
    assert [(x["id"], x["room_id"], x["requester"], x["pushed_at"]) for x in got] == [
        (1, ids[101], None, "2026-09-23T01:30:00"),
        (2, ids[101], s1, None),
    ]
    # 신청자 이름·학번은 자기 학교 관리자에게만
    for path in (f"/api/buildings/{bid}/reservations", f"/api/rooms/{ids[101]}/reservations"):
        assert client.get(path, headers=other_admin_hdr).status_code == 404, path
        assert client.get(path, headers=student_hdr).status_code == 403, path

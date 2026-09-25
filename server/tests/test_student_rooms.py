import datetime as dt

from app.domain import clock
from app.domain.models import Building, ExamPeriod, Reservation, Room, Slot

UTC_NOW = dt.datetime(2026, 9, 23, 1, 30)  # noqa: DTZ001 — KST 9/23(수) 10:30


def _fix_clock(monkeypatch):
    monkeypatch.setattr(clock, "now_utc", lambda: UTC_NOW)


def _building(app, school_id, bld, rooms=((101, 1),), *, reservable=True):
    with app.state.Session() as s, s.begin():
        b = Building(school_id=school_id, name=f"{bld}동", bld=bld)
        s.add(b)
        s.flush()
        ids = {}
        for room, units in rooms:
            r = Room(building_id=b.id, room=room, units=units, reservable=reservable)
            s.add(r)
            s.flush()
            ids[room] = r.id
        bid = b.id
    return bid, ids


def _slot(app, room_id, day, s_h, s_m, e_h, e_m, *, type=1, subject="수업", professor=""):
    with app.state.Session() as s, s.begin():
        s.add(
            Slot(
                room_id=room_id,
                day=day,
                s_h=s_h,
                s_m=s_m,
                e_h=e_h,
                e_m=e_m,
                type=type,
                subject=subject,
                professor=professor,
            )
        )


def _resv(
    app,
    room_id,
    date,
    s_h,
    s_m,
    e_h,
    e_m,
    *,
    id_,
    type=6,
    subject="예약",
    professor="",
    status="approved",
    requested_by=None,
    requested_at=None,
):
    with app.state.Session() as s, s.begin():
        s.add(
            Reservation(
                id=id_,
                room_id=room_id,
                date=date,
                s_h=s_h,
                s_m=s_m,
                e_h=e_h,
                e_m=e_m,
                type=type,
                subject=subject,
                professor=professor,
                status=status,
                requested_by=requested_by,
                requested_at=requested_at,
            )
        )
    return id_


def _exam(app, room_id, id_, date_start, date_end):
    with app.state.Session() as s, s.begin():
        s.add(ExamPeriod(id=id_, room_id=room_id, date_start=date_start, date_end=date_end))


def test_free_rooms_now_and_at(client, client_raw, app, school, student_hdr, monkeypatch):
    _fix_clock(monkeypatch)  # KST 수 10:30
    _, ids = _building(app, 1, "E", rooms=((101, 1), (102, 1), (103, 1)))
    _building(app, 1, "G", rooms=((201, 1),), reservable=False)  # 예약 불가 방 제외
    _building(app, 2, "F", rooms=((101, 1),))  # 타교 제외
    _slot(app, ids[101], 3, 9, 0, 10, 50)  # 101 수업 중
    _resv(app, ids[102], dt.date(2026, 9, 23), 10, 0, 11, 0, id_=1)  # 102 대여 중
    _slot(app, ids[103], 3, 13, 0, 14, 0)  # 103 비어 있음, 13:00 까지
    r = client.get("/api/student/rooms/free", headers=student_hdr)
    assert r.status_code == 200
    assert [(x["room"], x["layout"], x["free_until"]) for x in r.json()] == [(103, 4, "13:00")]
    r = client.get("/api/student/rooms/free?at=2026-09-23T11:00:00", headers=student_hdr)
    assert [x["room"] for x in r.json()] == [101, 102, 103]
    r = client.get(
        "/api/student/rooms/free?at=2026-09-23T01:30:00Z", headers=student_hdr
    )  # = KST 10:30 — now 과 같은 순간, 변환 없으면 달라진다
    assert [(x["room"], x["layout"], x["free_until"]) for x in r.json()] == [(103, 4, "13:00")]
    assert (
        client_raw.get("/api/student/rooms/free").status_code == 401
    )  # client 는 관리자 Bearer 가 붙어 403 이 된다
    assert client.get("/api/student/rooms/free").status_code == 403  # 관리자


def test_rooms_with_state(client, app, school, student_hdr, monkeypatch):
    _fix_clock(monkeypatch)
    bid, ids = _building(app, 1, "E", rooms=((101, 1), (102, 1)))
    _slot(app, ids[101], 3, 9, 0, 10, 50)
    r = client.get(f"/api/student/rooms?building_id={bid}", headers=student_hdr)
    assert [(x["room"], x["layout"], x["until"]) for x in r.json()] == [
        (101, 1, "10:50"),
        (102, 4, None),
    ]
    assert r.json()[0]["building"] == "E동" and r.json()[0]["bld"] == "E"


def test_week_hides_others_and_scopes(
    client, app, school, student_hdr, other_student_hdr, student_hdr_school2, monkeypatch
):
    _fix_clock(monkeypatch)
    _, ids = _building(app, 1, "E")
    rid = ids[101]
    _slot(app, rid, 1, 9, 0, 10, 0)
    _resv(
        app,
        rid,
        dt.date(2026, 9, 24),
        13,
        0,
        14,
        0,
        id_=1,
        requested_by="s1@mju.ac.kr",
        subject="스터디",
    )
    _resv(app, rid, dt.date(2026, 9, 25), 13, 0, 14, 0, id_=2, subject="관리자예약")
    _resv(app, rid, dt.date(2026, 9, 30), 13, 0, 14, 0, id_=3)  # 다음 주 → 제외
    _resv(
        app,
        rid,
        dt.date(2026, 9, 26),
        9,
        0,
        10,
        0,
        id_=4,
        status="requested",
        requested_by="s1@mju.ac.kr",
    )  # 신청 중 → 제외
    _exam(app, rid, 1, dt.date(2026, 9, 21), dt.date(2026, 9, 22))
    r = client.get(f"/api/student/rooms/{rid}/week", headers=student_hdr)
    j = r.json()
    assert r.status_code == 200 and j["week_start"] == "2026-09-21" and j["room"]["room"] == 101
    assert [x["day"] for x in j["slots"]] == [1]
    assert [(x["id"], x["mine"], x["label"]) for x in j["reservations"]] == [
        (1, True, "스터디"),
        (2, False, "관리자예약"),
    ]
    assert [x["id"] for x in j["exams"]] == [1]
    j2 = client.get(f"/api/student/rooms/{rid}/week", headers=other_student_hdr).json()
    assert [(x["id"], x["mine"], x["label"]) for x in j2["reservations"]] == [
        (1, False, "예약됨"),
        (2, False, "관리자예약"),
    ]
    assert (
        client.get(f"/api/student/rooms/{rid}/week?date=2026-09-30", headers=student_hdr).json()[
            "reservations"
        ][0]["id"]
        == 3
    )
    assert (
        client.get(f"/api/student/rooms/{rid}/week", headers=student_hdr_school2).status_code == 404
    )
    assert client.get("/api/student/rooms/999/week", headers=student_hdr).status_code == 404

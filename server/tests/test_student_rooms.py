import datetime as dt

from sqlalchemy import select

from app.domain import clock, reserve, room_state
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


def test_week_busy_merges_and_hides_requesters(
    client, app, school, student_hdr, other_student_hdr, monkeypatch
):
    _fix_clock(monkeypatch)  # KST 수 9/23 10:30 — 주 = 9/21(월)~9/27(일)
    _, ids = _building(app, 1, "E", rooms=((101, 1), (102, 1)))
    rid = ids[101]
    _slot(app, rid, 2, 9, 0, 10, 0, subject="A")
    _slot(app, rid, 2, 10, 0, 11, 0, subject="B")  # 10:00 에 맞닿기만 — 합치지 않는다
    _exam(app, rid, 1, dt.date(2026, 9, 22), dt.date(2026, 9, 22))  # 화요일만 시험기간
    _slot(app, rid, 5, 10, 0, 12, 0, subject="알고리즘")
    _resv(app, rid, dt.date(2026, 9, 25), 11, 0, 13, 0, id_=1, subject="동아리 대관")
    thu = dt.date(2026, 9, 24)
    _resv(
        app,
        rid,
        thu,
        14,
        0,
        15,
        0,
        id_=2,
        status="requested",
        requested_by="s2@mju.ac.kr",
        subject="비밀",
    )
    _resv(
        app,
        rid,
        thu,
        16,
        0,
        17,
        0,
        id_=3,
        status="requested",
        requested_by="s1@mju.ac.kr",
        subject="스터디",
    )
    _resv(app, rid, thu, 18, 0, 19, 0, id_=9, requested_by="s1@mju.ac.kr", subject="내 예약")
    _resv(app, rid, thu, 9, 0, 10, 0, id_=4, status="rejected", requested_by="s2@mju.ac.kr")
    _resv(app, rid, thu, 10, 0, 11, 0, id_=5, status="cancelled")
    _resv(app, rid, thu, 11, 0, 12, 0, id_=6, status="expired", requested_by="s2@mju.ac.kr")
    _resv(app, ids[102], thu, 9, 0, 10, 0, id_=7)  # 다른 방
    _resv(app, rid, dt.date(2026, 9, 28), 9, 0, 10, 0, id_=8)  # 다음 주
    r = client.get(f"/api/student/rooms/{rid}/week", headers=student_hdr)
    assert r.status_code == 200
    assert [d["day"] for d in r.json()["busy"]] == [1, 2, 3, 4, 5, 6, 7]
    busy = {
        d["day"]: [
            (x["from"], x["to"], x["label"], x["type"], x["mine"], x["status"]) for x in d["spans"]
        ]
        for d in r.json()["busy"]
    }
    assert busy == {
        1: [],
        2: [("09:00", "10:00", "A", 2, False, None), ("10:00", "11:00", "B", 2, False, None)],
        3: [],
        4: [
            ("14:00", "15:00", "예약됨", 6, False, None),  # 남의 신청 — 상태도 숨긴다
            ("16:00", "17:00", "스터디", 6, True, "requested"),  # 내 신청(대기)
            ("18:00", "19:00", "내 예약", 6, True, "approved"),
        ],
        5: [("10:00", "13:00", "알고리즘 외 1건", 1, False, None)],
        6: [],
        7: [],
    }
    assert "비밀" not in r.text and "s2@mju.ac.kr" not in r.text  # 남의 신청은 존재만 보인다
    j2 = client.get(f"/api/student/rooms/{rid}/week", headers=other_student_hdr).json()
    assert [(x["label"], x["mine"], x["status"]) for x in j2["busy"][3]["spans"]] == [
        ("비밀", True, "requested"),
        ("예약됨", False, None),
        ("예약됨", False, None),  # s1 의 승인 예약도 남에게는 상태 없이
    ]


def test_week_date_upper_bound_is_422_not_500(client, app, school, student_hdr, monkeypatch):
    _fix_clock(monkeypatch)
    _, ids = _building(app, 1, "E")
    url = f"/api/student/rooms/{ids[101]}/week"
    # 9999-12-27(월) 의 주 끝은 10000년 — 계산하면 OverflowError(500). 범위는 clock.DATE_MIN~MAX
    assert client.get(f"{url}?date=9999-12-27", headers=student_hdr).status_code == 422
    assert client.get(f"{url}?date=2100-01-01", headers=student_hdr).status_code == 422
    j = client.get(f"{url}?date=2099-12-31", headers=student_hdr).json()
    assert j["week_start"] == "2099-12-28" and len(j["busy"]) == 7


def test_week_free_spans_match_what_request_accepts(client, app, school, student_hdr, monkeypatch):
    _fix_clock(monkeypatch)  # KST 수 9/23 10:30
    _, ids = _building(app, 1, "E")
    rid = ids[101]
    _slot(app, rid, 3, 13, 0, 14, 0)  # 수 — 오늘과 다음 주 수요일
    _slot(app, rid, 4, 9, 0, 12, 0, type=4, subject="빈강의실")  # type 무관하게 신청을 막는다
    fri = dt.date(2026, 9, 25)
    _resv(app, rid, fri, 15, 0, 16, 0, id_=1, status="requested", requested_by="s2@mju.ac.kr")
    _resv(app, rid, fri, 17, 0, 18, 0, id_=2, status="cancelled")  # 취소는 막지 않는다
    _slot(app, rid, 6, 9, 0, 10, 2)  # 토 — 끝이 5분 격자 밖
    _slot(app, rid, 6, 10, 12, 11, 0)  # 틈 10:02~10:12 → 격자 안쪽 10:05~10:10 = 5분 < 15분 → 버림
    _slot(app, rid, 7, 7, 0, 9, 30)  # 일 — 운영 시작 전부터
    _slot(app, rid, 1, 20, 0, 22, 0)  # 월 — 운영 끝 뒤까지
    # 화 — 슬롯 없는 시험기간은 신청을 막지 않는다 (reserve.overlaps 와 같다)
    _exam(app, rid, 1, dt.date(2026, 9, 29), dt.date(2026, 9, 29))
    url = f"/api/student/rooms/{rid}/week"

    def free():
        j = client.get(url, headers=student_hdr).json()
        return [(d["date"], [(x["from"], x["to"]) for x in d["spans"]]) for d in j["free"]]

    assert free() == [
        ("2026-09-23", [("10:35", "13:00"), ("14:00", "21:00")]),  # 10:30 지남 → 10:31 뒤 첫 5분
        ("2026-09-24", [("12:00", "21:00")]),
        ("2026-09-25", [("09:00", "15:00"), ("16:00", "21:00")]),  # 남의 신청도 막는다
        ("2026-09-26", [("11:00", "21:00")]),
        ("2026-09-27", [("09:30", "21:00")]),
        ("2026-09-28", [("09:00", "20:00")]),
        ("2026-09-29", [("09:00", "21:00")]),
        ("2026-09-30", [("09:00", "13:00"), ("14:00", "21:00")]),
    ]
    # free 의 경계가 곧 신청이 받아들이는 경계다
    post = f"/api/student/rooms/{rid}/reservations"
    body = {"date": "2026-09-25", "subject": "스터디"}
    t1 = {"s_h": 15, "s_m": 55, "e_h": 16, "e_m": 10}
    t2 = {"s_h": 16, "s_m": 0, "e_h": 16, "e_m": 15}
    assert client.post(post, json=body | t1, headers=student_hdr).status_code == 409
    assert client.post(post, json=body | t2, headers=student_hdr).status_code == 201
    assert free()[2] == ("2026-09-25", [("09:00", "15:00"), ("16:15", "21:00")])  # 내 신청도 뺀다
    # 다른 주를 봐도 free 는 오늘~+7 그대로
    j = client.get(f"{url}?date=2026-10-20", headers=student_hdr).json()
    assert j["week_start"] == "2026-10-19" and j["free"][0]["date"] == "2026-09-23"
    assert j["full"] is False


def test_week_free_uses_kst_today_and_operating_hours(
    client, app, school, student_hdr, monkeypatch
):
    _, ids = _building(app, 1, "E")
    url = f"/api/student/rooms/{ids[101]}/week"

    def at(utc):
        monkeypatch.setattr(clock, "now_utc", lambda: utc)
        return client.get(url, headers=student_hdr).json()["free"]

    j = at(dt.datetime(2026, 9, 23, 15, 10))  # noqa: DTZ001 — KST 9/24(목) 00:10
    assert [d["date"] for d in j] == [
        str(dt.date(2026, 9, 24) + dt.timedelta(days=i)) for i in range(8)
    ]
    assert j[0]["spans"] == [{"from": "09:00", "to": "21:00"}]  # 새벽 — 운영 시작부터
    j = at(dt.datetime(2026, 9, 23, 11, 40))  # noqa: DTZ001 — KST 20:40
    assert j[0]["spans"] == [{"from": "20:45", "to": "21:00"}]  # 딱 15분
    j = at(dt.datetime(2026, 9, 23, 11, 50))  # noqa: DTZ001 — KST 20:50
    assert j[0] == {"date": "2026-09-23", "spans": []}  # 20:55~21:00 은 15분 미만
    assert j[1]["spans"] == [{"from": "09:00", "to": "21:00"}]


def test_week_does_not_straddle_midnight_across_two_clock_reads(
    client, app, school, student_hdr, monkeypatch
):
    """/week 가 시계를 두 번 읽으면(local_now·local_today 각각) 그 사이 자정이 지나 week_start 와
    room 상태가 다른 날 기준으로 계산될 수 있다 — 한 번 읽은 now 를 끝까지 써야 한다."""
    _, ids = _building(app, 1, "E")
    # KST 9/27(일) 23:59:59.5 → 다음 호출부터는 9/28(월) 00:00:00.5 로 자정 + 주 경계를 같이 넘긴다
    before = dt.datetime(2026, 9, 27, 14, 59, 59, 500000)  # noqa: DTZ001 — UTC, KST 일 23:59:59.5
    after = dt.datetime(2026, 9, 27, 15, 0, 0, 500000)  # noqa: DTZ001 — UTC, KST 월 00:00:00.5
    calls = iter([before, after, after, after, after])
    monkeypatch.setattr(clock, "now_utc", lambda: next(calls, after))
    j = client.get(f"/api/student/rooms/{ids[101]}/week", headers=student_hdr).json()
    assert j["week_start"] == "2026-09-21"  # 첫 읽음(일, 9/27)이 속한 주 — 9/28(월)치면 버그


def test_week_full_flag_empties_free(client, app, school, student_hdr, monkeypatch):
    _fix_clock(monkeypatch)
    monkeypatch.setattr(reserve, "NODE_RESV_MAX", 1)  # 창 안 1건이면 가득 — 신청은 409
    _, ids = _building(app, 1, "E")
    _resv(app, ids[101], dt.date(2026, 9, 26), 9, 0, 10, 0, id_=1)
    j = client.get(f"/api/student/rooms/{ids[101]}/week", headers=student_hdr).json()
    assert j["full"] is True  # 화면은 '예약이 가득 찼어요' — '빈 시간 없음' 이 아니라
    assert len(j["free"]) == 8 and all(d["spans"] == [] for d in j["free"])


def _count_sql(app):
    from sqlalchemy import event

    n = [0]
    event.listen(app.state.engine, "before_cursor_execute", lambda *a: n.__setitem__(0, n[0] + 1))
    return n


def _mixed_rooms(app, n):
    """방 n 개 — 수업·휴강·예약(승인·신청)·시험기간을 섞는다. 응답 스냅숏 비교용."""
    bid, ids = _building(app, 1, "E", rooms=tuple((100 + i, 1) for i in range(n)))
    d = dt.date(2026, 9, 23)  # 수
    for i, rid in enumerate(ids.values()):
        if i % 5 == 0:
            _slot(app, rid, 3, 9, 0, 10, 50)
        if i % 5 == 1:
            _slot(app, rid, 3, 10, 0, 12, 0, type=3, subject="휴강")
        if i % 5 == 2:
            _resv(app, rid, d, 10, 0, 11, 0, id_=1000 + i)
            _resv(app, rid, d, 10, 0, 11, 0, id_=2000 + i, status="requested")
        if i % 5 == 3:
            _slot(app, rid, 3, 10, 0, 11, 0)
            _exam(app, rid, 3000 + i, d, d)
        if i % 7 == 0:
            _slot(app, rid, 3, 13, 0, 14, 0)
    return bid, ids


def test_student_rooms_and_free_are_constant_queries_and_unchanged(
    client, app, school, student_hdr, monkeypatch
):
    """#49 리뷰: 방마다 쿼리 3개(N+1) → 방 수와 무관한 상수. 응답은 방별 state_of(옛 경로)와 같다."""
    _fix_clock(monkeypatch)  # KST 수 10:30
    _mixed_rooms(app, 30)
    n = _count_sql(app)
    urls = (
        "/api/student/rooms",
        "/api/student/rooms/free",
        "/api/student/rooms/free?at=2026-09-23T13:10:00",
    )
    counts = {}
    for u in urls:
        n[0] = 0
        r = client.get(u, headers=student_hdr)
        assert r.status_code == 200
        counts[u] = n[0]
        # 스냅숏 = 방별 state_of (배치 전 구현이 쓰던 경로)
        at = dt.datetime(2026, 9, 23, 13, 10) if "at=" in u else clock.local_now()  # noqa: DTZ001 — KST naive
        with app.state.Session() as s:
            want = []
            for room in s.scalars(select(Room).order_by(Room.room)):
                layout, until = room_state.state_of(s, room.id, at)
                want.append((room.room, layout, room_state.fmt_hhmm(until)))
        key = "free_until" if "free" in u else "until"
        got = [(x["room"], x["layout"], x[key]) for x in r.json()]
        assert got == ([w for w in want if w[1] == room_state.FREE] if "free" in u else want)
    # 방 1개(building_id 로 좁힘)일 때와 쿼리 수가 같다
    b2, _ = _building(app, 1, "Z", rooms=((1, 1),))
    for u in ("/api/student/rooms", "/api/student/rooms/free"):
        n[0] = 0
        assert client.get(f"{u}?building_id={b2}", headers=student_hdr).status_code == 200
        assert n[0] == counts[u], (u, n[0], counts[u])

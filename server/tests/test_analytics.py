import datetime as dt

from app.domain import analytics as A
from app.domain import clock
from app.domain.models import Building, ExamPeriod, Reservation, Room, Slot
from app.lora_service.models import Modem, Outbox

UTC_NOW = dt.datetime(2026, 9, 23, 1, 30)  # noqa: DTZ001 — KST 9/23(수) 10:30


def _fix_clock(monkeypatch):
    monkeypatch.setattr(clock, "now_utc", lambda: UTC_NOW)


def _building(app, school_id, bld, rooms=((101, 1),)):
    with app.state.Session() as s, s.begin():
        b = Building(school_id=school_id, name=f"{bld}동", bld=bld)
        s.add(b)
        s.flush()  # 부모 먼저
        ids = {}
        for room, units in rooms:
            r = Room(building_id=b.id, room=room, units=units, reservable=True)
            s.add(r)
            s.flush()
            ids[room] = r.id
        bid = b.id
    return bid, ids


def _slot(app, room_id, day, s_h, s_m, e_h, e_m, *, type_=1):
    with app.state.Session() as s, s.begin():
        s.add(
            Slot(
                room_id=room_id,
                day=day,
                s_h=s_h,
                s_m=s_m,
                e_h=e_h,
                e_m=e_m,
                type=type_,
                subject="수업",
                professor="",
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
    status="approved",
    requested_by=None,
    requested_at=None,
    checked_in_at=None,
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
                type=6,
                subject="예약",
                professor="",
                status=status,
                requested_by=requested_by,
                requested_at=requested_at,
                checked_in_at=checked_in_at,
            )
        )


def _acked(app, bld, room, type_, created, secs, modem_id=None):
    with app.state.Session() as s, s.begin():
        s.add(
            Outbox(
                bld=bld,
                room=room,
                unit=1,
                type=type_,
                payload="{}",
                state="acked",
                created_at=created,
                finished_at=created + dt.timedelta(seconds=secs),
                modem_id=modem_id,
            )
        )


def test_day_segments_and_allocation(app, school, monkeypatch):
    _fix_clock(monkeypatch)
    bid, ids = _building(app, 1, "E", rooms=((101, 1), (102, 1)))
    rid = ids[101]
    _slot(app, rid, 3, 9, 0, 10, 50)  # 수 110 분 수업(1·2)
    _slot(app, rid, 3, 11, 0, 12, 0, type_=3)  # 휴강 60 분 → unused
    _resv(app, rid, dt.date(2026, 9, 23), 13, 0, 14, 0, id_=1)  # 60 분 대여
    _slot(app, rid, 3, 20, 0, 22, 0)  # 운영 시간 밖 21~22 는 잘림 → 60 분
    with app.state.Session() as s:
        segs = A.day_segments(s, rid, dt.date(2026, 9, 23))
        assert segs == [
            (540, 590, 1),
            (590, 600, 2),
            (600, 650, 1),
            (660, 720, 3),
            (780, 840, 7),
            (1200, 1250, 1),
            (1250, 1260, 2),
        ]
        rows = A.allocation(s, 1, dt.date(2026, 9, 23), dt.date(2026, 9, 23), None, "room")
        r101 = next(r for r in rows if r["key"] == rid)
        assert (r101["assigned_min"], r101["unused_min"], r101["total_min"]) == (290, 60, 720)
        assert r101["rate"] == round(290 / 720, 4) and r101["label"] == "E동 101"
        assert next(r for r in rows if r["key"] == ids[102])["assigned_min"] == 0
        by_b = A.allocation(s, 1, dt.date(2026, 9, 23), dt.date(2026, 9, 23), None, "building")
        assert by_b[0]["key"] == bid and by_b[0]["total_min"] == 1440
        assert by_b[0]["assigned_min"] == 290
        by_w = A.allocation(s, 1, dt.date(2026, 9, 21), dt.date(2026, 9, 27), None, "weekday")
        assert by_w[0]["key"] == 3 and by_w[0]["label"] == "수"  # rate desc — 수요일만 배정


def test_range_loader_matches_day_segments_with_exam(app, school, monkeypatch):
    _fix_clock(monkeypatch)
    _, ids = _building(app, 1, "E", rooms=((101, 1),))
    rid = ids[101]
    _slot(app, rid, 2, 9, 0, 10, 50)  # 화
    _slot(app, rid, 3, 9, 0, 10, 50)  # 수
    _resv(app, rid, dt.date(2026, 9, 22), 13, 0, 14, 0, id_=1)
    with app.state.Session() as s, s.begin():
        s.add(
            ExamPeriod(room_id=rid, date_start=dt.date(2026, 9, 23), date_end=dt.date(2026, 9, 23))
        )
    with app.state.Session() as s:
        assert A.day_segments(s, rid, dt.date(2026, 9, 23)) == [(540, 650, 5)]  # 시험기간
        inputs = A._inputs_range(s, [rid], dt.date(2026, 9, 21), dt.date(2026, 9, 27))
        for i in range(7):
            d = dt.date(2026, 9, 21) + dt.timedelta(days=i)
            assert A._segments(*inputs(rid, d)) == A.day_segments(s, rid, d)


def test_free_slots_merge(app, school, monkeypatch):
    _fix_clock(monkeypatch)
    _, ids = _building(app, 1, "E", rooms=((101, 1),))
    rid = ids[101]
    _slot(app, rid, 3, 9, 0, 10, 0)
    _slot(app, rid, 3, 10, 0, 11, 0)  # 연속 → 빈 구간 없음
    _slot(app, rid, 3, 15, 0, 16, 0)
    with app.state.Session() as s:
        out = A.free_slots(s, 1, dt.date(2026, 9, 23), None)
        assert out[0]["room"] == 101
        assert out[0]["free"] == [
            {"from": "11:00", "to": "15:00"},
            {"from": "16:00", "to": "21:00"},
        ]


def test_reservation_stats_and_no_show(app, school, students, monkeypatch):
    _fix_clock(monkeypatch)
    _, ids = _building(app, 1, "E", rooms=((101, 1),))
    rid = ids[101]
    d = dt.date(2026, 9, 22)
    s1, s2 = "s1@mju.ac.kr", "s2@mju.ac.kr"
    _resv(app, rid, d, 9, 0, 10, 0, id_=1, requested_by=s1, requested_at=UTC_NOW)  # no_show
    _resv(
        app,
        rid,
        d,
        10,
        0,
        11,
        0,
        id_=2,
        requested_by=s1,
        requested_at=UTC_NOW,
        checked_in_at=UTC_NOW,
    )
    _resv(
        app,
        rid,
        d,
        11,
        0,
        12,
        0,
        id_=3,
        status="rejected",
        requested_by=s2,
        requested_at=UTC_NOW,
    )
    _resv(  # 미래 → no_show 아님
        app,
        rid,
        dt.date(2026, 9, 24),
        11,
        0,
        12,
        0,
        id_=4,
        requested_by=s2,
        requested_at=UTC_NOW,
    )
    _resv(app, rid, d, 13, 0, 14, 0, id_=5)  # 관리자 예약 → 통계 제외
    _resv(  # 대기 중 신청 — requested 에 한 번만 센다
        app, rid, dt.date(2026, 9, 24), 13, 0, 14, 0, id_=6, status="requested", requested_by=s1
    )
    with app.state.Session() as s:
        st = A.reservation_stats(s, 1, d, dt.date(2026, 9, 24), "day", clock.local_now())
        assert st["totals"] == {
            "requested": 5,
            "approved": 3,
            "rejected": 1,
            "cancelled": 0,
            "expired": 0,
            "no_show": 1,
            "checked_in": 1,
        }
        assert st["no_show_rate"] == 0.5 and st["checkin_rate"] == 0.5
        assert [x["date"] for x in st["series"]] == ["2026-09-22", "2026-09-23", "2026-09-24"]
        assert st["series"][0]["approved"] == 2 and st["series"][2]["approved"] == 1
        assert st["series"][2]["requested"] == 2


def test_latency_bins_and_samples(app, school, monkeypatch):
    _fix_clock(monkeypatch)
    _building(app, 1, "E", rooms=((101, 1),))
    _building(app, 2, "F", rooms=((101, 1),))
    day_ago = UTC_NOW - dt.timedelta(days=1)
    for secs in (5, 12, 25, 31, 50, 95, 130):
        _acked(app, "E", 101, "SLOT_SET", day_ago, secs)
    _acked(app, "E", 101, "RESV_SET", day_ago, 8)
    _acked(app, "E", 101, "FILE", day_ago, 3)  # 제외
    _acked(app, "F", 101, "SLOT_SET", day_ago, 1)  # 타교
    _acked(app, "E", 101, "SLOT_SET", UTC_NOW - dt.timedelta(days=40), 1)  # 창 밖
    with app.state.Session() as s:
        d0, d1 = dt.date(2026, 8, 25), dt.date(2026, 9, 23)
        lat = A.latency(s, 1, d0, d1, "all")
        assert lat["n"] == 8 and lat["max"] == 130 and lat["p50"] == 25 and lat["p95"] == 95
        assert [b["count"] for b in lat["bins"]] == [2, 1, 1, 1, 1, 0, 1, 1]
        assert lat["bins"][-1] == {"ge": 120, "lt": None, "count": 1}
        assert lat["within_30s"] == round(4 / 8, 4) and lat["within_90s"] == round(6 / 8, 4)
        assert A.latency(s, 1, d0, d1, "RESV_SET")["n"] == 1
        smp = A.latency_samples(s, 1, d0, d1, "all", 3)
        assert len(smp) == 3 and smp[0]["seconds"] in (5, 12, 25, 31, 50, 95, 130, 8)
        assert smp[0]["room"] == 101


def test_latency_excludes_other_school_modem_on_bld_reuse(app, school, monkeypatch):
    _fix_clock(monkeypatch)
    _building(app, 1, "E", rooms=((101, 1),))
    with app.state.Session() as s, s.begin():
        s.add(Modem(modem_id="m2", token_hash="x", school_id=2))
    day_ago = UTC_NOW - dt.timedelta(days=1)
    _acked(app, "E", 101, "SLOT_SET", day_ago, 7, modem_id="m2")  # 학교 2 모뎀의 옛 행
    _acked(app, "E", 101, "SLOT_SET", day_ago, 9)
    _acked(app, "E", 101, "SLOT_SET", day_ago, -3)  # 시계 역행 → 0 s 로 첫 bin
    with app.state.Session() as s:
        d0, d1 = dt.date(2026, 8, 25), dt.date(2026, 9, 23)
        lat = A.latency(s, 1, d0, d1, "all")
        assert lat["n"] == 2 and sum(b["count"] for b in lat["bins"]) == 2
        assert sorted(x["seconds"] for x in A.latency_samples(s, 1, d0, d1, "all", 10)) == [0, 9]


def test_parse_range_and_endpoints(client, app, school, student_hdr, monkeypatch):
    _fix_clock(monkeypatch)
    today = dt.date(2026, 9, 23)
    assert A.parse_range(None, None, today) == (dt.date(2026, 8, 25), today)
    _building(app, 1, "E", rooms=((101, 1),))
    base = "/api/admin/analytics"
    assert client.get(f"{base}/allocation").status_code == 200
    assert client.get(f"{base}/allocation?from=2026-01-01&to=2026-09-23").status_code == 422
    assert client.get(f"{base}/allocation?from=2026-09-23&to=2026-09-22").status_code == 422
    free = client.get(f"{base}/free-slots?date=2026-09-23").json()
    assert free[0]["room"] == 101 and free[0]["free"] == [{"from": "09:00", "to": "21:00"}]
    assert client.get(f"{base}/reservations").json()["totals"]["requested"] == 0
    assert client.get(f"{base}/latency").json()["n"] == 0
    assert client.get(f"{base}/latency/samples").json() == []
    assert client.get(f"{base}/allocation", headers=student_hdr).status_code == 403


def test_extreme_dates_are_422_not_500(client, app, school, student_hdr, monkeypatch):
    """#49 리뷰: 날짜 계산(±일·시간대)이 OverflowError(500) 가 되던 극단값 → 공용 범위 검사로 422."""
    _fix_clock(monkeypatch)
    _, ids = _building(app, 1, "E", rooms=((101, 1),))
    st = "/api/student"
    ad = "/api/admin"
    bad_student = [
        f"{st}/rooms/{ids[101]}/week?date=9999-12-31",
        f"{st}/rooms/free?at=0001-01-01T00:00:00%2B14:00",
        f"{st}/rooms/free?at=9999-12-31T23:59:00-14:00",
    ]
    bad_admin = [
        f"{ad}/analytics/allocation?to=0001-01-01",
        f"{ad}/analytics/latency?from=9999-12-30&to=9999-12-31",
        f"{ad}/analytics/latency/samples?from=9999-12-30&to=9999-12-31",
        f"{ad}/analytics/reservations?to=0001-01-01",
        f"{ad}/analytics/free-slots?date=9999-12-31",
        f"{ad}/reservations?date_from=0001-01-01",
        f"{ad}/reservations?date_to=9999-12-31",
    ]
    for u in bad_student:
        assert client.get(u, headers=student_hdr).status_code == 422, u
    for u in bad_admin:
        assert client.get(u).status_code == 422, u
    ok_student = [
        f"{st}/rooms/{ids[101]}/week?date=2026-09-23",
        f"{st}/rooms/free?at=2026-09-23T01:30:00Z",
    ]
    for u in ok_student:
        assert client.get(u, headers=student_hdr).status_code == 200, u
    for u in (
        f"{ad}/analytics/allocation?to=2026-09-23",
        f"{ad}/analytics/latency?from=2026-09-01&to=2026-09-23",
        f"{ad}/analytics/free-slots?date=2026-09-23",
        f"{ad}/reservations?date_from=2026-09-01&date_to=2026-09-30",
    ):
        assert client.get(u).status_code == 200, u

import datetime as dt

from sqlalchemy import select

from app.domain import clock
from app.domain.models import Building, Reservation, Room
from app.lora_service.models import Outbox

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
    pushed_at=None,
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
                pushed_at=pushed_at,
            )
        )
    return id_


def test_list_scope_and_filters(client, app, school, students, other_admin_hdr, monkeypatch):
    _fix_clock(monkeypatch)
    bid, ids = _building(app, 1, "E")
    _, ids2 = _building(app, 2, "F")
    _resv(
        app,
        ids[101],
        dt.date(2026, 9, 24),
        13,
        0,
        14,
        0,
        id_=1,
        status="requested",
        requested_by="s1@mju.ac.kr",
        requested_at=UTC_NOW,
    )
    _resv(app, ids[101], dt.date(2026, 9, 25), 13, 0, 14, 0, id_=2, status="approved")
    _resv(
        app,
        ids2[101],
        dt.date(2026, 9, 24),
        13,
        0,
        14,
        0,
        id_=3,
        status="requested",
        requested_by="s3@other.ac.kr",
    )
    r = client.get("/api/admin/reservations")
    assert r.status_code == 200 and [x["id"] for x in r.json()] == [1]
    assert r.json()[0]["requester"] == {
        "email": "s1@mju.ac.kr",
        "name": "학생1",
        "student_no": "S1",
    }
    assert [x["id"] for x in client.get("/api/admin/reservations?status=approved").json()] == [2]
    assert client.get("/api/admin/reservations?status=approved").json()[0]["requester"] is None
    assert [
        x["id"]
        for x in client.get(
            f"/api/admin/reservations?status=requested,approved&building_id={bid}"
        ).json()
    ] == [1, 2]
    assert (
        client.get(
            "/api/admin/reservations?status=approved&date_from=2026-09-25&date_to=2026-09-25"
        ).json()[0]["id"]
        == 2
    )
    assert [
        x["id"] for x in client.get("/api/admin/reservations", headers=other_admin_hdr).json()
    ] == [3]
    assert (
        client.get(
            "/api/admin/reservations",
            headers=dict(client.headers) | {"Authorization": other_admin_hdr["Authorization"]},
        ).status_code
        == 200
    )


def test_approve_reject_cancel_and_summary_bucket(client, live, app, school, students, monkeypatch):
    _fix_clock(monkeypatch)
    _, ids = _building(app, 1, "E", rooms=((301, 2),))
    rid = ids[301]
    _resv(
        app,
        rid,
        dt.date(2026, 9, 24),
        13,
        0,
        14,
        0,
        id_=1,
        status="requested",
        requested_by="s1@mju.ac.kr",
        requested_at=UTC_NOW,
    )
    _resv(
        app,
        rid,
        dt.date(2026, 9, 24),
        15,
        0,
        16,
        0,
        id_=2,
        status="requested",
        requested_by="s2@mju.ac.kr",
        requested_at=UTC_NOW,
    )
    j = client.get("/api/admin/summary").json()
    assert (
        j["warnings"]["pending_reservations"]["count"] == 2
        and j["warnings"]["pending_reservations"]["items"][0]["id"] == 1
    )
    r = client.post("/api/admin/reservations/1/approve")
    assert r.status_code == 200 and r.json()["status"] == "approved" and r.json()["decided_at"]
    assert client.post("/api/admin/reservations/1/approve").status_code == 409
    r = client.post("/api/admin/reservations/2/reject", json={"reason": "사유"})
    assert r.json()["status"] == "rejected" and r.json()["reject_reason"] == "사유"
    r = client.post("/api/admin/reservations/1/cancel")
    assert r.json()["status"] == "cancelled"
    assert client.post("/api/admin/reservations/999/approve").status_code == 404
    with live() as s:
        assert [o.type for o in s.scalars(select(Outbox).order_by(Outbox.id))] == [
            "RESV_SET",
            "RESV_SET",
            "RESV_DEL",
            "RESV_DEL",
        ]
    assert client.get("/api/admin/summary").json()["warnings"]["pending_reservations"]["count"] == 0


def test_status_filter_validated(client, app, school, student_hdr):
    for q in ("status=bogus", "status=requested,", "status="):
        assert client.get(f"/api/admin/reservations?{q}").status_code == 422, q
        assert (
            client.get(f"/api/student/me/reservations?{q}", headers=student_hdr).status_code == 422
        )
    assert client.get("/api/admin/reservations?status=approved,expired").status_code == 200
    assert (
        client.get("/api/student/me/reservations?status=cancelled", headers=student_hdr).status_code
        == 200
    )


def test_summary_pending_uses_injected_now(app, school, students):
    from app.domain import admin

    _, ids = _building(app, 1, "E")
    _resv(
        app, ids[101], dt.date(2030, 1, 1), 13, 0, 14, 0, id_=1, status="requested",
        requested_by="s1@mju.ac.kr", requested_at=UTC_NOW,
    )  # fmt: skip
    with app.state.Session() as s:
        at = admin.summary(s, 1, now=dt.datetime(2030, 1, 1, 3, 59))  # noqa: DTZ001 — KST 12:59
        assert at["warnings"]["pending_reservations"]["count"] == 1
        at = admin.summary(s, 1, now=dt.datetime(2030, 1, 1, 4, 0))  # noqa: DTZ001 — KST 13:00
        assert at["warnings"]["pending_reservations"]["count"] == 0


def test_actions_scope_and_state_conflicts(client, live, app, school, students, monkeypatch):
    _fix_clock(monkeypatch)  # KST 9/23 10:30
    _, ids = _building(app, 1, "E", rooms=((301, 2), (302, 1)))
    _, ids2 = _building(app, 2, "F")
    req = {"status": "requested", "requested_by": "s1@mju.ac.kr", "requested_at": UTC_NOW}
    _resv(app, ids2[101], dt.date(2026, 9, 24), 13, 0, 14, 0, id_=1, **req)  # 타교
    for act in ("approve", "cancel"):
        assert client.post(f"/api/admin/reservations/1/{act}").status_code == 404
    assert client.post("/api/admin/reservations/1/reject", json={"reason": "x"}).status_code == 404
    _resv(app, ids[301], dt.date(2026, 9, 23), 10, 0, 11, 0, id_=2, **req)  # 이미 시작
    assert client.post("/api/admin/reservations/2/approve").status_code == 409
    for i in range(24):  # 302 는 노드 용량만큼 찼다
        _resv(app, ids[302], dt.date(2026, 9, 25), 0, 0, 0, 5, id_=100 + i)
    _resv(app, ids[302], dt.date(2026, 9, 24), 13, 0, 14, 0, id_=3, **req)
    assert client.post("/api/admin/reservations/3/approve").status_code == 409
    # 틀린 상태: requested 는 취소 불가, approved 는 거절 불가
    assert client.post("/api/admin/reservations/3/cancel").status_code == 409
    assert (
        client.post("/api/admin/reservations/100/reject", json={"reason": "x"}).status_code == 409
    )


def test_list_carries_pushed_at(client, app, school, students, monkeypatch):
    _fix_clock(monkeypatch)
    _, ids = _building(app, 1, "E")
    _resv(app, ids[101], dt.date(2026, 9, 24), 13, 0, 14, 0, id_=1, pushed_at=UTC_NOW)
    _resv(app, ids[101], dt.date(2026, 12, 1), 13, 0, 14, 0, id_=2)  # 창 밖 — 아직 안 보냄
    got = client.get("/api/admin/reservations?status=approved").json()
    assert [(x["id"], x["pushed_at"]) for x in got] == [(1, "2026-09-23T01:30:00"), (2, None)]


def test_list_limit_and_hides_started_requests(client, app, school, students, monkeypatch):
    """#49 리뷰: limit 없음 → ?limit (기본 500, 1..1000). 시작 지난 신청은 승인 불가(409)라 목록에서 뺀다
    (summary.pending_reservations 와 같은 규칙). 다른 상태는 그대로."""
    _fix_clock(monkeypatch)  # KST 9/23 10:30
    _, ids = _building(app, 1, "E")
    today, tmr = dt.date(2026, 9, 23), dt.date(2026, 9, 24)
    req = {"status": "requested", "requested_by": "s1@mju.ac.kr", "requested_at": UTC_NOW}
    _resv(app, ids[101], dt.date(2026, 9, 22), 13, 0, 14, 0, id_=1, **req)  # 어제
    _resv(app, ids[101], today, 10, 30, 11, 0, id_=2, **req)  # 방금 시작(10:30) — 승인 불가
    _resv(app, ids[101], today, 10, 35, 11, 0, id_=3, **req)  # 아직
    _resv(app, ids[101], tmr, 9, 0, 10, 0, id_=4, **req)
    _resv(app, ids[101], today, 9, 0, 10, 0, id_=5, status="approved")  # 지난 승인은 그대로
    assert [x["id"] for x in client.get("/api/admin/reservations").json()] == [3, 4]
    assert [
        x["id"] for x in client.get("/api/admin/reservations?status=requested,approved").json()
    ] == [5, 3, 4]
    assert [x["id"] for x in client.get("/api/admin/reservations?limit=1").json()] == [3]
    for bad in ("0", "1001"):
        assert client.get(f"/api/admin/reservations?limit={bad}").status_code == 422
    with app.state.Session() as s:
        from app.domain import admin

        assert [x["id"] for x in admin.pending_reservations(s, 1, clock.local_now())] == [3, 4]

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

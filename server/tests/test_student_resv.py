import datetime as dt

from sqlalchemy import select

from app.domain import clock
from app.domain.models import Building, Reservation, Room, Slot
from app.lora_service import api
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


BODY = {"date": "2026-09-24", "s_h": 13, "s_m": 0, "e_h": 14, "e_m": 0, "subject": "스터디"}


def test_request_list_withdraw(client, app, school, student_hdr, other_student_hdr, monkeypatch):
    _fix_clock(monkeypatch)
    _, ids = _building(app, 1, "E")
    rid = ids[101]
    r = client.post(f"/api/student/rooms/{rid}/reservations", json=BODY, headers=student_hdr)
    assert r.status_code == 201, r.text
    j = r.json()
    assert (
        j["status"] == "requested"
        and j["id"] == 1
        and j["type"] == 6
        and j["room"] == 101
        and j["building"] == "E동"
    )
    assert (
        client.post(
            f"/api/student/rooms/{rid}/reservations", json=BODY, headers=other_student_hdr
        ).status_code
        == 409
    )  # 선착순
    assert (
        client.post(
            f"/api/student/rooms/{rid}/reservations", json={**BODY, "e_m": 3}, headers=student_hdr
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/student/rooms/{rid}/reservations",
            json={**BODY, "date": "2026-10-05"},
            headers=student_hdr,
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/student/rooms/999/reservations", json=BODY, headers=student_hdr
        ).status_code
        == 404
    )
    mine = client.get("/api/student/me/reservations", headers=student_hdr).json()
    assert [x["id"] for x in mine] == [1] and "requested_at" in mine[0]
    assert client.get("/api/student/me/reservations", headers=other_student_hdr).json() == []
    assert (
        client.post("/api/student/me/reservations/1/cancel", headers=other_student_hdr).status_code
        == 404
    )
    r = client.post("/api/student/me/reservations/1/cancel", headers=student_hdr)
    assert r.status_code == 200 and r.json()["status"] == "cancelled"  # 신청 철회
    assert (
        client.get(
            "/api/student/me/reservations?status=requested,cancelled", headers=student_hdr
        ).json()
        == []
    )  # 행 삭제
    assert (
        client.post("/api/student/me/reservations/1/cancel", headers=student_hdr).status_code == 404
    )
    assert (
        client.post(
            f"/api/student/rooms/{rid}/reservations", json=BODY, headers=student_hdr
        ).json()["id"]
        == 1
    )  # id 재사용


def test_daily_request_cap(client, app, school, student_hdr, monkeypatch):
    from app.domain import student_router

    _fix_clock(monkeypatch)
    monkeypatch.setattr(student_router, "DAILY_REQUESTS", 1)
    _, ids = _building(app, 1, "E")
    assert (
        client.post(
            f"/api/student/rooms/{ids[101]}/reservations", json=BODY, headers=student_hdr
        ).status_code
        == 201
    )
    r = client.post(
        f"/api/student/rooms/{ids[101]}/reservations",
        json={**BODY, "s_h": 15, "e_h": 16},
        headers=student_hdr,
    )
    assert r.status_code == 429  # 신청·철회 반복으로 id 를 소진하지 못하게 (리뷰 🟡)


def test_concurrent_requests_cannot_both_pass(
    client, app, school, student_hdr, other_student_hdr, monkeypatch
):
    """검증이 락 밖이면 동시 두 신청이 둘 다 requested → 승인 재검사에서 서로 막혀 둘 다 409 (r2 🟡).
    검증~커밋이 _ID_LOCK 안이므로 둘째는 첫째의 커밋을 보고 409. (sync 핸들러는 스레드풀에서 동시에 돈다.)"""
    import threading

    _fix_clock(monkeypatch)
    _, ids = _building(app, 1, "E")
    hdrs = [student_hdr, other_student_hdr]
    gate, codes = threading.Barrier(2), []

    def go(h):
        gate.wait()
        codes.append(
            client.post(
                f"/api/student/rooms/{ids[101]}/reservations", json=BODY, headers=h
            ).status_code
        )

    ts = [threading.Thread(target=go, args=(h,)) for h in hdrs]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert sorted(codes) == [201, 409]


def test_cancel_approved_sends_resv_del_and_checkin_window(
    client, live, app, school, student_hdr, monkeypatch
):
    seen = []
    monkeypatch.setattr(api, "notify", lambda mid: seen.append(mid))  # 커밋 뒤 호출되는지 (S2c)
    _fix_clock(monkeypatch)
    _, ids = _building(app, 1, "E", rooms=((301, 2),))
    rid = ids[301]
    a = _resv(
        app,
        rid,
        dt.date(2026, 9, 24),
        13,
        0,
        14,
        0,
        id_=1,
        status="approved",
        requested_by="s1@mju.ac.kr",
        pushed_at=UTC_NOW,
    )  # 노드에 가 있음
    b = _resv(
        app,
        rid,
        dt.date(2026, 9, 23),
        10,
        25,
        11,
        0,
        id_=2,
        status="approved",
        requested_by="s1@mju.ac.kr",
    )  # 시작 5분 전
    r = client.post(f"/api/student/me/reservations/{b}/checkin", headers=student_hdr)
    assert r.status_code == 200 and r.json()["checked_in_at"]
    assert (
        client.post(f"/api/student/me/reservations/{a}/checkin", headers=student_hdr).status_code
        == 409
    )  # 내일
    assert (
        client.post(f"/api/student/me/reservations/{b}/cancel", headers=student_hdr).status_code
        == 409
    )  # 10:25 시작, 지금 10:30 → 이미 시작
    r = client.post(f"/api/student/me/reservations/{a}/cancel", headers=student_hdr)
    assert r.status_code == 200
    with live() as s:
        assert [o.type for o in s.scalars(select(Outbox))] == ["RESV_DEL", "RESV_DEL"]  # 유닛 2
    assert seen == [None]  # 테스트 건물엔 modem 없음 — 호출 자체는 됐다

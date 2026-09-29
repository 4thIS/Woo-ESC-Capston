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
    assert j["checked_out_at"] is None  # 조기 퇴실 칸 — 새 신청은 비어 있다
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
    client, live, app, school, student_hdr, other_student_hdr, monkeypatch
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
    )  # 10:25 시작 — 지금 10:30, 5분 지남(체크인 창 안)
    r = client.post(f"/api/student/me/reservations/{b}/checkin", headers=student_hdr)
    assert r.status_code == 200 and r.json()["checked_in_at"]
    url = f"/api/student/me/reservations/{b}/checkin"
    assert client.post(url, headers=other_student_hdr).status_code == 404  # 남의 예약
    assert client.post(url, headers=student_hdr).status_code == 409  # 두 번째 체크인
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
    url = f"/api/student/me/reservations/{a}/cancel"
    assert client.post(url, headers=student_hdr).status_code == 409  # 이미 cancelled
    with live() as s:
        assert [o.type for o in s.scalars(select(Outbox))] == ["RESV_DEL", "RESV_DEL"]  # 유닛 2
    assert seen == [None]  # 테스트 건물엔 modem 없음 — 호출 자체는 됐다


# ---- 조기 퇴실 (docs/specs/2026-09-29-early-checkout-design.md) — 지금 KST 9/23 10:30 ----
def _checked_in(app, rid, id_, s_h, s_m, e_h, e_m, *, pushed=True):
    _resv(
        app,
        rid,
        dt.date(2026, 9, 23),
        s_h,
        s_m,
        e_h,
        e_m,
        id_=id_,
        status="approved",
        requested_by="s1@mju.ac.kr",
        pushed_at=UTC_NOW if pushed else None,
    )
    with app.state.Session() as s, s.begin():
        s.get(Reservation, id_).checked_in_at = UTC_NOW
    return id_


def test_checkout_frees_room(
    client, live, app, school, student_hdr, other_student_hdr, monkeypatch
):
    _fix_clock(monkeypatch)
    _, ids = _building(app, 1, "E", rooms=((301, 1),))
    rid = ids[301]
    a = _checked_in(app, rid, 1, 10, 0, 12, 0)  # 10:00~12:00, 지금 10:30
    url = f"/api/student/me/reservations/{a}/checkout"
    assert client.post(url, headers=other_student_hdr).status_code == 404  # 남의 예약
    r = client.post(url, headers=student_hdr)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["checked_out_at"] and (j["e_h"], j["e_m"]) == (10, 30)  # 끝을 퇴실 분으로
    again = client.post(url, headers=student_hdr)
    assert again.status_code == 409 and again.json()["detail"] == "이미 퇴실했습니다"
    with live() as s:
        # FakeTopo 의 E-301 은 노드 유닛 2 — 유닛마다 한 건 (취소 테스트와 같다)
        assert [o.type for o in s.scalars(select(Outbox))] == ["RESV_DEL", "RESV_DEL"]
        assert s.get(Reservation, a).pushed_at is None
    rooms = client.get("/api/student/rooms", headers=student_hdr).json()
    assert [x["layout"] for x in rooms if x["room_id"] == rid] == [4]  # 바로 빈 강의실
    week = client.get(f"/api/student/rooms/{rid}/week", headers=student_hdr).json()
    today = next(d for d in week["free"] if d["date"] == "2026-09-23")
    # 남은 시간이 예약 가능 — 원래 12:00 까지 막혀 있던 구간이 열린다. 신청은 지금 뒤 5분 격자부터(10:35)
    assert today["spans"] == [{"from": "10:35", "to": "21:00"}]


def test_checkout_rejects(client, live, app, school, student_hdr, monkeypatch):
    _fix_clock(monkeypatch)
    _, ids = _building(app, 1, "E", rooms=((301, 1),))
    rid = ids[301]

    def post(i):
        return client.post(f"/api/student/me/reservations/{i}/checkout", headers=student_hdr)

    _resv(app, rid, dt.date(2026, 9, 23), 10, 0, 11, 0, id_=1, requested_by="s1@mju.ac.kr")
    assert post(1).json()["detail"] == "체크인한 예약만 퇴실할 수 있습니다"
    _checked_in(app, rid, 2, 10, 35, 11, 30)  # 10:35 시작, 지금 10:30(일찍 체크인)
    assert post(2).json()["detail"] == "시작 전에는 취소를 쓰세요"
    _checked_in(app, rid, 3, 9, 0, 10, 30)  # 10:30 끝 — 지금이 끝
    assert post(3).json()["detail"] == "이미 끝난 예약입니다"
    _resv(
        app,
        rid,
        dt.date(2026, 9, 23),
        12,
        0,
        13,
        0,
        id_=4,
        status="requested",
        requested_by="s1@mju.ac.kr",
    )
    r = post(4)
    assert r.status_code == 409 and "requested" in r.json()["detail"]
    assert {post(i).status_code for i in (1, 2, 3)} == {409}
    with live() as s:
        assert list(s.scalars(select(Outbox))) == []  # 거절은 노드에 아무것도 보내지 않는다


def test_checkout_same_minute_and_unpushed(client, live, app, school, student_hdr, monkeypatch):
    # 10:30:40 — 시작 분 안의 퇴실
    monkeypatch.setattr(clock, "now_utc", lambda: dt.datetime(2026, 9, 23, 1, 30, 40))  # noqa: DTZ001
    _, ids = _building(app, 1, "E", rooms=((301, 1),))
    a = _checked_in(app, ids[301], 1, 10, 30, 11, 0, pushed=False)  # 노드에 안 간 예약
    r = client.post(f"/api/student/me/reservations/{a}/checkout", headers=student_hdr)
    assert r.status_code == 200, r.text
    # 끝 = 퇴실 분(10:30) — 시작과 같아 길이 0. 시작+1분으로 두면 그 1분 동안 '사용중'으로 남았다(실측)
    assert (r.json()["e_h"], r.json()["e_m"]) == (10, 30)
    with live() as s:
        assert list(s.scalars(select(Outbox))) == []  # 보낸 적 없으니 RESV_DEL 도 없다
    rooms = client.get("/api/student/rooms", headers=student_hdr).json()
    assert [x["layout"] for x in rooms if x["room_id"] == ids[301]] == [4]  # 바로 빈 강의실
    # 길이 0 은 새 신청을 막지 않는다 — 신청은 늘 지금 뒤에 시작한다
    body = {"date": "2026-09-23", "s_h": 10, "s_m": 35, "e_h": 11, "e_m": 0, "subject": "다음"}
    r2 = client.post(f"/api/student/rooms/{ids[301]}/reservations", json=body, headers=student_hdr)
    assert r2.status_code == 201, r2.text

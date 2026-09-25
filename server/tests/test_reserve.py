import datetime as dt
import json

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app import schemas as S
from app.auth.models import User
from app.domain import clock, reserve
from app.domain.models import Building, ExamPeriod, Reservation, Room, Slot
from app.lora_service.models import Outbox

UTC_NOW = dt.datetime(2026, 9, 23, 1, 30)  # noqa: DTZ001 — KST 9/23(수) 10:30


def _fix_clock(monkeypatch):
    monkeypatch.setattr(clock, "now_utc", lambda: UTC_NOW)


def _building(app, school_id, bld, rooms=((101, 1),)):
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


def _body(date="2026-09-24", s_h=13, s_m=0, e_h=14, e_m=0, subject="스터디"):
    return S.StudentResvIn(
        date=dt.date.fromisoformat(date), s_h=s_h, s_m=s_m, e_h=e_h, e_m=e_m, subject=subject
    )


def _check(app, rid, body, email="s1@mju.ac.kr"):
    with app.state.Session() as s:
        user, room = s.get(User, email), s.get(Room, rid)
        try:
            reserve.validate_request(s, user, room, body, clock.local_now())
            return 200
        except HTTPException as e:
            return e.status_code


S1 = {"requested_by": "s1@mju.ac.kr"}
S2 = {"requested_by": "s2@mju.ac.kr"}


def test_free_spans_splits_at_zero_length_blocker_like_overlaps_blocks_it(app, students):
    _, ids = _building(app, 1, "E")
    rid = ids[101]
    _slot(app, rid, dt.date(2026, 9, 23).isoweekday(), 10, 0, 10, 0)  # 0분짜리(관리자 입력 오류)
    with app.state.Session() as s:
        spans = reserve.free_spans(s, rid, dt.date(2026, 9, 23), reserve.OPEN_MIN)
        assert spans == [(540, 600), (600, 1260)]  # 10:00 에서 갈라진다 — 이어붙은 하나가 아니다
        assert reserve.overlaps(s, rid, dt.date(2026, 9, 23), 595, 605) is True  # 09:55~10:05


def test_constraints(app, students, monkeypatch):
    _fix_clock(monkeypatch)  # KST 9/23 10:30
    _, ids = _building(app, 1, "E")
    rid = ids[101]
    assert _check(app, rid, _body()) == 200
    assert _check(app, rid, _body(date="2026-09-22")) == 400  # 과거 날짜
    assert _check(app, rid, _body(date="2026-10-01")) == 400  # +8
    assert _check(app, rid, _body(date="2026-09-30")) == 200  # +7
    assert _check(app, rid, _body(date="2026-09-23", s_h=10, s_m=0, e_h=11)) == 400  # 시작 지남
    assert _check(app, rid, _body(date="2026-09-23", s_h=10, s_m=35, e_h=11)) == 200
    assert _check(app, rid, _body(s_h=13, s_m=0, e_h=13, e_m=10)) == 400  # 10 분
    assert _check(app, rid, _body(s_h=13, s_m=0, e_h=15, e_m=30)) == 400  # 150 분
    _slot(app, rid, 4, 14, 0, 15, 0)  # 목 14~15 정규
    assert _check(app, rid, _body(s_h=13, s_m=30, e_h=14, e_m=30)) == 409  # 슬롯 겹침
    _exam(app, rid, 1, dt.date(2026, 9, 24), dt.date(2026, 9, 24))
    assert _check(app, rid, _body(s_h=15, s_m=0, e_h=16, e_m=0)) == 200  # 시험기간이라도 슬롯 밖 OK
    _resv(app, rid, dt.date(2026, 9, 24), 16, 0, 17, 0, id_=1, status="requested", **S2)
    assert _check(app, rid, _body(s_h=16, s_m=30, e_h=17, e_m=30)) == 409  # requested 도 겹침
    for i, d in enumerate(("2026-09-25", "2026-09-26", "2026-09-27"), start=2):
        st = "approved" if i == 2 else "requested"
        _resv(app, rid, dt.date.fromisoformat(d), 9, 0, 10, 0, id_=i, status=st, **S1)
    assert _check(app, rid, _body(date="2026-09-28")) == 400  # 4 건째
    assert _check(app, rid, _body(date="2026-09-28"), email="s2@mju.ac.kr") == 200


def test_student_transitions(app, students, monkeypatch):
    _fix_clock(monkeypatch)  # KST 9/23 10:30
    _, ids = _building(app, 1, "E")
    rid = ids[101]
    d23, d24 = dt.date(2026, 9, 23), dt.date(2026, 9, 24)
    a = _resv(app, rid, d24, 13, 0, 14, 0, id_=1, status="requested", requested_at=UTC_NOW, **S1)
    b = _resv(app, rid, d23, 10, 25, 11, 0, id_=2, **S1)  # approved, 5분 전 시작
    with app.state.Session() as s, s.begin():
        reserve.withdraw(s, s.get(Reservation, a))  # 신청 철회 = 행 삭제 (id 반환)
    with app.state.Session() as s, s.begin():
        assert s.get(Reservation, a) is None
        r2 = s.get(Reservation, b)
        with pytest.raises(HTTPException) as e:
            reserve.cancel(s, r2, by_admin=False, now_local=clock.local_now())
        assert e.value.status_code == 409  # 시작된 예약은 학생이 못 취소
        reserve.checkin(s, r2, clock.local_now())  # 시작 +5분 → 창 안
        assert r2.checked_in_at is not None
        with pytest.raises(HTTPException):
            reserve.checkin(s, r2, clock.local_now())  # 재체크인
    c = _resv(app, rid, d23, 10, 14, 11, 0, id_=3, **S1)
    with app.state.Session() as s, s.begin(), pytest.raises(HTTPException):
        reserve.checkin(s, s.get(Reservation, c), clock.local_now())  # 10:14 시작 +16분 → 창 밖


def test_approve_reject_cancel_enqueue_in_same_session(db, hub, app, students, monkeypatch):
    """approve·cancel 은 호출자 세션으로 RESV_SET/DEL 을 쓴다 — 커밋 전엔 notify 없음."""
    _fix_clock(monkeypatch)
    _, ids = _building(app, 1, "E", rooms=((301, 2),))  # FakeTopo("E", 301) = units 2, modem m1
    rid = ids[301]
    d23, d24 = dt.date(2026, 9, 23), dt.date(2026, 9, 24)
    a = _resv(app, rid, d24, 13, 0, 14, 0, id_=1, status="requested", **S1)
    far = _resv(app, rid, dt.date(2026, 10, 15), 13, 0, 14, 0, id_=2, status="requested", **S1)
    started = _resv(app, rid, d23, 10, 0, 11, 0, id_=4, status="requested", **S2)
    now, adm = clock.local_now, "admin@mju.ac.kr"
    with app.state.Session() as s, s.begin():
        assert len(reserve.approve(s, s.get(Reservation, a), adm, now())) == 2
        assert s.get(Reservation, a).status == "approved" and hub.notified == []
        assert s.get(Reservation, a).pushed_at is not None  # 보냈다
        assert reserve.approve(s, s.get(Reservation, far), adm, now()) == []  # 창 밖 → 승격 대기
        assert s.get(Reservation, far).pushed_at is None
        with pytest.raises(HTTPException) as e:
            reserve.approve(s, s.get(Reservation, started), adm, now())
        assert e.value.status_code == 409  # 이미 시작한 신청은 승인 불가
        # 테스트 건물엔 modem 없음
        assert reserve.addr(s, s.get(Reservation, a)) == ("E", 301, None)
    _resv(app, rid, d24, 13, 30, 14, 30, id_=3, status="requested", **S2)
    with app.state.Session() as s, s.begin():
        with pytest.raises(HTTPException) as e:
            reserve.approve(s, s.get(Reservation, 3), adm, now())
        assert e.value.status_code == 409  # 겹침 재검사
        r = s.get(Reservation, 3)
        reserve.reject(s, r, adm, "겹침", now())
        assert r.status == "rejected" and r.reject_reason == "겹침"
        assert len(reserve.cancel(s, s.get(Reservation, a), by_admin=True, now_local=now())) == 2
        # 안 보낸 것 → DEL 없음
        assert reserve.cancel(s, s.get(Reservation, far), by_admin=True, now_local=now()) == []
        assert s.get(Reservation, a).pushed_at is None
    with db() as s:
        types = [o.type for o in s.scalars(select(Outbox).order_by(Outbox.id))]
        assert types == ["RESV_SET"] * 2 + ["RESV_DEL"] * 2


def test_room_capacity_and_public_subject(db, hub, app, students, monkeypatch):
    """방의 창 안 예약이 노드 용량에 차면 신청·승인 409, 노드엔 학생 과목 대신 고정 문구."""
    _fix_clock(monkeypatch)
    monkeypatch.setattr(reserve, "NODE_RESV_MAX", 2)
    _, ids = _building(app, 1, "E", rooms=((301, 2),))
    rid = ids[301]
    a = _resv(
        app, rid, dt.date(2026, 9, 24), 9, 0, 10, 0,
        id_=1, status="requested", subject="면접 준비 홍길동", **S1,
    )  # fmt: skip
    _resv(app, rid, dt.date(2026, 9, 25), 9, 0, 10, 0, id_=2, status="approved")
    assert _check(app, rid, _body(date="2026-09-26")) == 409  # 2 개로 가득
    with app.state.Session() as s, s.begin():  # 자기 자신은 빼고 셈
        reserve.approve(s, s.get(Reservation, a), "admin@mju.ac.kr", clock.local_now())
    with db() as s:
        o = s.scalars(select(Outbox).where(Outbox.type == "RESV_SET")).first()
        assert json.loads(o.payload)["subject"] == "학생 예약"


def test_admin_write_tracks_pushed_at(client, live, app, school, students, monkeypatch):
    """pushed_at = 노드로 보냈는가. 창 밖으로 옮기면 RESV_DEL, 안 보낸 예약 삭제엔 RESV_DEL 없음."""
    _fix_clock(monkeypatch)  # KST 9/23 10:30
    with app.state.Session() as s, s.begin():
        b = Building(school_id=1, name="E동", bld="E")
        s.add(b)
        s.flush()
        r = Room(building_id=b.id, room=302, units=1)  # live FakeTopo: E302 units 1
        s.add(r)
        s.flush()
        rid = r.id
    body = {"date": "2026-09-24", "s_h": 9, "s_m": 0, "e_h": 10, "e_m": 0}
    body |= {"type": 6, "subject": "r", "professor": ""}
    url = f"/api/rooms/{rid}/reservations"

    def types():
        with live() as s:
            return [o.type for o in s.scalars(select(Outbox).order_by(Outbox.id))]

    i = client.post(url, json=body).json()["id"]
    with app.state.Session() as s:
        assert s.get(Reservation, i).pushed_at is not None
    client.post(url, json={**body, "id": i, "date": "2026-10-10"})  # 창 밖으로
    assert types() == ["RESV_SET", "RESV_DEL"]
    with app.state.Session() as s:
        assert s.get(Reservation, i).pushed_at is None
    client.post(url, json={**body, "id": i, "date": "2026-10-11"})  # 창 밖 → 창 밖
    assert client.delete(f"{url}/{i}").json()["outbox_ids"] == []  # 보낸 적 없음
    assert client.delete(f"{url}/999").status_code == 200  # 멱등
    assert types() == ["RESV_SET", "RESV_DEL"]


@pytest.mark.parametrize(
    ("old", "new", "want"),
    [
        # 유령: 9/23 10:00~11:00(진행 중) → 10/10 07:00~08:00. 옛 끝 11:00 > 10:30 → DEL 필요
        (("2026-09-23", 10, 0, 11, 0), (7, 0, 8, 0), ["RESV_DEL"]),
        # 이미 끝남: 9/23 09:00~09:30 → 10/10 20:00~21:00. 옛 끝 09:30 ≤ 10:30 → DEL 불필요
        (("2026-09-23", 9, 0, 9, 30), (20, 0, 21, 0), []),
        # 어제(d < today): 9/22 → 10/10 20:00~21:00 → DEL 불필요
        (("2026-09-22", 9, 0, 10, 0), (20, 0, 21, 0), []),
    ],
    ids=["ghost", "already_ended", "yesterday"],
)
def test_move_out_of_window_uses_old_end(
    client, live, app, school, students, monkeypatch, old, new, want
):
    """창 밖으로 옮길 때 '끝났나' 는 노드가 가진 옛 날짜·옛 끝 시각으로 판단한다 (리뷰 fix 1)."""
    _fix_clock(monkeypatch)  # KST 9/23 10:30
    _, ids = _building(app, 1, "E", rooms=((302, 1),))  # live FakeTopo: E302 units 1
    rid = ids[302]
    d, s_h, s_m, e_h, e_m = old
    _resv(app, rid, dt.date.fromisoformat(d), s_h, s_m, e_h, e_m, id_=1)
    with app.state.Session() as s, s.begin():
        s.get(Reservation, 1).pushed_at = UTC_NOW  # 노드로 보낸 적 있음
    n_h, n_m, ne_h, ne_m = new
    body = {"id": 1, "date": "2026-10-10", "s_h": n_h, "s_m": n_m, "e_h": ne_h, "e_m": ne_m}
    body |= {"type": 6, "subject": "r", "professor": ""}
    assert client.post(f"/api/rooms/{rid}/reservations", json=body).status_code == 200
    with live() as s:
        assert [o.type for o in s.scalars(select(Outbox).order_by(Outbox.id))] == want
        assert s.get(Reservation, 1).pushed_at is None

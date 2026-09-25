import datetime as dt
import json

from sqlalchemy import select

from app.auth.models import EmailToken
from app.domain import clock, daily
from app.domain.models import Building, JobRun, Reservation, Room
from app.lora_service.models import Outbox

UTC_NOW = dt.datetime(2026, 9, 23, 1, 30)  # noqa: DTZ001 — KST 9/23(수) 10:30


def _fix_clock(monkeypatch, now=UTC_NOW):
    monkeypatch.setattr(clock, "now_utc", lambda: now)


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
    status="approved",
    requested_by=None,
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
                type=6,
                subject="예약",
                professor="",
                status=status,
                requested_by=requested_by,
                pushed_at=pushed_at,
            )
        )
    return id_


def _outbox(app, bld, room, type_, state, finished_at, payload="{}", unit=1, last_error=None):
    with app.state.Session() as s, s.begin():
        o = Outbox(
            bld=bld,
            room=room,
            unit=unit,
            type=type_,
            payload=payload,
            state=state,
            created_at=UTC_NOW,
            finished_at=finished_at,
            modem_id="m1",
            last_error=last_error,
        )
        s.add(o)
        s.flush()
        return o.id


def _run(app) -> dict:
    """run_daily 는 이번 실행의 JobRun id 를 돌려준다 — 결과 dict 는 그 행의 result."""
    with app.state.Session() as s:
        return json.loads(s.get(JobRun, daily.run_daily(app.state.Session)).result)


def test_run_daily_five_steps(db, hub, app, school, students, monkeypatch):
    _fix_clock(monkeypatch)  # KST 9/23 10:30 → 오늘+7 = 9/30
    _, ids = _building(app, 1, "E", rooms=((301, 2), (302, 1)))
    r301, r302 = ids[301], ids[302]
    # 1 만료: 신청인데 시작 지남
    _resv(
        app,
        r301,
        dt.date(2026, 9, 23),
        9,
        0,
        10,
        0,
        id_=1,
        status="requested",
        requested_by="s1@mju.ac.kr",
    )
    # 2 승격: 창 안 승인 예약 중 pushed_at NULL 전부
    _resv(app, r301, dt.date(2026, 9, 30), 13, 0, 14, 0, id_=2)  # +7 → 승격
    _outbox(
        app, "E", 301, "RESV_SET", "acked", UTC_NOW, payload=json.dumps({"resv_id": 2})
    )  # 옛 예약 2 의 이력 — id 재사용에 속지 않는다
    _resv(app, r302, dt.date(2026, 9, 26), 15, 0, 16, 0, id_=8)  # +3, 놓친 날 따라잡음
    _resv(app, r301, dt.date(2026, 9, 24), 13, 0, 14, 0, id_=3, pushed_at=UTC_NOW)
    _resv(app, r302, dt.date(2026, 9, 30), 15, 0, 16, 0, id_=6, pushed_at=UTC_NOW)
    _resv(app, r301, dt.date(2026, 10, 5), 13, 0, 14, 0, id_=4)  # 창 밖
    # 3 재동기: 24 h 안 실패 — CMD·25 h 전·관리자 취소분은 무시
    _outbox(app, "E", 302, "SLOT_SET", "failed", UTC_NOW - dt.timedelta(hours=1))
    _outbox(
        app,
        "E",
        301,
        "FILE",
        "failed",
        UTC_NOW - dt.timedelta(hours=2),
        payload=json.dumps({"kind": 2, "records": []}),
        unit=2,
    )
    _outbox(app, "E", 302, "CMD", "failed", UTC_NOW - dt.timedelta(hours=1))
    _outbox(app, "E", 301, "EXAM_SET", "failed", UTC_NOW - dt.timedelta(hours=25))
    _outbox(
        app, "E", 301, "SLOT_SET", "failed", UTC_NOW - dt.timedelta(hours=1), last_error="cancelled"
    )
    # 4 정리: 91 일 전 예약, 8 일 전 거절 신청, 91 일 전 job_run, 8 일 지난 토큰
    _resv(app, r302, dt.date(2026, 6, 20), 9, 0, 10, 0, id_=5)
    _resv(
        app,
        r302,
        dt.date(2026, 9, 15),
        9,
        0,
        10,
        0,
        id_=7,
        status="rejected",
        requested_by="s2@mju.ac.kr",
    )
    with app.state.Session() as s, s.begin():
        s.add(JobRun(name="daily", ran_at=UTC_NOW - dt.timedelta(days=91), result="{}"))
        s.add(
            EmailToken(
                token_hash="x",
                email="s1@mju.ac.kr",
                purpose="verify",
                created_at=UTC_NOW - dt.timedelta(days=8),
                expires_at=UTC_NOW - dt.timedelta(days=8),
            )
        )
        s.add(
            EmailToken(
                token_hash="y",
                email="s1@mju.ac.kr",
                purpose="verify",
                created_at=UTC_NOW - dt.timedelta(days=6),
                expires_at=UTC_NOW - dt.timedelta(days=6),
            )
        )
    res = _run(app)
    assert res["errors"] == []
    assert res["expired"] == 1 and res["promoted"] == 2
    assert res["resynced"] == [["E", 301, 2, ["resv"]], ["E", 302, 1, ["schedule"]]]
    assert res["pruned"] == {"reservations": 2, "job_runs": 1, "email_tokens": 1}
    with app.state.Session() as s:
        assert s.get(Reservation, 1).status == "expired"
        assert s.get(Reservation, 5) is None and s.get(Reservation, 7) is None
        rows = s.scalars(select(Outbox).where(Outbox.state == "queued")).all()
        assert sorted((o.room, o.unit, o.type) for o in rows) == [
            (301, 1, "RESV_SET"),
            (301, 2, "FILE"),
            (301, 2, "RESV_SET"),
            (302, 1, "FILE"),
            (302, 1, "RESV_SET"),
        ]
        assert s.get(Reservation, 2).pushed_at is not None
        assert s.get(Reservation, 4).pushed_at is None
        assert s.scalar(select(EmailToken.token_hash).where(EmailToken.token_hash == "y")) == "y"
        runs = s.scalars(select(JobRun).order_by(JobRun.id)).all()
        assert len(runs) == 1 and json.loads(runs[0].result)["promoted"] == 2
    assert _run(app)["promoted"] == 0  # 이미 보낸 건 안 보낸다


def test_promote_skips_ended_and_full_room(db, hub, app, school, monkeypatch):
    _fix_clock(monkeypatch)  # KST 10:30
    _, ids = _building(app, 1, "E", rooms=((301, 2), (302, 1)))
    _resv(app, ids[301], dt.date(2026, 9, 23), 9, 0, 10, 0, id_=1)  # 오늘 이미 끝남 → 조용히 건너뜀
    for i in range(24):  # 302 는 창 안 보낸 예약이 노드 용량만큼
        _resv(app, ids[302], dt.date(2026, 9, 24), 0, 0, 0, 5, id_=100 + i, pushed_at=UTC_NOW)
    _resv(app, ids[302], dt.date(2026, 9, 25), 13, 0, 14, 0, id_=2)
    res = _run(app)
    assert res["promoted"] == 0 and len(res["errors"]) == 1 and "resv 2" in res["errors"][0]
    with app.state.Session() as s:
        assert s.get(Reservation, 1).pushed_at is None and s.get(Reservation, 2).pushed_at is None


def test_promote_one_failure_does_not_stop_others(db, hub, app, school, monkeypatch):
    """예약마다 자기 트랜잭션 — 한 건이 실패해도 나머지는 보내고, 실패분은 다음 날 다시 시도."""
    _fix_clock(monkeypatch)
    _, ids = _building(app, 1, "E", rooms=((301, 2), (302, 1)))
    _resv(app, ids[301], dt.date(2026, 9, 25), 13, 0, 14, 0, id_=1)
    _resv(app, ids[302], dt.date(2026, 9, 25), 13, 0, 14, 0, id_=2)
    real = daily.api.enqueue_resv_set

    def flaky(bld, room, *a, **kw):
        if room == 301:
            raise LookupError("room gone")
        return real(bld, room, *a, **kw)

    monkeypatch.setattr(daily.api, "enqueue_resv_set", flaky)
    res = _run(app)
    assert res["promoted"] == 1 and any("resv 1" in e for e in res["errors"])
    with app.state.Session() as s:
        assert s.get(Reservation, 1).pushed_at is None
        assert s.get(Reservation, 2).pushed_at is not None


def test_resync_one_room_failure_does_not_stop_others(db, hub, app, school, monkeypatch):
    _fix_clock(monkeypatch)
    _building(app, 1, "E", rooms=((301, 2), (302, 1)))
    _outbox(app, "E", 301, "SLOT_SET", "failed", UTC_NOW - dt.timedelta(hours=1))
    _outbox(app, "E", 302, "SLOT_SET", "failed", UTC_NOW - dt.timedelta(hours=1))
    real = daily.api.enqueue_full_sync

    def flaky(bld, room, kinds, unit=0):
        if room == 301:
            raise LookupError("room gone")
        return real(bld, room, kinds, unit=unit)

    monkeypatch.setattr(daily.api, "enqueue_full_sync", flaky)
    res = _run(app)
    assert res["resynced"] == [["E", 302, 1, ["schedule"]]]
    assert any("E301" in e for e in res["errors"])


def test_step_failure_continues(db, hub, app, school, monkeypatch):
    _fix_clock(monkeypatch)

    def boom(Session, now_local, errors):
        raise RuntimeError("boom")

    monkeypatch.setattr(daily, "_promote", boom)
    res = _run(app)
    assert res["promoted"] == 0 and res["errors"] == ["promoted: RuntimeError"] and "pruned" in res


def test_already_ran_today_and_loop_tick(db, hub, app, school, monkeypatch):
    with app.state.Session() as s:
        assert daily.already_ran_today(s, dt.datetime(2026, 9, 23, 10, 0)) is False  # noqa: DTZ001
    _fix_clock(monkeypatch, dt.datetime(2026, 9, 22, 18, 59))  # noqa: DTZ001 — KST 03:59 → 안 돎
    assert daily.tick(app.state.Session) is False
    _fix_clock(monkeypatch, dt.datetime(2026, 9, 22, 19, 0))  # noqa: DTZ001 — KST 04:00 → 돎
    assert daily.tick(app.state.Session) is True
    assert daily.tick(app.state.Session) is False  # 같은 날 두 번 안 돎
    _fix_clock(monkeypatch, dt.datetime(2026, 9, 23, 5, 0))  # noqa: DTZ001 — KST 14:00
    assert daily.tick(app.state.Session) is False
    # 04:00 이전 수동 실행은 그날 자동 실행을 막지 않는다
    _fix_clock(monkeypatch, dt.datetime(2026, 9, 23, 17, 0))  # noqa: DTZ001 — KST 9/24 02:00
    daily.run_daily(app.state.Session)
    _fix_clock(monkeypatch, dt.datetime(2026, 9, 23, 19, 0))  # noqa: DTZ001 — KST 9/24 04:00
    assert daily.tick(app.state.Session) is True


def test_jobs_endpoints(client, live, app, school, monkeypatch):
    _fix_clock(monkeypatch)
    r = client.post("/api/admin/jobs/daily")
    body = r.json()
    assert r.status_code == 200 and body["name"] == "daily" and body["result"]["errors"] == []
    r = client.post("/api/admin/jobs/daily")  # 수동은 항상 돎
    assert r.status_code == 200
    assert len(client.get("/api/admin/jobs?name=daily").json()) == 2
    assert client.get("/api/admin/jobs?name=daily&limit=1").json()[0]["id"] == r.json()["id"]


def test_expire_does_not_overwrite_concurrent_approve(db, hub, app, school, students, monkeypatch):
    """만료 대상 선택 뒤·UPDATE 전에 관리자가 승인하면 승인이 이긴다 — expired 로 덮이면 RESV_SET 이
    이미 나간 행을 아무도 DEL 하지 않는 유령 예약이 된다 (final review #1)."""
    _fix_clock(monkeypatch)
    _, ids = _building(app, 1, "E")
    _resv(
        app, ids[101], dt.date(2026, 9, 23), 9, 0, 10, 0, id_=1, status="requested",
        requested_by="s1@mju.ac.kr",
    )  # fmt: skip
    real = daily.reserve.start_local

    def approve_meanwhile(r):
        with app.state.Session() as s2, s2.begin():
            s2.get(Reservation, 1).status = "approved"
        return real(r)

    monkeypatch.setattr(daily.reserve, "start_local", approve_meanwhile)
    res = _run(app)
    assert res["expired"] == 0
    with app.state.Session() as s:
        assert s.get(Reservation, 1).status == "approved"


def test_resync_not_repeated_within_24h(db, hub, app, school, monkeypatch):
    """직전 실행이 이미 재동기한 실패는 24 h 안의 다음 실행(수동 포함)이 다시 FILE 로 보내지 않는다 (#3)."""
    _fix_clock(monkeypatch)
    _building(app, 1, "E", rooms=((302, 1),))
    _outbox(app, "E", 302, "SLOT_SET", "failed", UTC_NOW - dt.timedelta(hours=1))
    assert _run(app)["resynced"] == [["E", 302, 1, ["schedule"]]]
    later = UTC_NOW + dt.timedelta(hours=1)
    _fix_clock(monkeypatch, later)
    assert _run(app)["resynced"] == []
    _outbox(app, "E", 302, "EXAM_SET", "failed", later + dt.timedelta(minutes=1))  # 그 뒤 새 실패
    _fix_clock(monkeypatch, later + dt.timedelta(hours=1))
    assert _run(app)["resynced"] == [["E", 302, 1, ["exam"]]]


def test_run_daily_skip_if_ran(db, hub, app, school, monkeypatch):
    _fix_clock(monkeypatch, dt.datetime(2026, 9, 22, 19, 0))  # noqa: DTZ001 — KST 04:00
    assert daily.run_daily(app.state.Session, skip_if_ran=True) is not None
    assert daily.run_daily(app.state.Session, skip_if_ran=True) is None


def test_manual_daily_returns_its_own_jobrun(client, live, app, school, monkeypatch):
    _fix_clock(monkeypatch)
    real = daily._run_daily

    def then_another(Session, now_utc):
        jid = real(Session, now_utc)
        with Session() as s, s.begin():  # 커밋 직후 다른 실행 기록이 끼어든다
            s.add(JobRun(name="daily", ran_at=UTC_NOW, result="{}"))
        return jid

    monkeypatch.setattr(daily, "_run_daily", then_another)
    body = client.post("/api/admin/jobs/daily").json()
    assert body["result"] != {} and body["id"] == 1


def test_errors_keep_only_exception_class_name(db, hub, app, school, monkeypatch):
    """#49 리뷰: /api/admin/jobs 로 나가는 errors 에 str(e) 를 넣으면 IntegrityError 의 SQL 파라미터가
    섞인다 — 예외 클래스명만 남긴다 (자세한 건 서버 로그)."""
    _fix_clock(monkeypatch)
    _, ids = _building(app, 1, "E", rooms=((301, 2),))
    _resv(app, ids[301], dt.date(2026, 9, 25), 13, 0, 14, 0, id_=1)
    _outbox(app, "E", 301, "SLOT_SET", "failed", UTC_NOW - dt.timedelta(hours=1))

    def leak(*a, **kw):
        raise LookupError("secret-param")

    monkeypatch.setattr(daily.api, "enqueue_resv_set", leak)
    monkeypatch.setattr(daily.api, "enqueue_full_sync", leak)
    monkeypatch.setattr(daily, "_prune", leak)  # 단계 실패도
    res = _run(app)
    assert "promoted: resv 1: LookupError" in res["errors"]
    assert "resynced: E301/1: LookupError" in res["errors"]
    assert "pruned: LookupError" in res["errors"]
    assert not any("secret-param" in e for e in res["errors"]), res["errors"]

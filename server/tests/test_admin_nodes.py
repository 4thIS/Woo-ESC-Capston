import datetime as dt

from app.domain import admin
from app.domain.models import Building, Room
from app.lora_service.models import Modem, Outbox, TerminalStatus

NOW = dt.datetime(2026, 9, 25)  # noqa: DTZ001 — 앱 전역이 naive UTC (app.db.utcnow)


def _building(app, school_id, bld, rooms=((101, 1), (102, 1)), modem_id=None):
    with app.state.Session() as s, s.begin():
        if modem_id is not None:
            s.add(Modem(modem_id=modem_id, token_hash="x", school_id=school_id))
            s.flush()  # buildings.modem_id FK — 부모 먼저
        b = Building(school_id=school_id, name=f"{bld}동", bld=bld, modem_id=modem_id)
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


def _status(
    app,
    bld,
    room,
    unit,
    *,
    modem_id=None,
    last_seen_at=None,
    low_batt=False,
    clock_stale=False,
    sync_state="unknown",
    batt_mv=None,
):
    with app.state.Session() as s, s.begin():
        s.add(
            TerminalStatus(
                bld=bld,
                room=room,
                unit=unit,
                modem_id=modem_id,
                last_seen_at=last_seen_at,
                low_batt=low_batt,
                clock_stale=clock_stale,
                sync_state=sync_state,
                batt_mv=batt_mv,
            )
        )


def _outbox(
    app, bld, room, *, unit=1, state="failed", last_error=None, finished_at=None, modem_id=None
):
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
            last_error=last_error,
            created_at=NOW,
            finished_at=finished_at,
        )
        s.add(o)
        s.flush()
        oid = o.id
    return oid


def _nodes(app, school_id=1, **kw):
    with app.state.Session() as s:
        return admin.expected_nodes(s, school_id, now=NOW, **kw)


def test_expected_nodes_left_join_and_warnings(app, school):
    bid, ids = _building(app, 1, "E", rooms=((101, 1), (102, 2)), modem_id="m1")
    _building(app, 2, "F", rooms=((101, 1),))  # 타 학교
    fresh = NOW - dt.timedelta(hours=47, minutes=59)
    stale = NOW - dt.timedelta(hours=48, seconds=1)
    _status(app, "E", 101, 1, last_seen_at=fresh, low_batt=True, sync_state="synced", batt_mv=3400)
    _status(app, "E", 102, 1, last_seen_at=stale, sync_state="resync", clock_stale=True)
    # E102 unit 2 는 보고 없음
    _status(app, "F", 101, 1, last_seen_at=fresh)
    rows = _nodes(app)
    assert [(r["bld"], r["room"], r["unit"]) for r in rows] == [
        ("E", 101, 1),
        ("E", 102, 1),
        ("E", 102, 2),
    ]
    a, b, c = rows
    assert a["room_id"] == ids[101] and a["building"] == "E동" and a["building_id"] == bid
    assert a["warnings"] == ["low_batt"] and a["batt_mv"] == 3400 and a["sync_state"] == "synced"
    assert b["warnings"] == ["unseen", "resync", "clock_stale"]
    assert c["warnings"] == ["unseen"] and c["sync_state"] == "unknown" and c["batt_mv"] is None
    assert c["low_batt"] is False and c["clock_stale"] is False
    assert _nodes(app, building_id=bid) == rows
    assert _nodes(app, school_id=2)[0]["bld"] == "F"


def test_expected_nodes_excludes_other_school_modem_on_bld_reuse(app, school):
    """건물 삭제·재생성으로 bld 글자가 재사용되면, 옛 학교(모뎀이 다른 학교 소속) status 행이
    같은 (bld, room, unit) 을 우연히 물고 있어도 쓰이면 안 된다 (/api/lora/status 와 같은 규칙)."""
    _building(app, 1, "E", modem_id="m1")
    with app.state.Session() as s, s.begin():
        s.add(Modem(modem_id="m2", token_hash="x", school_id=2))
    _status(app, "E", 101, 1, modem_id="m2", last_seen_at=NOW)  # 학교 2 소유 모뎀의 옛 행 → 안 쓰임
    _status(app, "E", 102, 1, modem_id="m1", last_seen_at=NOW)  # 학교 1 소유 모뎀 → 쓰임
    rows = _nodes(app)
    a = next(r for r in rows if r["room"] == 101)
    b = next(r for r in rows if r["room"] == 102)
    assert (
        a["warnings"] == ["unseen"] and a["sync_state"] == "unknown" and a["last_seen_at"] is None
    )
    assert b["warnings"] == [] and b["last_seen_at"] == NOW


def test_failed_outbox_window_join_and_limit(app, school):
    _, ids = _building(app, 1, "E")
    _building(app, 2, "F", rooms=((101, 1),))
    recent = _outbox(
        app, "E", 101, finished_at=NOW - dt.timedelta(days=6, hours=23), last_error="no_ack"
    )
    old = _outbox(app, "E", 101, finished_at=NOW - dt.timedelta(days=7, seconds=1))
    _outbox(app, "F", 101, finished_at=NOW)  # 타 학교
    _outbox(app, "E", 999, finished_at=NOW)  # 방 없음 → 제외
    _outbox(app, "E", 102, state="acked", finished_at=NOW)  # 실패 아님
    _outbox(app, "E", 102, finished_at=NOW, last_error="cancelled")  # 관리자 취소 → 제외
    newest = _outbox(app, "E", 102, finished_at=NOW)
    with app.state.Session() as s:
        rows = admin.failed_outbox(s, 1, days=7, now=NOW)
        assert [r["id"] for r in rows] == [newest, recent] and old not in [r["id"] for r in rows]
        assert (
            rows[1]["room_id"] == ids[101]
            and rows[1]["building"] == "E동"
            and rows[1]["last_error"] == "no_ack"
        )
        assert [r["id"] for r in admin.failed_outbox(s, 1, days=7, limit=1, now=NOW)] == [newest]
        assert admin.failed_outbox(s, 1, days=8, now=NOW)[-1]["id"] == old


def test_failed_outbox_excludes_other_school_modem_on_bld_reuse(app, school):
    """건물 삭제·재생성으로 bld 글자가 재사용되면, 옛 학교(모뎀이 다른 학교 소속) outbox 행이
    같은 (bld, room) 을 우연히 물고 있어도 실패 목록에 보이면 안 된다 (/api/lora/outbox 와 같은 규칙)."""
    _building(app, 1, "E")
    with app.state.Session() as s, s.begin():
        s.add(Modem(modem_id="m2", token_hash="x", school_id=2))
    stale = _outbox(app, "E", 101, modem_id="m2", finished_at=NOW)  # 학교 2 소유 모뎀의 옛 행
    mine = _outbox(app, "E", 101, modem_id=None, finished_at=NOW)
    with app.state.Session() as s:
        rows = admin.failed_outbox(s, 1, days=7, now=NOW)
    assert [r["id"] for r in rows] == [mine]
    assert stale not in [r["id"] for r in rows]

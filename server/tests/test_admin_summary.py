import datetime as dt

from app.auth import password
from app.auth.models import User
from app.domain import admin
from app.domain.models import Building, Room
from app.lora_service.models import Modem, Outbox, PendingDevice, TerminalStatus

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


def _seed(app):
    bid, e = _building(app, 1, "E", rooms=((101, 1), (102, 2)), modem_id="m1")
    _building(app, 1, "G", rooms=((201, 1),), modem_id="m2")
    _building(app, 2, "F", rooms=((101, 1),), modem_id="mf")
    with app.state.Session() as s, s.begin():
        s.get(Modem, "m2").connected = True
        s.get(Modem, "m1").last_seen_at = NOW - dt.timedelta(days=1)
    stale = NOW - dt.timedelta(days=3)
    _status(app, "E", 101, 1, last_seen_at=NOW, low_batt=True, batt_mv=3400)
    _status(app, "E", 102, 1, last_seen_at=stale, low_batt=True, batt_mv=3300, sync_state="resync")
    # E102/2, G201 보고 없음 → unseen 3 (E102/1 포함)
    for i in range(6):
        _outbox(app, "E", 101, finished_at=NOW - dt.timedelta(hours=i))
    with app.state.Session() as s, s.begin():
        s.add_all(
            [
                PendingDevice(
                    mac="aabbccddeeff",
                    modem_id="m1",
                    first_seen_at=NOW - dt.timedelta(hours=2),
                    last_seen_at=NOW,
                ),
                PendingDevice(
                    mac="112233445566", modem_id="mf", first_seen_at=NOW, last_seen_at=NOW
                ),
                User(
                    email="p1@mju.ac.kr",
                    school_id=1,
                    role="student",
                    status="pending_approval",
                    name="p1",
                    student_no="1",
                    pw_hash=password.hash("password1"),
                ),
                User(
                    email="p2@mju.ac.kr",
                    school_id=1,
                    role="student",
                    status="pending_approval",
                    name="p2",
                    student_no="2",
                    pw_hash=password.hash("password1"),
                ),
                User(
                    email="po@other.ac.kr",
                    school_id=2,
                    role="student",
                    status="pending_approval",
                    name="po",
                    student_no="3",
                    pw_hash=password.hash("password1"),
                ),
            ]
        )
    return bid, e


def test_summary_counts_previews_and_totals(client, app, school, monkeypatch):
    monkeypatch.setattr(admin, "utcnow", lambda: NOW)
    _seed(app)
    r = client.get("/api/admin/summary?preview=2")
    assert r.status_code == 200
    j = r.json()
    assert j["totals"] == {"buildings": 2, "rooms": 3, "nodes": 4, "modems": 2}
    w = j["warnings"]
    assert {
        k: w[k]["count"]
        for k in (
            "modem_offline",
            "unseen",
            "low_batt",
            "resync",
            "clock_stale",
            "failed",
            "pending_devices",
            "pending_approval",
        )
    } == {  # S10 이 pending_reservations 를 더하므로 전체 키가 아니라 이 8개만 본다
        "modem_offline": 1,
        "unseen": 3,
        "low_batt": 2,
        "resync": 1,
        "clock_stale": 0,
        "failed": 6,
        "pending_devices": 1,
        "pending_approval": 2,
    }
    assert w["modem_offline"]["items"] == [
        {
            "modem_id": "m1",
            "last_seen_at": (NOW - dt.timedelta(days=1)).isoformat(),
            "buildings": ["E동"],
        }
    ]
    assert [(x["room"], x["unit"]) for x in w["unseen"]["items"]] == [
        (102, 2),
        (201, 1),
    ]  # None(보고 없음) 먼저, preview=2
    assert [x["room"] for x in w["low_batt"]["items"]] == [102, 101]  # 오래된 순
    assert (
        len(w["failed"]["items"]) == 2 and w["failed"]["items"][0]["finished_at"] == NOW.isoformat()
    )
    assert w["failed"]["items"][0]["building"] == "E동"
    assert w["pending_devices"]["items"][0]["mac"] == "aabbccddeeff"
    assert [x["email"] for x in w["pending_approval"]["items"]] == ["p1@mju.ac.kr", "p2@mju.ac.kr"]
    assert "pw_hash" not in r.text and j["as_of"] == NOW.isoformat()


def test_summary_defaults_limits_and_auth(client, client_raw, app, school, monkeypatch):
    monkeypatch.setattr(
        admin, "utcnow", lambda: NOW
    )  # 시드가 NOW 기준 — 실제 날짜가 지나도 7일 창이 같다
    _seed(app)
    j = client.get("/api/admin/summary").json()
    assert len(j["warnings"]["failed"]["items"]) == 5 and j["warnings"]["failed"]["count"] == 6
    assert client.get("/api/admin/summary?preview=21").status_code == 422
    assert client.get("/api/admin/summary?preview=0").status_code == 422
    assert client_raw.get("/api/admin/summary").status_code == 401
    # 학생(active) 토큰은 403 — pending 계정은 토큰을 못 받으므로 active 학생을 따로 만든다
    with app.state.Session() as s, s.begin():
        s.add(
            User(
                email="a@mju.ac.kr",
                school_id=1,
                role="student",
                status="active",
                name="a",
                student_no="9",
                pw_hash=password.hash("password1"),
            )
        )
    with app.state.Session() as s:
        from app.auth import tokens
        from app.settings import Settings

        stu = tokens.jwt_encode(Settings(), s.get(User, "a@mju.ac.kr"))
    assert (
        client.get("/api/admin/summary", headers={"Authorization": f"Bearer {stu}"}).status_code
        == 403
    )

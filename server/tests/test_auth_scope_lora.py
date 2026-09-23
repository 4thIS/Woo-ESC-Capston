import datetime as dt

from app.domain.models import Building, Room
from app.lora_service import api
from app.lora_service.models import Modem, Outbox, PendingDevice, TerminalStatus


def _seed(app):
    with app.state.Session() as s, s.begin():
        s.add_all(
            [
                Modem(modem_id="m1", token_hash="x", school_id=1),
                Modem(modem_id="m2", token_hash="x", school_id=2),
            ]
        )
        s.flush()  # 모뎀 먼저 — Building.modem_id FK (r2 🔴3)
        for sid, bld, mid in ((1, "E", "m1"), (2, "F", "m2")):
            b = Building(school_id=sid, name=bld, bld=bld, modem_id=mid)
            s.add(b)
            s.flush()
            s.add(Room(building_id=b.id, room=101, units=1))
        now = dt.datetime(2026, 9, 23)  # noqa: DTZ001 — 앱 전역이 naive UTC (app.db.utcnow)
        s.add_all(
            [
                Outbox(
                    id=1,
                    modem_id="m1",
                    bld="E",
                    room=101,
                    unit=1,
                    type="CMD",
                    payload="{}",
                    priority=5,
                    created_at=now,
                ),
                Outbox(
                    id=2,
                    modem_id="m2",
                    bld="F",
                    room=101,
                    unit=1,
                    type="CMD",
                    payload="{}",
                    priority=5,
                    created_at=now,
                ),
                TerminalStatus(bld="E", room=101, unit=1, modem_id="m1"),
                TerminalStatus(bld="F", room=101, unit=1, modem_id="m2"),
                PendingDevice(
                    mac="aabbccddeeff", modem_id="m1", first_seen_at=now, last_seen_at=now
                ),
                PendingDevice(
                    mac="112233445566", modem_id="m2", first_seen_at=now, last_seen_at=now
                ),
            ]
        )


def test_lora_endpoints_require_admin(client_raw, school):
    for path in ("/api/lora/modems", "/api/lora/outbox", "/api/lora/status", "/api/lora/pending"):
        assert client_raw.get(path).status_code == 401, path
    assert client_raw.post("/api/lora/time").status_code == 401


def test_lists_are_school_scoped(client, app, school):
    _seed(app)
    assert [m["modem_id"] for m in client.get("/api/lora/modems").json()] == ["m1"]
    assert client.get("/api/lora/modems").json()[0]["school_id"] == 1
    assert [o["id"] for o in client.get("/api/lora/outbox").json()] == [1]
    assert [x["bld"] for x in client.get("/api/lora/status").json()] == ["E"]
    assert [p["mac"] for p in client.get("/api/lora/pending").json()] == ["aabbccddeeff"]


def test_single_actions_scoped(client, app, school):
    _seed(app)
    assert client.post("/api/lora/outbox/2/cancel").status_code == 404
    assert client.post("/api/lora/outbox/1/cancel").status_code == 200
    assert client.post("/api/lora/modems/m2/token").status_code == 404
    assert client.post("/api/lora/modems/m1/token").status_code == 200
    assert (
        client.post(
            "/api/lora/pending/112233445566/provision", json={"bld": "F", "room": 101, "unit": 1}
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/lora/pending/aabbccddeeff/provision", json={"bld": "F", "room": 101, "unit": 1}
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/lora/pending/aabbccddeeff/provision", json={"bld": "E", "room": 101, "unit": 1}
        ).status_code
        == 200
    )


def test_time_broadcast_rate_limited(client, school):
    assert client.post("/api/lora/time").status_code == 200
    assert client.post("/api/lora/time").status_code == 429  # 전역 10분 1회 (S4a §3.3)


def test_register_modem_sets_school(client, app, school):
    r = client.post("/api/lora/modems", json={"modem_id": "new-1"})
    assert r.status_code == 200 and api.verify_token("new-1", r.json()["token"])
    with app.state.Session() as s:
        assert s.get(Modem, "new-1").school_id == 1

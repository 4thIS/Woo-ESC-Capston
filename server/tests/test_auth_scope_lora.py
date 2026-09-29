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


def test_outbox_limit_applied_after_school_filter(client, app, school):
    """리뷰 🟡 — limit 을 먼저 자르면 타교의 최신 행이 내 행을 밀어낸다."""
    _seed(app)
    with app.state.Session() as s, s.begin():
        now = dt.datetime(2026, 9, 23)  # noqa: DTZ001
        s.add_all(
            [
                Outbox(
                    id=i,
                    modem_id="m2",
                    bld="F",
                    room=101,
                    unit=1,
                    type="CMD",
                    payload="{}",
                    priority=5,
                    created_at=now,
                )
                for i in (3, 4, 5)
            ]
        )
    assert [o["id"] for o in client.get("/api/lora/outbox?limit=1").json()] == [1]


def test_outbox_status_hide_old_school_rows_on_bld_reuse(client, app, school):
    """⚪ bld 재사용 — B 가 F동을 지우고 A 가 같은 bld·room 을 새로 만들어도, 남은 B 소유
    옛 outbox·status 행(modem_id 가 B 소유)은 A 에게 보이면 안 된다."""
    _seed(app)
    with app.state.Session() as s, s.begin():
        now = dt.datetime(2026, 9, 23)  # noqa: DTZ001
        s.add(
            Outbox(
                id=9,
                modem_id="m2",  # 학교 2 소유 모뎀
                bld="E",  # 하지만 bld/room 은 학교 1 의 현재 방과 겹친다
                room=101,
                unit=1,
                type="CMD",
                payload="{}",
                priority=5,
                created_at=now,
            )
        )
        s.add(TerminalStatus(bld="E", room=101, unit=2, modem_id="m2"))
    assert [o["id"] for o in client.get("/api/lora/outbox").json()] == [1]
    assert [t["unit"] for t in client.get("/api/lora/status").json()] == [1]
    assert (
        client.post("/api/lora/outbox/9/cancel").status_code == 404
    )  # 안 보이는 행은 취소도 못 한다


def test_register_modem_sets_school(client, app, school):
    r = client.post("/api/lora/modems", json={"modem_id": "new-1"})
    assert r.status_code == 200 and api.verify_token("new-1", r.json()["token"])
    with app.state.Session() as s:
        assert s.get(Modem, "new-1").school_id == 1

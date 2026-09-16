import datetime as dt
import json

import pytest
from lora_proto import codec as C
from sqlalchemy import select

from app.domain.models import Building, ExamPeriod, Reservation, Room, School, Slot
from app.domain.topology import DomainTopology, record_provider
from app.lora_service import api
from app.lora_service.api import RoomInfo
from app.lora_service.models import Modem, Outbox


def _seed(Session):
    with Session() as s, s.begin():
        s.add(Modem(modem_id="mjc-eng", token_hash="x"))  # buildings.modem_id FK (app/db.py: FK ON)
        sch = School(name="명지", net_id=0x4B)
        s.add(sch)
        s.flush()
        b = Building(school_id=sch.id, name="공학관", bld="E", modem_id="mjc-eng")
        s.add(b)
        s.flush()
        r1 = Room(building_id=b.id, room=301, units=2)
        r2 = Room(building_id=b.id, room=302, units=1)
        s.add_all([r1, r2])
        s.flush()
        s.add(
            Slot(
                room_id=r1.id,
                day=1,
                s_h=9,
                s_m=0,
                e_h=10,
                e_m=50,
                type=1,
                subject="자료구조",
                professor="김",
            )
        )
        s.add(
            Reservation(
                id=7,
                room_id=r1.id,
                date=dt.date(2026, 9, 16),
                s_h=13,
                s_m=0,
                e_h=15,
                e_m=0,
                type=6,
                subject="대여",
                professor="",
            )
        )
        s.add(
            Reservation(
                id=8,
                room_id=r1.id,
                date=dt.date(2026, 10, 30),
                s_h=13,
                s_m=0,
                e_h=15,
                e_m=0,
                type=6,
                subject="먼예약",
                professor="",
            )
        )
        s.add(
            ExamPeriod(
                id=3,
                room_id=r1.id,
                date_start=dt.date(2026, 10, 19),
                date_end=dt.date(2026, 10, 23),
            )
        )
        return r1.id


def test_topology_resolves_room_nodes_net_id(app):
    _seed(app.state.Session)
    t = DomainTopology(app.state.Session)
    assert t.room("E", 301) == RoomInfo("mjc-eng", 2, 0x4B)
    assert t.room("E", 999) is None and t.room("Z", 301) is None
    assert sorted(t.nodes("mjc-eng")) == [("E", 301, 1), ("E", 301, 2), ("E", 302, 1)]
    assert t.nodes("nope") == [] and t.net_id("mjc-eng") == 0x4B and t.net_id("nope") is None


def test_room_raises_when_bld_ambiguous_across_schools(app):
    """PR #5 M-f — 같은 bld 코드 건물이 두 학교에 있으면 운영 규칙 위반으로 명시적 예외."""
    with app.state.Session() as s, s.begin():
        sch1 = School(name="A", net_id=1)
        sch2 = School(name="B", net_id=2)
        s.add_all([sch1, sch2])
        s.flush()
        b1 = Building(school_id=sch1.id, name="공학관", bld="E")
        b2 = Building(school_id=sch2.id, name="이과관", bld="E")
        s.add_all([b1, b2])
        s.flush()
        s.add_all(
            [Room(building_id=b1.id, room=301, units=1), Room(building_id=b2.id, room=301, units=1)]
        )
    t = DomainTopology(app.state.Session)
    with pytest.raises(LookupError, match="여러 학교"):
        t.room("E", 301)


def test_record_provider_mirrors_codec_and_limits_resv_to_7_days(app):
    _seed(app.state.Session)
    rp = record_provider(app.state.Session, today=lambda: dt.date(2026, 9, 14))
    sched = rp("E", 301, "schedule")
    assert sched == [C.SlotSet(0, 1, 9, 0, 10, 50, 1, "자료구조", "김")]
    resv = rp("E", 301, "resv")
    assert [r.resv_id for r in resv] == [7]  # 10/30 은 7일 밖
    assert resv[0] == C.ResvSet(0, 7, 2026, 9, 16, 13, 0, 15, 0, 6, "대여", "")
    assert rp("E", 301, "exam") == [C.ExamSet(0, 3, 2026, 10, 19, 2026, 10, 23)]
    assert rp("E", 999, "schedule") == []


def _setup(client):
    sch = client.post("/api/schools", json={"name": "명지", "net_id": 75}).json()
    b = client.post(
        "/api/buildings", json={"school_id": sch["id"], "name": "공학관", "bld": "E"}
    ).json()
    r = client.post("/api/rooms", json={"building_id": b["id"], "room": 301, "units": 2}).json()
    return sch, b, r


def test_crud_and_slot_put_creates_outbox_rows(client, app):
    _sch, _b, r = _setup(client)
    assert client.get("/api/rooms").json()[0]["room"] == 301
    res = client.put(
        f"/api/rooms/{r['id']}/slots",
        json={
            "day": 1,
            "s_h": 9,
            "s_m": 0,
            "e_h": 10,
            "e_m": 50,
            "type": 1,
            "subject": "자료구조",
            "professor": "김",
        },
    )
    assert res.status_code == 200 and len(res.json()["outbox_ids"]) == 2
    assert client.get(f"/api/rooms/{r['id']}/slots").json()[0]["subject"] == "자료구조"
    # 같은 멱등키 → 갱신(행 1개 유지), 버전 2
    client.put(
        f"/api/rooms/{r['id']}/slots",
        json={
            "day": 1,
            "s_h": 9,
            "s_m": 0,
            "e_h": 10,
            "e_m": 50,
            "type": 3,
            "subject": "휴강",
            "professor": "김",
        },
    )
    assert len(client.get(f"/api/rooms/{r['id']}/slots").json()) == 1
    with app.state.Session() as s:
        rows = s.scalars(select(Outbox).order_by(Outbox.id)).all()
        assert [x.new_ver for x in rows] == [1, 1, 2, 2]
        p = json.loads(rows[2].payload)
        assert p["type"] == 3 and p["subject"] == "휴강"


def test_slot_delete_day_clear_resv_exam_sync_cmd(client, app):
    _sch, _b, r = _setup(client)
    rid = r["id"]
    client.put(
        f"/api/rooms/{rid}/slots",
        json={
            "day": 2,
            "s_h": 9,
            "s_m": 0,
            "e_h": 10,
            "e_m": 0,
            "type": 1,
            "subject": "a",
            "professor": "b",
        },
    )
    assert client.delete(f"/api/rooms/{rid}/slots/2/9/0").status_code == 200
    assert client.get(f"/api/rooms/{rid}/slots").json() == []
    assert client.delete(f"/api/rooms/{rid}/slots?day=3").json()["outbox_ids"]
    res = client.post(
        f"/api/rooms/{rid}/reservations",
        json={
            "id": 7,
            "date": "2026-09-16",
            "s_h": 13,
            "s_m": 0,
            "e_h": 15,
            "e_m": 0,
            "type": 6,
            "subject": "대여",
            "professor": "",
        },
    )
    assert res.status_code == 200
    assert client.delete(f"/api/rooms/{rid}/reservations/7").status_code == 200
    assert (
        client.post(
            f"/api/rooms/{rid}/exams",
            json={"id": 3, "date_start": "2026-10-19", "date_end": "2026-10-23"},
        ).status_code
        == 200
    )
    assert client.delete(f"/api/rooms/{rid}/exams/3").status_code == 200
    assert client.post(f"/api/rooms/{rid}/sync", json={"kinds": ["schedule"]}).json()["outbox_ids"]
    assert client.post(f"/api/rooms/{rid}/cmd", json={"cmd": 4, "args_hex": ""}).status_code == 200
    with app.state.Session() as s:
        types = [x.type for x in s.scalars(select(Outbox).order_by(Outbox.id))]
    assert (
        types
        == ["SLOT_SET"] * 2
        + ["SLOT_DEL"] * 2
        + ["DAY_CLEAR"] * 2
        + ["RESV_SET"] * 2
        + ["RESV_DEL"] * 2
        + ["EXAM_SET"] * 2
        + ["EXAM_DEL"] * 2
        + ["FILE"] * 2
        + ["CMD"] * 2
    )


def test_sync_rejects_bogus_kind(client):
    _sch, _b, r = _setup(client)
    assert client.post(f"/api/rooms/{r['id']}/sync", json={"kinds": ["bogus"]}).status_code == 422


def test_create_building_with_ghost_modem_returns_409(client):
    sch = client.post("/api/schools", json={"name": "명지", "net_id": 75}).json()
    res = client.post(
        "/api/buildings",
        json={"school_id": sch["id"], "name": "공학관", "bld": "E", "modem_id": "ghost"},
    )
    assert res.status_code == 409


def test_validation_errors(client):
    _sch, _b, r = _setup(client)
    bad = client.put(
        f"/api/rooms/{r['id']}/slots",
        json={
            "day": 1,
            "s_h": 9,
            "s_m": 0,
            "e_h": 10,
            "e_m": 0,
            "type": 1,
            "subject": "가" * 7,
            "professor": "",
        },
    )  # 21 B
    assert bad.status_code == 422 and "20 B" in str(
        bad.json()
    )  # Pydantic 검증 = 422 (FastAPI 표준)
    assert (
        client.put(
            "/api/rooms/999/slots",
            json={
                "day": 1,
                "s_h": 9,
                "s_m": 0,
                "e_h": 10,
                "e_m": 0,
                "type": 1,
                "subject": "a",
                "professor": "",
            },
        ).status_code
        == 404
    )
    assert (
        client.post("/api/rooms", json={"building_id": 1, "room": 302, "units": 3}).status_code
        == 422
    )


def test_resv_outside_horizon_stored_but_not_enqueued(client, app):
    _sch, _b, r = _setup(client)
    rid = r["id"]
    today = dt.datetime.now(dt.UTC).date()
    far = (today + dt.timedelta(days=60)).isoformat()
    res = client.post(
        f"/api/rooms/{rid}/reservations",
        json={
            "id": 9,
            "date": far,
            "s_h": 13,
            "s_m": 0,
            "e_h": 15,
            "e_m": 0,
            "type": 6,
            "subject": "먼예약",
            "professor": "",
        },
    )
    assert res.status_code == 200 and res.json()["outbox_ids"] == []
    assert [x["id"] for x in client.get(f"/api/rooms/{rid}/reservations").json()] == [9]
    with app.state.Session() as s:
        assert s.scalars(select(Outbox).where(Outbox.type == "RESV_SET")).all() == []

    tomorrow = (today + dt.timedelta(days=1)).isoformat()
    res2 = client.post(
        f"/api/rooms/{rid}/reservations",
        json={
            "id": 10,
            "date": tomorrow,
            "s_h": 13,
            "s_m": 0,
            "e_h": 15,
            "e_m": 0,
            "type": 6,
            "subject": "내일",
            "professor": "",
        },
    )
    assert res2.status_code == 200 and len(res2.json()["outbox_ids"]) == 2  # units=2


def test_building_gets_modem_reassigns_queued_jobs(client, app):
    """PR #5 I1 — 모뎀 없는 건물에 쌓인 outbox 는 모뎀 배정 PATCH 뒤 그 모뎀으로 재지정된다."""
    sch = client.post("/api/schools", json={"name": "명지", "net_id": 75}).json()
    b = client.post(
        "/api/buildings", json={"school_id": sch["id"], "name": "공학관", "bld": "E"}
    ).json()
    r = client.post("/api/rooms", json={"building_id": b["id"], "room": 301, "units": 1}).json()
    res = client.put(
        f"/api/rooms/{r['id']}/slots",
        json={
            "day": 1,
            "s_h": 9,
            "s_m": 0,
            "e_h": 10,
            "e_m": 0,
            "type": 1,
            "subject": "a",
            "professor": "b",
        },
    )
    oid = res.json()["outbox_ids"][0]
    with app.state.Session() as s:
        assert s.get(Outbox, oid).modem_id is None
    api.register_modem("m1")
    client.patch(
        f"/api/buildings/{b['id']}",
        json={"school_id": sch["id"], "name": "공학관", "bld": "E", "modem_id": "m1"},
    )
    with app.state.Session() as s:
        assert s.get(Outbox, oid).modem_id == "m1"


def test_room_change_resends_config_after_commit(client, app):
    api.register_modem("m1")  # buildings.modem_id FK
    seen = []
    app.state.hub.config_changed = lambda mid: seen.append((mid, sorted(api._topology.nodes(mid))))
    sch = client.post("/api/schools", json={"name": "명지", "net_id": 75}).json()
    b = client.post(
        "/api/buildings",
        json={"school_id": sch["id"], "name": "공학관", "bld": "E", "modem_id": "m1"},
    ).json()
    r = client.post("/api/rooms", json={"building_id": b["id"], "room": 301, "units": 2}).json()
    assert seen[-1] == ("m1", [("E", 301, 1), ("E", 301, 2)])  # 커밋 뒤에 불렸다
    client.patch(f"/api/rooms/{r['id']}", json={"building_id": b["id"], "room": 301, "units": 1})
    assert seen[-1] == ("m1", [("E", 301, 1)])
    client.delete(f"/api/rooms/{r['id']}")
    assert seen[-1] == ("m1", [])


def test_put_slot_source_default_and_409_on_downgrade(client):
    _sch, _b, r = _setup(client)
    body = {
        "day": 2,
        "s_h": 9,
        "s_m": 0,
        "e_h": 10,
        "e_m": 0,
        "type": 1,
        "subject": "a",
        "professor": "",
    }
    assert client.put(f"/api/rooms/{r['id']}/slots", json=body).status_code == 200
    assert client.get(f"/api/rooms/{r['id']}/slots").json()[0]["source"] == 2
    # 긴급으로 올리기 (2 → 3) 허용
    assert (
        client.put(f"/api/rooms/{r['id']}/slots", json={**body, "type": 3, "source": 3}).status_code
        == 200
    )
    assert client.get(f"/api/rooms/{r['id']}/slots").json()[0]["source"] == 3
    # 수동(기본 2)·포털(1)로 덮기 → 409
    assert client.put(f"/api/rooms/{r['id']}/slots", json=body).status_code == 409
    assert client.put(f"/api/rooms/{r['id']}/slots", json={**body, "source": 1}).status_code == 409
    assert client.get(f"/api/rooms/{r['id']}/slots").json()[0]["type"] == 3  # 그대로
    # 삭제는 출처 무시
    assert client.delete(f"/api/rooms/{r['id']}/slots/2/9/0").status_code == 200
    assert client.get(f"/api/rooms/{r['id']}/slots").json() == []
    # 범위 밖 source
    assert client.put(f"/api/rooms/{r['id']}/slots", json={**body, "source": 4}).status_code == 422

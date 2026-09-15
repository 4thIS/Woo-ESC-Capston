import datetime as dt
import json

import pytest
from lora_proto import codec as C
from lora_proto import proto as P
from sqlalchemy import select

from app.lora_service import api
from app.lora_service.models import Outbox, RoomVersion


def _rows(db):
    with db() as s:
        return list(s.scalars(select(Outbox).order_by(Outbox.id)))


def test_slot_set_unit0_splits_into_units_with_same_ver(db, hub):
    ids = api.enqueue_slot_set("E", 301, 1, (9, 0), (10, 50), 1, "자료구조", "김교수")
    rows = _rows(db)
    assert [r.id for r in rows] == ids and len(rows) == 2
    assert [r.unit for r in rows] == [1, 2]
    assert {r.new_ver for r in rows} == {1}
    assert rows[0].state == "queued" and rows[0].modem_id == "m1" and rows[0].priority == 3
    payload = json.loads(rows[0].payload)
    assert "new_ver" not in payload
    assert C.SlotSet(new_ver=1, **payload).subject == "자료구조"  # 키 = codec 필드명
    assert hub.notified == ["m1"]


def test_unit1_only_one_row(db):
    ids = api.enqueue_slot_set("E", 301, 1, (9, 0), (10, 50), 1, "a", "b", unit=2)
    assert len(ids) == 1 and _rows(db)[0].unit == 2


def test_version_increments_and_rolls_255_to_1(db):
    with db() as s, s.begin():
        s.add(RoomVersion(bld="E", room=302, kind="schedule", ver=255))
    api.enqueue_slot_set("E", 302, 1, (9, 0), (10, 0), 1, "a", "b")
    assert _rows(db)[0].new_ver == 1
    api.enqueue_slot_set("E", 302, 2, (9, 0), (10, 0), 1, "a", "b")
    assert _rows(db)[1].new_ver == 2


def test_bad_subject_rolls_back_version_and_inserts_nothing(db, hub):
    with pytest.raises(ValueError):
        api.enqueue_slot_set("E", 301, 1, (9, 0), (10, 0), 1, "가" * 7, "b")  # 21 B > 20
    with db() as s:
        assert s.get(RoomVersion, ("E", 301, "schedule")) is None
    assert _rows(db) == [] and hub.notified == []


def test_unknown_room_raises_not_found(db):
    with pytest.raises(api.NotFound):
        api.enqueue_slot_set("E", 999, 1, (9, 0), (10, 0), 1, "a", "b")


def test_each_kind_bumps_its_own_version(db):
    api.enqueue_slot_del("E", 302, 1, (9, 0))
    api.enqueue_resv_set("E", 302, 7, dt.date(2026, 9, 20), (13, 0), (15, 0), 6, "대여", "")
    api.enqueue_exam_set("E", 302, 3, dt.date(2026, 10, 19), dt.date(2026, 10, 23))
    api.enqueue_day_clear("E", 302, 3)
    rows = _rows(db)
    assert [(r.type, r.new_ver, r.priority) for r in rows] == [
        ("SLOT_DEL", 1, 3),
        ("RESV_SET", 1, 1),
        ("EXAM_SET", 1, 3),
        ("DAY_CLEAR", 2, 3),
    ]
    resv = json.loads(rows[1].payload)
    assert resv["year"] == 2026 and resv["resv_id"] == 7
    exam = json.loads(rows[2].payload)
    assert (exam["y1"], exam["m1"], exam["d1"], exam["y2"]) == (2026, 10, 19, 2026)


def test_cmd_has_no_version_and_hex_args(db):
    api.enqueue_cmd("E", 302, P.Cmd.SET_PARAM, b"\x01\x00\x00\x00\x12")
    r = _rows(db)[0]
    assert r.type == "CMD" and r.new_ver is None
    assert json.loads(r.payload) == {"cmd": int(P.Cmd.SET_PARAM), "args": "0100000012"}


def test_full_sync_reads_records_and_dedupes(db):
    api.set_record_provider(
        lambda bld, room, kind: (
            [C.SlotSet(0, 1, 9, 0, 10, 0, 1, "a", "b")] if kind == "schedule" else []
        )
    )
    ids = api.enqueue_full_sync("E", 302, kinds=("schedule",))
    again = api.enqueue_full_sync("E", 302, kinds=("schedule",))
    assert ids == again  # queued FILE 이 있으면 새로 만들지 않고 기존 id
    r = _rows(db)[0]
    p = json.loads(r.payload)
    assert r.type == "FILE" and r.priority == 5 and r.new_ver == 1
    assert p["kind"] == 1 and p["records"][0]["subject"] == "a" and "new_ver" not in p["records"][0]
    with db() as s, s.begin():
        s.get(Outbox, ids[0]).state = "acked"
    later = api.enqueue_full_sync("E", 302, kinds=("schedule",))
    assert (
        _rows(db)[-1].id == later[0] and _rows(db)[-1].new_ver == 1
    )  # 재동기는 bump 없이 현재 버전


def test_full_sync_dedupes_per_unit(db):
    ids = api.enqueue_full_sync("E", 301, kinds=("schedule",))  # units 1,2
    assert len(ids) == 2
    with db() as s, s.begin():
        s.get(Outbox, ids[0]).state = "acked"  # unit 1 끝남, unit 2 는 아직 queued
    again = api.enqueue_full_sync("E", 301, kinds=("schedule",))
    assert len(again) == 2 and again[1] == ids[1] and again[0] != ids[0]
    with db() as s:
        new = s.get(Outbox, again[0])
        assert new.unit == 1 and new.state == "queued" and new.new_ver == 1  # 재동기는 bump 없음
        assert s.get(RoomVersion, ("E", 301, "schedule")).ver == 1


def test_provision_uses_ident_version(db):
    oid = api.provision("aabbccddeeff", "E", 302, 1)
    r = _rows(db)[0]
    assert r.id == oid and r.type == "SET_ROOM" and r.new_ver == 1 and r.unit == 1
    assert json.loads(r.payload) == {"mac": "aabbccddeeff", "bld": ord("E"), "room": 302, "unit": 1}


def test_get_outbox_and_cancel(db, hub):
    ids = api.enqueue_slot_set("E", 301, 1, (9, 0), (10, 0), 1, "a", "b")
    assert [r.id for r in api.get_outbox(state="queued", bld="E", room=301)] == ids
    assert api.cancel(ids[0]) is True
    assert _rows(db)[0].state == "cancelled" and hub.cancels == []
    with db() as s, s.begin():
        s.get(Outbox, ids[1]).state = "dispatched"
    assert api.cancel(ids[1]) is True
    assert _rows(db)[1].state == "dispatched" and hub.cancels == [
        ("m1", ids[1])
    ]  # 모뎀Pi 응답 대기
    assert api.cancel(99999) is False


def test_request_time_broadcast_calls_hub(db, hub):
    api.request_time_broadcast()
    assert hub.time_calls == 1

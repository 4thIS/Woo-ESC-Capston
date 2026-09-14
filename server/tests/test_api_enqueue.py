import json

import pytest
from lora_proto import codec as C
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

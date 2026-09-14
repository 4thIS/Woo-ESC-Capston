import pytest

from lora_proto import codec as C
from lora_proto import jsonio
from lora_proto import proto as P

MAC = bytes.fromhex("a0b1c2d3e4f5")


def test_bytes_fields_are_lowercase_hex_without_separator():
    d = jsonio.to_json(C.SetRoom(1, MAC, ord("E"), 301, 2))
    assert d == {"new_ver": 1, "mac": "a0b1c2d3e4f5", "bld": 69, "room": 301, "unit": 2}
    assert jsonio.from_json(P.Type.SET_ROOM, d) == C.SetRoom(1, MAC, 69, 301, 2)


def test_nested_status_ack_roundtrip():
    st = C.Status(C.Ack(0, 0, 3900, 2, 0, 0, 1, 20, 4), -90, 20, 0, 10)
    d = jsonio.to_json(st)
    assert d["ack"]["sched_ver"] == 2 and d["rssi_last"] == -90
    assert jsonio.from_json(P.Type.STATUS, d) == st


def test_drop_new_ver_for_file_records_and_inject_on_read():
    """계약 ⑥: FILE records[] 에는 new_ver 가 없고, 모뎀Pi 가 job.new_ver 를 주입해 codec 객체를 만든다."""
    rec = C.SlotSet(7, 3, 9, 0, 10, 50, 1, "임베디드SW", "정필성")
    d = jsonio.to_json(rec, drop=("new_ver",))
    assert "new_ver" not in d
    assert jsonio.from_json(P.Type.SLOT_SET, d, new_ver=9) == C.SlotSet(
        9, 3, 9, 0, 10, 50, 1, "임베디드SW", "정필성"
    )


def test_missing_field_is_key_error():
    with pytest.raises(KeyError):
        jsonio.from_json(P.Type.SLOT_DEL, {"new_ver": 1, "day": 1})


def test_every_type_has_a_class():
    assert set(jsonio.CLASSES) == {int(t) for t in P.Type}

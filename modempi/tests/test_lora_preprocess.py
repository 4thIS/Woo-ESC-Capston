"""preprocess — jobs 행을 공중에 나갈 단위로 (S6 spec §4.2, 로드맵 §4.2 인코딩 규칙)."""

import json

import pytest
from lora_proto import codec as C
from lora_proto import proto as P

from modempi.lora.preprocess import PreprocessError, Unit, is_file_session, preprocess
from modempi.store import SqliteStore

from .conftest import FakeClock


@pytest.fixture
def db():
    s = SqliteStore(":memory:")
    yield s
    s.close()


def job(db, *, job_id="10", bld="E", room=301, unit=1, type="SLOT_SET", payload=None, new_ver=3):
    db.put_job(
        job_id=job_id,
        bld=bld,
        room=room,
        unit=unit,
        type=type,
        payload=json.dumps(
            payload
            if payload is not None
            else {
                "day": 1,
                "s_h": 9,
                "s_m": 0,
                "e_h": 9,
                "e_m": 50,
                "type": 1,
                "subject": "자료구조",
                "professor": "김교수",
            }
        ),
        priority=3,
        new_ver=new_ver,
    )
    return db.get_job(job_id)


def test_normal_downlink_is_one_wake_unit_with_ack_req(db):
    [u] = preprocess(job(db))
    assert isinstance(u, Unit)
    assert (u.bld, u.room, u.unit, u.type) == (ord("E"), 301, 1, P.Type.SLOT_SET)
    assert (u.wake, u.ack_ms, u.flags) == (True, 3000, P.FLAG_ACK_REQ)
    assert u.payload_obj == C.SlotSet(3, 1, 9, 0, 9, 50, 1, "자료구조", "김교수")
    assert is_file_session([u]) is False


def test_unit_zero_non_time_is_rejected(db):
    with pytest.raises(PreprocessError, match="unit0"):
        preprocess(job(db, unit=0))


def test_bad_payload_is_reported_with_reason(db):
    with pytest.raises(PreprocessError, match="bad_payload"):
        preprocess(job(db, payload={"day": 1}))


def test_broadcast_time_restamps_epoch_and_has_no_ack(db):
    clk = FakeClock()
    j = job(
        db,
        job_id="time-1",
        bld="",
        room=0,
        unit=0,
        type="TIME",
        new_ver=None,
        payload={"epoch": 1_700_000_000, "flags": int(P.TimeFlag.REQUEST_STATUS)},
    )
    [u] = preprocess(j, clock=clk)
    assert (u.bld, u.room, u.unit) == (P.BLD_ALL, P.ROOM_ALL, 0)
    assert (u.wake, u.ack_ms, u.flags) == (True, 0, P.FLAG_BROADCAST)
    assert u.payload_obj == C.Time(int(clk.now), int(P.TimeFlag.REQUEST_STATUS))


def test_targeted_time_keeps_node_address_and_no_broadcast_flag(db):
    j = job(db, job_id="time-2-E301-1", type="TIME", new_ver=None, payload={"epoch": 1, "flags": 0})
    [u] = preprocess(j)
    assert (u.bld, u.room, u.unit, u.flags, u.ack_ms) == (ord("E"), 301, 1, 0, 0)


def test_file_becomes_begin_data_end_with_only_begin_waking(db):
    recs = [
        {
            "day": d,
            "s_h": 9,
            "s_m": 0,
            "e_h": 9,
            "e_m": 50,
            "type": 1,
            "subject": f"과목{d}",
            "professor": "김교수",
        }
        for d in range(1, 6)
    ]
    j = job(db, type="FILE", new_ver=7, payload={"kind": int(P.FileKind.SCHEDULE), "records": recs})
    units = preprocess(j)
    assert is_file_session(units) is True
    expected = [P.Type.FILE_BEGIN] + [P.Type.FILE_DATA] * (len(units) - 2) + [P.Type.FILE_END]
    assert [u.type for u in units] == expected
    assert [u.wake for u in units] == [True] + [False] * (len(units) - 1)
    assert all(u.ack_ms == 3000 and u.flags == P.FLAG_ACK_REQ for u in units)
    assert units[0].payload_obj.new_ver == 7
    assert units[0].payload_obj.kind == P.FileKind.SCHEDULE


def test_file_with_wrong_kind_is_bad_payload(db):
    j = job(
        db,
        type="FILE",
        new_ver=7,
        payload={
            "kind": int(P.FileKind.RESV),
            "records": [
                {
                    "day": 1,
                    "s_h": 9,
                    "s_m": 0,
                    "e_h": 9,
                    "e_m": 50,
                    "type": 1,
                    "subject": "a",
                    "professor": "b",
                }
            ],
        },
    )
    with pytest.raises(PreprocessError, match="bad_payload"):
        preprocess(j)


@pytest.mark.parametrize("payload", ["[]", "3", '"x"', "null"])
def test_any_malformed_payload_is_preprocess_error_not_a_crash(db, payload):
    """최상위가 객체가 아닌 payload 도 PreprocessError 여야 한다 — 워커는 이것만 잡아 failed 로 닫는다.
    AttributeError 가 그대로 올라가면 워커 루프가 통째로 죽어 그 모뎀Pi 가 멈춘다."""
    db.put_job(
        job_id="99", bld="", room=0, unit=0, type="TIME", payload=payload, priority=0, new_ver=None
    )
    with pytest.raises(PreprocessError, match="bad_payload"):
        preprocess(db.get_job("99"))

    db.put_job(
        job_id="98",
        bld="E",
        room=301,
        unit=1,
        type="SLOT_SET",
        payload=payload,
        priority=3,
        new_ver=1,
    )
    with pytest.raises(PreprocessError, match="bad_payload"):
        preprocess(db.get_job("98"))

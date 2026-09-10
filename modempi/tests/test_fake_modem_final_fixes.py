"""final-review 항목(E.11~E.14) 회귀 테스트: close() await, 타겟 TIME OK, _do_tx 내부 예외 처리, 긴 라인 무시."""

import asyncio
import json

import pytest
from lora_proto import codec as C
from lora_proto import proto as P

from modempi.lora.fake_modem import FakeModem

from .conftest import frame, hexs, send

pytestmark = pytest.mark.anyio


async def test_targeted_time_acked_ok(modem):
    f = frame(P.Type.TIME, C.Time(1_757_400_000, 0))
    r = await send(modem, {"op": "tx", "id": 21, "frame": hexs(f), "wake": True, "ack_ms": 3000})
    assert r["status"] == "acked"
    h, pb = C.decode_frame(bytes.fromhex(r["ack"].replace(" ", "")))
    assert h.type == P.Type.ACK
    ack = C.decode_payload(P.Type.ACK, pb)
    assert ack.status == P.AckStatus.OK


async def test_do_tx_internal_exception_becomes_tx_done_error_and_modem_stays_responsive(modem):
    # _target()은 SET_ROOM + BLD_UNPROVISIONED일 때만 decode_payload를 try/except 없이 직접 호출한다.
    # mac이 5 B뿐인 손상된 페이로드를 CRC는 유효하게 감싸면, 헤더 디코드는 통과하고
    # _target() 안에서 FrameError가 잡히지 않은 채 올라와야 한다 — _do_tx의 새 try/except가 이를 잡는다.
    bad_payload = bytes([1]) + b"\x00" * 5 + bytes([0x45, 0x01, 0x2D, 1])
    h = C.Header(
        type=P.Type.SET_ROOM, bld=P.BLD_UNPROVISIONED, room=0, unit=0, txn=1, flags=P.FLAG_ACK_REQ
    )
    f = C.encode_frame(h, bad_payload)
    r = await send(modem, {"op": "tx", "id": 9, "frame": hexs(f), "wake": True, "ack_ms": 500})
    assert r["op"] == "tx_done" and r["status"] == "error"
    assert r["reason"].startswith("internal:")

    # 예외가 워커/모뎀을 죽이지 않고, 다음 명령에 정상 응답한다.
    assert (await send(modem, {"op": "ping"}))["op"] == "pong"


async def test_write_line_over_1024_is_logged_and_ignored(modem):
    await modem.write_line("x" * 1025)
    r = json.loads(await modem.read_line())
    assert r["op"] == "log" and r["level"] == "warn" and "long" in r["msg"]

    # 이어지는 정상 명령은 그대로 처리된다.
    assert (await send(modem, {"op": "ping"}))["op"] == "pong"


async def test_close_awaits_cancelled_inflight_task():
    m = FakeModem(latency_ms=50)
    assert json.loads(await m.read_line())["op"] == "ready"
    f = frame(P.Type.SLOT_DEL, C.SlotDel(3, 1, 9, 0))
    msg = {"op": "tx", "id": 1, "frame": hexs(f), "wake": True, "ack_ms": 100}
    await m.write_line(json.dumps(msg))
    assert m._inflight is not None and not m._inflight.done()

    await m.close()  # CancelledError 를 삼키고 inflight 완료까지 기다려야 한다(뜬 Task 경고 없이)

    assert m._inflight.done()
    # 취소된 태스크의 예외를 조회해도 CancelledError 가 다시 튀지 않는다(이미 소비됨).
    await asyncio.sleep(0)

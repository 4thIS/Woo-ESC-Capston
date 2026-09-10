import json

import pytest
from lora_proto import codec as C
from lora_proto import proto as P

from modempi.lora.fake_modem import FakeModem

from .conftest import E, frame, hexs, send

pytestmark = pytest.mark.anyio


async def test_ready_line_first():
    m = FakeModem()
    r = json.loads(await m.read_line())
    assert (
        r["op"] == "ready"
        and r["fw"] == "gw-2.0.0"
        and r["sf"] == P.RADIO["RP_SF"]
        and r["freq"] == 922.5
    )


async def test_ping_pong_and_stats(modem):
    assert (await send(modem, {"op": "ping"}))["op"] == "pong"
    s = await send(modem, {"op": "stats"})
    assert s["op"] == "stats" and s["tx"] == 0


async def test_tx_acked_updates_node_and_returns_decodable_ack(modem):
    f = frame(P.Type.SLOT_SET, C.SlotSet(3, 3, 9, 0, 10, 50, 1, "s", "p"))
    r = await send(modem, {"op": "tx", "id": 17, "frame": hexs(f), "wake": True, "ack_ms": 3000})
    assert r["op"] == "tx_done" and r["id"] == 17 and r["status"] == "acked"
    assert isinstance(r["rssi"], int) and isinstance(r["snr"], float) and r["air_ms"] > 0
    h, pb = C.decode_frame(bytes.fromhex(r["ack"].replace(" ", "")))
    req_h, _ = C.decode_frame(f)
    assert req_h.matches_ack(h)
    ack = C.decode_payload(P.Type.ACK, pb)
    assert ack.status == P.AckStatus.OK and ack.sched_ver == 3
    assert modem.nodes[(E, 301, 1)].sched_ver == 3
    assert modem.stats["tx"] == 1 and modem.stats["acked"] == 1


async def test_ack_ms_zero_is_sent(modem):
    f = frame(
        P.Type.TIME,
        C.Time(1_757_400_000, 0),
        bld=P.BLD_ALL,
        room=P.ROOM_ALL,
        unit=0,
        txn=0,
        flags=P.FLAG_BROADCAST,
    )
    r = await send(modem, {"op": "tx", "id": 1, "frame": hexs(f), "wake": True, "ack_ms": 0})
    assert r["status"] == "sent"


async def test_unregistered_target_no_ack(modem):
    f = frame(P.Type.SLOT_DEL, C.SlotDel(3, 1, 9, 0), room=999)
    r = await send(modem, {"op": "tx", "id": 2, "frame": hexs(f), "wake": True, "ack_ms": 500})
    assert r["status"] == "no_ack"


async def test_unit0_is_not_a_node(modem):
    f = frame(P.Type.SLOT_DEL, C.SlotDel(3, 1, 9, 0), unit=0)
    r = await send(modem, {"op": "tx", "id": 3, "frame": hexs(f), "wake": True, "ack_ms": 500})
    assert r["status"] == "no_ack"


async def test_bad_frame_is_error(modem):
    f = bytearray(frame(P.Type.SLOT_DEL, C.SlotDel(3, 1, 9, 0)))
    f[-1] ^= 0xFF
    r = await send(
        modem, {"op": "tx", "id": 4, "frame": hexs(bytes(f)), "wake": False, "ack_ms": 100}
    )
    assert r["status"] == "error" and r["reason"] == "bad_crc8"


async def test_unparseable_line_is_logged_and_ignored(modem):
    await modem.write_line("this is not json")
    r = json.loads(await modem.read_line())
    assert r["op"] == "log" and r["level"] == "warn"


async def test_uplink_injection_arrives_as_rx(modem):
    st = C.Status(C.Ack(0, 0, 3900, 2, 0, 0, 1, 20, 4), -90, 20, 0, 10)
    f = frame(P.Type.STATUS, st, txn=0, flags=0)
    modem.inject_uplink(f, rssi=-90, snr=5.0)
    r = json.loads(await modem.read_line())
    assert r["op"] == "rx" and r["rssi"] == -90 and bytes.fromhex(r["frame"].replace(" ", "")) == f

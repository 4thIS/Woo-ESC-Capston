import asyncio
import json

import pytest
from lora_proto import codec as C
from lora_proto import proto as P

from .conftest import frame, hexs, send

pytestmark = pytest.mark.anyio
F = frame(P.Type.DAY_CLEAR, C.DayClear(3, 2))


async def test_script_no_ack_then_auto(modem):
    modem.script(["no_ack"])
    r1 = await send(modem, {"op": "tx", "id": 1, "frame": hexs(F), "wake": True, "ack_ms": 100})
    r2 = await send(modem, {"op": "tx", "id": 2, "frame": hexs(F), "wake": True, "ack_ms": 100})
    assert r1["status"] == "no_ack" and r2["status"] == "acked"


async def test_script_cad_busy_reports_tries(modem):
    modem.script(["cad_busy"])
    r = await send(modem, {"op": "tx", "id": 1, "frame": hexs(F), "wake": True, "ack_ms": 100})
    assert r["status"] == "cad_busy" and r["tries"] == P.RADIO["RP_CAD_MAX_TRIES"]


@pytest.mark.parametrize(
    "tok,status",
    [
        ("ack:BUSY", P.AckStatus.BUSY),
        ("ack:STORE_FAIL", P.AckStatus.STORE_FAIL),
        ("ack:BAD_PAYLOAD", P.AckStatus.BAD_PAYLOAD),
    ],
)
async def test_script_forced_ack_status(modem, tok, status):
    modem.script([tok])
    r = await send(modem, {"op": "tx", "id": 1, "frame": hexs(F), "wake": True, "ack_ms": 100})
    _, pb = C.decode_frame(bytes.fromhex(r["ack"].replace(" ", "")))
    assert r["status"] == "acked" and C.decode_payload(P.Type.ACK, pb).status == status


async def test_forced_busy_does_not_apply_version(modem):
    modem.script(["ack:BUSY"])
    await send(modem, {"op": "tx", "id": 1, "frame": hexs(F), "wake": True, "ack_ms": 100})
    assert modem.nodes[(ord("E"), 301, 1)].sched_ver == 2


async def test_concurrent_tx_rejected_with_busy():
    from modempi.lora.fake_modem import FakeModem

    m = FakeModem(latency_ms=200)
    m.add_node(ord("E"), 301, 1, sched_ver=2)
    await m.read_line()
    await m.write_line(
        json.dumps({"op": "tx", "id": 1, "frame": hexs(F), "wake": True, "ack_ms": 100})
    )
    await asyncio.sleep(0.02)
    await m.write_line(
        json.dumps({"op": "tx", "id": 2, "frame": hexs(F), "wake": True, "ack_ms": 100})
    )
    first = json.loads(await m.read_line())
    second = json.loads(await m.read_line())
    assert first == {"op": "tx_done", "id": 2, "status": "error", "reason": "busy"}
    assert second["id"] == 1 and second["status"] == "acked"
    await m.close()


async def test_unknown_token_raises(modem):
    with pytest.raises(ValueError):
        modem.script(["explode"])

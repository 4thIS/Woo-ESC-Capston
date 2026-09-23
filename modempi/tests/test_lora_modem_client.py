import asyncio

import pytest
from lora_proto import codec as C
from lora_proto import proto as P

from modempi.lora.fake_modem import FakeModem
from modempi.lora.modem_client import ModemClient, RxEvent

from .conftest import frame

pytestmark = pytest.mark.anyio

F = frame(P.Type.DAY_CLEAR, C.DayClear(3, 2), txn=7)


@pytest.fixture
async def client():
    m = FakeModem()
    # DayClear(new_ver=3) 가 연속 버전이 되도록 2 — 1 이면 가상 노드가 GAP 를 돌려준다.
    m.add_node(ord("E"), 301, 1, sched_ver=2)
    c = ModemClient(m)
    await c.start()
    yield c
    await c.stop()


async def test_start_waits_for_ready_and_records_fw(client):
    assert client.fw == "gw-2.0.0"


async def test_tx_acked_carries_ack_frame_and_radio_stats(client):
    r = await client.tx(F, wake=True, ack_ms=100)
    assert r.status == "acked" and r.rssi is not None and r.air_ms is not None
    h, pb = C.decode_frame(r.ack)
    assert h.type == P.Type.ACK and h.txn == 7
    assert C.decode_payload(P.Type.ACK, pb).status == P.AckStatus.OK


async def test_concurrent_tx_is_runtime_error(client):
    async def send():
        return await client.tx(F, wake=True, ack_ms=100)

    with pytest.raises(RuntimeError):
        await asyncio.gather(send(), send())


async def test_no_ack_and_cad_busy_pass_through(client):
    client._t.script(["no_ack", "cad_busy"])
    assert (await client.tx(F, wake=True, ack_ms=50)).status == "no_ack"
    r = await client.tx(F, wake=True, ack_ms=50)
    assert r.status == "cad_busy" and r.tries == P.RADIO["RP_CAD_MAX_TRIES"]


async def test_ack_ms_zero_returns_sent(client):
    r = await client.tx(
        frame(
            P.Type.TIME,
            C.Time(1_800_000_000, 0),
            txn=0,
            flags=P.FLAG_BROADCAST,
            bld=P.BLD_ALL,
            room=P.ROOM_ALL,
            unit=0,
        ),
        wake=True,
        ack_ms=0,
    )
    assert r.status == "sent"


async def test_unsolicited_uplink_goes_to_rx_queue(client):
    up = frame(
        P.Type.HELLO,
        C.Hello(bytes.fromhex("a0b1c2d3e4f5"), 20, 4000),
        bld=P.BLD_UNPROVISIONED,
        room=0,
        unit=0,
        txn=0,
        flags=0,
    )
    client._t.inject_uplink(up)
    ev = await asyncio.wait_for(client.rx.get(), 2)
    assert isinstance(ev, RxEvent) and ev.frame == up


async def test_ping_returns_uptime(client):
    assert await client.ping() >= 0

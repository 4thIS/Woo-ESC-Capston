import asyncio
import json

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


async def test_ping_waits_for_in_flight_tx_instead_of_raising():
    """v2 §4.5 워치독 핑은 10 s 마다 나간다 — 송신 중이라고 예외를 내면 파이프라인이 죽는다.
    tx 끼리 겹치는 것만 워커 버그(RuntimeError)이고, ping 은 순번을 기다린다."""
    m = FakeModem(latency_ms=60)
    m.add_node(ord("E"), 301, 1, sched_ver=2)
    c = ModemClient(m)
    await c.start()
    try:
        tx = asyncio.create_task(c.tx(F, wake=True, ack_ms=50))
        await asyncio.sleep(0.01)  # tx 가 인플라이트인 동안
        uptime = await c.ping()
        assert uptime > 0
        assert (await tx).status == "acked"
    finally:
        await c.stop()


class _DeafTransport:
    """ready 만 주고 그 뒤로는 아무 응답도 하지 않는 모뎀(라인은 삼킨다)."""

    def __init__(self) -> None:
        self._out: asyncio.Queue[str] = asyncio.Queue()
        self._out.put_nowait(json.dumps({"op": "ready", "fw": "gw-2.0.0"}))
        self.written: list[str] = []

    async def write_line(self, line: str) -> None:
        self.written.append(line)

    async def read_line(self) -> str:
        return await self._out.get()

    async def close(self) -> None:
        pass


async def test_tx_times_out_instead_of_hanging_forever():
    """tx_done 이 영영 안 오면(id 불일치로 무시됐거나 모뎀이 죽었거나) 워커가 영구 대기한다.
    error/modem_timeout 으로 돌려 워커가 failed 로 닫게 한다."""
    c = ModemClient(_DeafTransport(), request_timeout=0.05)
    await c.start()
    try:
        r = await c.tx(F, wake=True, ack_ms=0)
        assert (r.status, r.reason) == ("error", "modem_timeout")
        r2 = await c.tx(F, wake=True, ack_ms=0)  # 슬롯이 풀려 다음 요청이 가능해야 한다
        assert r2.status == "error"
    finally:
        await c.stop()


async def test_ping_timeout_raises_so_watchdog_can_react():
    c = ModemClient(_DeafTransport(), request_timeout=0.05)
    await c.start()
    try:
        with pytest.raises(TimeoutError):
            await c.ping()
    finally:
        await c.stop()


async def test_cfg_waits_for_in_flight_tx():
    """전파를 쏘는 도중 무선 설정이 바뀌면 안 된다 — cfg 는 응답이 없어도 송신이 끝날 때까지 기다린다."""
    m = FakeModem(latency_ms=60)
    m.add_node(ord("E"), 301, 1, sched_ver=2)
    c = ModemClient(m)
    await c.start()
    try:
        tx = asyncio.create_task(c.tx(F, wake=True, ack_ms=50))
        await asyncio.sleep(0.01)
        await c.cfg(sf=10)
        await tx
        order = [(who, msg.get("op")) for who, msg in m.log if msg.get("op") in ("cfg", "tx_done")]
        assert order == [("modem", "tx_done"), ("host", "cfg")]
    finally:
        await c.stop()


async def test_malformed_modem_lines_do_not_kill_the_reader(client):
    """_on_message 안의 KeyError·ValueError·AttributeError 가 읽기 루프를 끝내면 그 뒤 모든 요청이
    타임아웃된다. 한 줄 버리고 계속 읽는다(#35 리뷰 6)."""
    m = client._t
    for raw in ('{"op":"rx"}', '{"op":"rx","rssi":-1,"snr":1,"frame":"zz"}', "[1, 2]", '"x"'):
        m._out.put_nowait(raw)
    assert await asyncio.wait_for(client.ping(), 2) > 0

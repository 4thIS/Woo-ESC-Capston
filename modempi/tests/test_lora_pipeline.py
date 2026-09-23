import asyncio
import json

import pytest
from lora_proto import codec as C
from lora_proto import proto as P

from modempi.lora.fake_modem import FakeModem
from modempi.lora.pipeline import PRUNE_EVERY_S, PRUNE_KEEP_S, Pipeline, radio_to_cfg
from modempi.store import SqliteStore

from .conftest import FakeClock

pytestmark = pytest.mark.anyio

SLOT = {
    "day": 1,
    "s_h": 9,
    "s_m": 0,
    "e_h": 9,
    "e_m": 50,
    "type": 1,
    "subject": "자료구조",
    "professor": "김교수",
}


def hub_config(**radio) -> dict:
    """메인Pi 허브 `config_msg` 가 보내는 모양 그대로(server/app/lora_service/hub.py)."""
    r = P.RADIO
    return {
        "net_id": P.NET_ID,
        "radio": {
            "sf": r["RP_SF"],
            "bw": r["RP_BW_KHZ"],
            "cr": r["RP_CR"],
            "tx_dbm": r["RP_TX_POWER_DBM"],
            "preamble_wake_ms": r["RP_PREAMBLE_WAKE_MS"],
            **radio,
        },
        "nodes": [{"bld": "E", "room": 301, "unit": 1}],
        "status_hour_utc": 18,
    }


def put_slot(db, job_id="10", *, new_ver=3):
    db.put_job(
        job_id=job_id,
        bld="E",
        room=301,
        unit=1,
        type="SLOT_SET",
        payload=json.dumps(SLOT),
        priority=3,
        new_ver=new_ver,
    )


async def test_job_goes_out_and_result_lands_in_store():
    db = SqliteStore(":memory:")
    modem = FakeModem()
    modem.add_node(ord("E"), 301, 1, sched_ver=2)
    db.set_config(hub_config())
    put_slot(db)
    stop = asyncio.Event()
    task = asyncio.create_task(Pipeline(db, modem).run(stop))
    for _ in range(100):
        await asyncio.sleep(0.02)
        if db.get_job("10").state == "acked":
            break
    stop.set()
    await asyncio.wait_for(task, 3)
    assert db.get_job("10").state == "acked"
    assert db.get_meta("modem_fw") == "gw-2.0.0"
    db.close()


async def test_waits_for_config_then_sends_cfg_and_resends_on_change():
    db = SqliteStore(":memory:")
    modem = FakeModem()
    modem.add_node(ord("E"), 301, 1)
    put_slot(db)  # 작업이 있어도 config 전엔 보내지 않는다
    stop = asyncio.Event()
    task = asyncio.create_task(Pipeline(db, modem).run(stop))
    await asyncio.sleep(0.05)
    assert modem.cfg_count == 0  # config 없으면 cfg 를 안 보낸다
    assert modem.stats["tx"] == 0
    db.set_config(hub_config())
    await asyncio.sleep(0.05)
    assert modem.cfg_count == 1
    # 모뎀이 받은 것은 계약 ⑥ 이름(tx_dbm·preamble_wake_ms)이 아니라 v2 §4.2 이름이어야 한다
    assert modem.radio == {
        "sf": P.RADIO["RP_SF"],
        "bw": P.RADIO["RP_BW_KHZ"],
        "cr": P.RADIO["RP_CR"],
        "power": P.RADIO["RP_TX_POWER_DBM"],
        "freq": P.RADIO["RP_FREQ_MHZ"],
        "wake_ms": P.RADIO["RP_PREAMBLE_WAKE_MS"],
    }
    db.set_config(hub_config(sf=10))
    await asyncio.sleep(0.05)
    assert modem.cfg_count == 2 and modem.radio["sf"] == 10
    cfg = hub_config(sf=10)
    cfg["nodes"] = []
    db.set_config(cfg)  # 무선 설정은 그대로 — 라디오를 다시 잡지 않는다
    await asyncio.sleep(0.05)
    assert modem.cfg_count == 2
    stop.set()
    await asyncio.wait_for(task, 3)
    db.close()


def test_radio_to_cfg_maps_contract6_names_to_modem_serial_names():
    """허브 `config_msg` 의 radio 를 v2 §4.2 `cfg` 로 — freq 는 config 에 없어 lora_proto 에서."""
    assert radio_to_cfg(hub_config()["radio"]) == {
        "sf": P.RADIO["RP_SF"],
        "bw": P.RADIO["RP_BW_KHZ"],
        "cr": P.RADIO["RP_CR"],
        "power": P.RADIO["RP_TX_POWER_DBM"],
        "freq": P.RADIO["RP_FREQ_MHZ"],
        "wake_ms": P.RADIO["RP_PREAMBLE_WAKE_MS"],
    }


def test_radio_to_cfg_rejects_partial_radio():
    radio = hub_config()["radio"]
    del radio["tx_dbm"]
    with pytest.raises(KeyError):
        radio_to_cfg(radio)


def host_ops(modem, op: str) -> list[dict]:
    return [m for who, m in modem.log if who == "host" and m.get("op") == op]


async def test_watchdog_ping_does_not_collide_with_tx():
    """v2 §4.5 핑(10 s)이 송신과 겹쳐도 RuntimeError 로 파이프라인이 죽으면 안 된다."""
    db = SqliteStore(":memory:")
    modem = FakeModem(latency_ms=30)
    modem.add_node(ord("E"), 301, 1, sched_ver=2)
    db.set_config(hub_config())
    for i in range(5):
        put_slot(db, str(10 + i), new_ver=3 + i)
    stop = asyncio.Event()
    clk = FakeClock()  # sleep 은 한 틱만 양보 — 10 s 핑이 5 ms 마다 돈다
    task = asyncio.create_task(Pipeline(db, modem, clock=clk, sleep=clk.sleep).run(stop))
    await asyncio.sleep(0.3)
    stop.set()
    await asyncio.wait_for(task, 3)  # 자식이 예외로 죽었으면 여기서 올라온다
    assert host_ops(modem, "ping") and host_ops(modem, "tx")
    db.close()


class ClosingSpy:
    """FakeModem 을 감싸 close 가 불렸는지 본다."""

    def __init__(self, modem: FakeModem):
        self.modem, self.closed = modem, False

    async def write_line(self, line: str) -> None:
        await self.modem.write_line(line)

    async def read_line(self) -> str:
        return await self.modem.read_line()

    async def close(self) -> None:
        self.closed = True
        await self.modem.close()


@pytest.mark.parametrize("with_config", [True, False], ids=["running", "waiting_config"])
async def test_stop_returns_promptly_and_closes_modem(with_config):
    """자식 run() 은 1 시간 sleep·rx 대기 중에 stop 을 못 본다 — 파이프라인이 cancel 해야 한다."""
    db = SqliteStore(":memory:")
    modem = FakeModem(latency_ms=200)
    modem.add_node(ord("E"), 301, 1, sched_ver=2)
    if with_config:
        db.set_config(hub_config())
        put_slot(db)  # 송신 중에 멈춘다
    spy = ClosingSpy(modem)
    stop = asyncio.Event()
    task = asyncio.create_task(Pipeline(db, spy).run(stop))
    await asyncio.sleep(0.1)
    stop.set()
    await asyncio.wait_for(task, 1)
    assert spy.closed
    db.close()


OTHER_NET = (P.NET_ID + 1) % 256  # 메인Pi 가 이 학교에 배정한 NET_ID — lora_proto 기본값과 다르다


def status_frame(net_id: int) -> bytes:
    ack = C.Ack(P.AckStatus.OK, 0, 3900, 2, 1, 0, 1, 20, int(P.Layout.CLASS))
    h = C.Header(type=P.Type.STATUS, bld=ord("E"), room=301, unit=1, txn=0, net_id=net_id)
    return C.encode_frame(h, C.encode_payload(C.Status(ack, -90, 20, 0, 42)))


async def test_net_id_comes_from_config_for_downlink_and_uplink():
    db = SqliteStore(":memory:")
    modem = FakeModem(net_id=OTHER_NET)  # 가상 노드는 이 NET_ID 프레임만 받는다
    modem.add_node(ord("E"), 301, 1, sched_ver=2)
    db.set_config({**hub_config(), "net_id": OTHER_NET})
    put_slot(db)
    stop = asyncio.Event()
    task = asyncio.create_task(Pipeline(db, modem).run(stop))
    for _ in range(100):
        await asyncio.sleep(0.02)
        if db.get_job("10").state != "received":
            break
    modem.inject_uplink(status_frame(P.NET_ID), rssi=-111)  # 다른 망 — 버린다
    modem.inject_uplink(status_frame(OTHER_NET), rssi=-77)
    for _ in range(50):
        await asyncio.sleep(0.02)
        if db.pending_uplinks():
            break
    stop.set()
    await asyncio.wait_for(task, 3)
    assert db.get_job("10").state == "acked"
    [row] = db.pending_uplinks()
    assert (row.body["kind"], row.body["rssi"]) == ("STATUS", -77)
    db.close()


async def test_prunes_at_start_and_daily(monkeypatch):
    """하루를 못 넘기고 재기동되는 Pi 도 정리되게 기동 때 한 번, 이후 하루마다 7 일 지난 행을 지운다."""
    db = SqliteStore(":memory:")
    modem = FakeModem()
    db.set_config(hub_config())
    calls: list[float] = []
    monkeypatch.setattr(db, "prune", lambda *, older_than: calls.append(older_than) or 0)
    slept: list[float] = []

    async def sleep(s: float) -> None:
        slept.append(s)
        if s == PRUNE_EVERY_S:
            await asyncio.Event().wait()  # 하루는 오지 않는다 — 기동 직후 정리만 본다
        await asyncio.sleep(0.005)

    stop = asyncio.Event()
    task = asyncio.create_task(Pipeline(db, modem, sleep=sleep).run(stop))
    await asyncio.sleep(0.05)
    stop.set()
    await asyncio.wait_for(task, 3)
    assert calls == [PRUNE_KEEP_S] and PRUNE_EVERY_S in slept
    db.close()

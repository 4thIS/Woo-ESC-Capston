import asyncio
import json

import pytest
import websockets
from lora_proto import proto as P

from modempi.link.client import LinkClient

from .conftest import FakeHub

pytestmark = pytest.mark.anyio

JOB = {
    "job_id": 5,
    "bld": "E",
    "room": 301,
    "unit": 1,
    "type": "SLOT_SET",
    "payload": {
        "day": 1,
        "s_h": 9,
        "s_m": 0,
        "e_h": 10,
        "e_m": 0,
        "type": 1,
        "subject": "a",
        "professor": "b",
    },
    "priority": 3,
    "new_ver": 1,
}


async def _run(store, hub, **kw):
    c = LinkClient(store, url=hub.url, modem_id="m1", token="secret", agent_ver="0.1", **kw)
    task = asyncio.create_task(c.run())
    await asyncio.wait_for(c.connected.wait(), 3)
    return c, task


async def _stop(c, task):
    await c.stop()
    await asyncio.wait_for(task, 3)


async def test_hello_then_config_stored(store, fake_hub):
    c, task = await _run(store, fake_hub)
    hello = await fake_hub.wait_for("hello")
    assert hello["modem_id"] == "m1" and hello["token"] == "secret"
    assert hello["agent_ver"] == "0.1" and hello["modem_fw"] == "unknown"
    assert hello["pending_results"] == 0
    assert store.config["net_id"] == 0x4B and c.state == "CONNECTED"
    await _stop(c, task)
    assert c.state == "DISCONNECTED"


async def test_job_stored_and_accepted_dup_ignored(store, fake_hub):
    fake_hub.jobs = [JOB, JOB]  # 같은 job_id 두 번 (서버 안전망 재송 흉내)
    c, task = await _run(store, fake_hub)
    await fake_hub.wait_for("job_accepted")
    await asyncio.sleep(0.1)
    accepted = [m for m in fake_hub.received if m["t"] == "job_accepted"]
    assert [m["job_id"] for m in accepted] == [5, 5]  # 둘 다 회신 (int)
    assert list(store.jobs) == ["5"]  # 한 번만 저장 (str)
    j = store.jobs["5"]
    assert j["type"] == "SLOT_SET" and j["priority"] == 3 and j["new_ver"] == 1
    assert json.loads(j["payload"])["subject"] == "a"  # 검증 없이 문자열로
    await _stop(c, task)


async def test_time_now_puts_time_row_uploaded(store, fake_hub):
    c, task = await _run(store, fake_hub)
    await fake_hub.send({"t": "time_now", "request_status": True})
    await fake_hub.send({"t": "ping"})
    await fake_hub.wait_for("pong")
    rows = [j for j in store.jobs.values() if j["type"] == "TIME"]
    assert len(rows) == 1 and rows[0]["uploaded"] == 1 and rows[0]["priority"] == 0
    p = json.loads(rows[0]["payload"])
    assert p["flags"] & P.TimeFlag.REQUEST_STATUS and isinstance(p["epoch"], int)
    await _stop(c, task)


async def test_cancel_and_unknown_and_garbage_keep_connection(store, fake_hub):
    fake_hub.jobs = [JOB]
    c, task = await _run(store, fake_hub)
    await fake_hub.wait_for("job_accepted")
    await fake_hub.send({"t": "cancel", "job_id": 5})
    await fake_hub.send({"t": "cancel", "job_id": 999})
    await fake_hub.send({"t": "whatever"})
    await fake_hub._conn.send("not json")
    await fake_hub.send({"t": "job"})  # job_id 없음 → 핸들러에서 KeyError, 연결은 유지
    await fake_hub.send({"t": "ping"})
    await fake_hub.wait_for("pong")
    accepted = [m for m in fake_hub.received if m["t"] == "job_accepted"]
    assert [m["job_id"] for m in accepted] == [5]  # 진짜 JOB 한 건만
    assert store.jobs["5"]["state"] == "cancelled" and c.state == "CONNECTED"
    await _stop(c, task)


async def test_non_json_first_frame_is_protocol_error_and_run_survives(store):
    # 허브가 config 대신 쓰레기를 먼저 보내면 세션은 실패하지만 run() 은 살아서 재시도한다.
    # serve() 가 시작 시점에 FakeHub._handle 을 바운드 메서드로 캡처해 버려서, 이미 떠 있는
    # fake_hub 인스턴스에 사후 패치해서는 새 접속에 반영되지 않는다 (검증 완료) — 그래서 여기서는
    # _handle 을 미리 바꿔치기한 새 FakeHub 를 만들어 start() 한다.
    hub = FakeHub(token="secret")

    async def bad_handle(conn):
        await conn.recv()  # hello
        await conn.send("not json")
        await conn.close()

    hub._handle = bad_handle
    await hub.start()
    try:
        c = LinkClient(store, url=hub.url, modem_id="m1", token="secret")
        task = asyncio.create_task(c.run())
        await asyncio.sleep(0.3)
        assert not task.done() and c.attempts >= 1 and c.state != "CONNECTED"
        await c.stop()
        await asyncio.wait_for(task, 3)
    finally:
        await hub.stop()


async def test_stop_during_backoff_exits_promptly(store, monkeypatch):
    # 실제 접속 거부 대신 monkeypatch — Windows 루프백 ECONNREFUSED 의 ~2 s 지연을 피한다.
    # 이 테스트가 검증하려는 건 connect 실패 사유가 아니라, 백오프 대기 중 stop() 이
    # 즉시 먹히는지다.
    def _refuse(*a, **k):
        raise ConnectionRefusedError

    monkeypatch.setattr(websockets, "connect", _refuse)
    c = LinkClient(store, url="ws://127.0.0.1:9/ws/modem", modem_id="m1", token="x", backoff_max=30)
    task = asyncio.create_task(c.run())

    async def _entered_backoff() -> None:
        while c.state != "DISCONNECTED" or c.attempts < 1:
            await asyncio.sleep(0.01)

    await asyncio.wait_for(_entered_backoff(), 5)
    t0 = asyncio.get_running_loop().time()
    await c.stop()
    await asyncio.wait_for(task, 3)
    assert asyncio.get_running_loop().time() - t0 < 0.5

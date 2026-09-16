import asyncio
import json

import pytest
from lora_proto import proto as P

from modempi.link.client import LinkClient

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
    await fake_hub.send({"t": "ping"})
    await fake_hub.wait_for("pong")
    assert store.jobs["5"]["state"] == "cancelled" and c.state == "CONNECTED"
    await _stop(c, task)

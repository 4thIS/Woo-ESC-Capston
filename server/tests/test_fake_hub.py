import asyncio
import json

import pytest
import websockets

from tests.fake_hub import FakeHub

JOB = {
    "job_id": 1,
    "bld": "E",
    "room": 302,
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


@pytest.mark.anyio
async def test_fake_hub_roundtrip():
    hub = FakeHub(token="secret", jobs=[JOB])
    await hub.start()
    try:
        async with websockets.connect(hub.url) as ws:
            await ws.send(
                json.dumps(
                    {
                        "t": "hello",
                        "modem_id": "m1",
                        "token": "secret",
                        "agent_ver": "0",
                        "modem_fw": "0",
                        "pending_results": 0,
                    }
                )
            )
            cfg = json.loads(await ws.recv())
            assert cfg["t"] == "config" and cfg["nodes"] == [{"bld": "E", "room": 302, "unit": 1}]
            job = json.loads(await ws.recv())
            assert job["t"] == "job" and job["job_id"] == 1
            await ws.send(json.dumps({"t": "job_accepted", "job_id": 1}))
            await ws.send(json.dumps({"t": "ping"}))
            assert json.loads(await ws.recv()) == {"t": "pong"}
            got = await hub.wait_for("job_accepted")
            assert got["job_id"] == 1
            await hub.send({"t": "cancel", "job_id": 1})
            assert json.loads(await ws.recv()) == {"t": "cancel", "job_id": 1}
    finally:
        await hub.stop()


@pytest.mark.anyio
async def test_fake_hub_rejects_bad_token():
    hub = FakeHub(token="secret")
    await hub.start()
    try:
        async with websockets.connect(hub.url) as ws:
            await ws.send(
                json.dumps(
                    {
                        "t": "hello",
                        "modem_id": "m1",
                        "token": "no",
                        "agent_ver": "0",
                        "modem_fw": "0",
                        "pending_results": 0,
                    }
                )
            )
            with pytest.raises(websockets.ConnectionClosed):
                await asyncio.wait_for(ws.recv(), 2)
    finally:
        await hub.stop()


@pytest.mark.anyio
async def test_fake_hub_tolerates_garbage_first_frame():
    hub = FakeHub(token="secret")
    await hub.start()
    try:
        async with websockets.connect(hub.url) as ws:
            await ws.send("not json")
            with pytest.raises(websockets.ConnectionClosed):
                await asyncio.wait_for(ws.recv(), 2)
        async with websockets.connect(hub.url) as ws:
            pass  # 아무것도 안 보내고 끊음 — 서버가 조용히 넘어간다
        async with websockets.connect(hub.url) as ws:  # 이후 정상 접속 여전히 됨
            await ws.send(
                json.dumps(
                    {
                        "t": "hello",
                        "modem_id": "m1",
                        "token": "secret",
                        "agent_ver": "0",
                        "modem_fw": "0",
                        "pending_results": 0,
                    }
                )
            )
            assert json.loads(await ws.recv())["t"] == "config"
    finally:
        await hub.stop()

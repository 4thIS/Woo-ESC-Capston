"""계약 ⑥ 형태만 말하는 최소 WS 서버. DB 없음. modempi/link(S5) 테스트가 재사용한다 (spec §4.5).

시그니처는 additive 로만 바꾼다.
"""

from __future__ import annotations

import asyncio
import json

import websockets
from websockets.asyncio.server import Server, ServerConnection, serve

DEFAULT_CONFIG = {
    "net_id": 0x4B,
    "radio": {"sf": 9, "bw": 125.0, "cr": 5, "tx_dbm": 14, "preamble_wake_ms": 3000},
    "nodes": [{"bld": "E", "room": 302, "unit": 1}],
    "qr_base_url": "",
    "status_hour_utc": 18,
}


class FakeHub:
    def __init__(self, token: str, jobs: list[dict] | None = None, config: dict | None = None):
        self.token = token
        self.jobs = list(jobs or [])
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        self.received: list[dict] = []
        self._server: Server | None = None
        self._conn: ServerConnection | None = None
        self._event = asyncio.Event()
        self.url = ""

    async def start(self) -> int:
        self._server = await serve(self._handle, "127.0.0.1", 0)
        port = self._server.sockets[0].getsockname()[1]
        self.url = f"ws://127.0.0.1:{port}/ws/modem"
        return port

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def send(self, msg: dict) -> None:
        assert self._conn is not None, "링크가 아직 안 붙음"
        await self._conn.send(json.dumps(msg))

    async def wait_for(self, t: str, timeout: float = 2.0) -> dict:
        async with asyncio.timeout(timeout):
            while True:
                # received 가 진실원이고, _event 는 재확인을 깨우는 용도일 뿐이다.
                for m in self.received:
                    if m.get("t") == t:
                        return m
                self._event.clear()
                await self._event.wait()

    async def _handle(self, conn: ServerConnection) -> None:
        try:
            hello = json.loads(await conn.recv())
        except (websockets.ConnectionClosed, json.JSONDecodeError, TypeError):
            return
        self.received.append(hello)
        self._event.set()
        if (
            not isinstance(hello, dict)
            or hello.get("t") != "hello"
            or hello.get("token") != self.token
        ):
            await conn.close(4001)
            return
        self._conn = conn
        await conn.send(json.dumps({"t": "config", **self.config}))
        for job in self.jobs:
            await conn.send(json.dumps({"t": "job", **job}))
        try:
            async for raw in conn:
                msg = json.loads(raw)
                self.received.append(msg)
                self._event.set()
                if msg.get("t") == "ping":
                    await conn.send(json.dumps({"t": "pong"}))
        except websockets.ConnectionClosed:
            pass
        finally:
            if self._conn is conn:
                self._conn = None

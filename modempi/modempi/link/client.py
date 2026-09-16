"""계약 ⑥ 소비 측 WS 클라이언트 (S5 spec §2.1·§2.2). 파이프라인과는 JobStore 로만 만난다."""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from typing import Literal

import websockets
from lora_proto import proto as P
from websockets.asyncio.client import ClientConnection

from modempi.link.store_port import JobStore

log = logging.getLogger("link")

State = Literal["DISCONNECTED", "CONNECTING", "CONNECTED"]


class AuthError(Exception):
    """서버가 4001 로 닫음 — 토큰 불일치."""


class ProtocolError(Exception):
    """hello 뒤 config 가 안 옴."""


class LinkClient:
    def __init__(
        self,
        store: JobStore,
        *,
        url: str,
        modem_id: str,
        token: str,
        agent_ver: str = "0.0.0",
        modem_fw: str = "unknown",
        clock=time.time,
        sleep=asyncio.sleep,
        upload_interval: float = 1.0,
        silence_timeout: float = 60.0,
        config_timeout: float = 10.0,
        backoff_max: float = 30.0,
    ):
        self.store = store
        self.url, self.modem_id, self._token = url, modem_id, token
        self.agent_ver, self.modem_fw = agent_ver, modem_fw
        self._clock, self._sleep = clock, sleep
        self.upload_interval, self.silence_timeout = upload_interval, silence_timeout
        self.config_timeout, self.backoff_max = config_timeout, backoff_max
        self.state: State = "DISCONNECTED"
        self.connected = asyncio.Event()
        self.backoff = 1.0
        self.attempts = 0
        self._stop = asyncio.Event()
        self._ws: ClientConnection | None = None
        self._last_rx = 0.0

    # ---- 수명 ----
    async def run(self) -> None:
        while not self._stop.is_set():
            self.state = "CONNECTING"
            self.attempts += 1
            try:
                await self._session()
            except AuthError:
                log.error(
                    "modem %s: 토큰 불일치(4001) — %.0f s 뒤 재시도",
                    self.modem_id,
                    self.backoff_max,
                )
                self.backoff = self.backoff_max
            except (
                OSError,
                ProtocolError,
                websockets.exceptions.WebSocketException,
                TimeoutError,
            ) as e:
                log.warning("modem %s: 연결 종료 %s", self.modem_id, e)
            finally:
                self.state = "DISCONNECTED"
                self.connected.clear()
                self._ws = None
            if self._stop.is_set():
                break
            await self._sleep(self.backoff * random.uniform(0.8, 1.2))
            self.backoff = min(self.backoff * 2, self.backoff_max)

    async def stop(self) -> None:
        self._stop.set()
        if self._ws is not None:
            await self._ws.close()

    # ---- 세션 1회 ----
    def _hello(self) -> dict:
        return {
            "t": "hello",
            "modem_id": self.modem_id,
            "token": self._token,
            "agent_ver": self.agent_ver,
            "modem_fw": self.modem_fw,
            "pending_results": len(self.store.pending_results()),
        }

    async def _session(self) -> None:
        async with websockets.connect(self.url) as ws:
            self._ws = ws
            hello = self._hello()
            log.info(
                "modem %s: hello (pending_results=%s)", self.modem_id, hello["pending_results"]
            )
            await ws.send(json.dumps(hello))
            try:
                first = json.loads(await asyncio.wait_for(ws.recv(), self.config_timeout))
            except websockets.exceptions.ConnectionClosed as e:
                if e.rcvd is not None and e.rcvd.code == 4001:
                    raise AuthError from e
                raise
            if not isinstance(first, dict) or first.get("t") != "config":
                raise ProtocolError(f"config 대신 {first!r}")
            self._on_message(first)
            self.state = "CONNECTED"
            self.backoff = 1.0
            self._last_rx = self._clock()
            self.connected.set()
            await self._recv_loop(ws)

    async def _recv_loop(self, ws: ClientConnection) -> None:
        async for raw in ws:
            self._last_rx = self._clock()
            try:
                msg = json.loads(raw)
            except ValueError:
                log.warning("modem %s: JSON 아님, 무시", self.modem_id)
                continue
            if not isinstance(msg, dict):
                continue
            try:
                reply = self._on_message(msg)
            except Exception:
                log.exception("modem %s: %s 처리 실패", self.modem_id, msg.get("t"))
                continue
            if reply is not None:
                await ws.send(json.dumps(reply))

    # ---- 메시지 → store ----
    def _on_message(self, msg: dict) -> dict | None:
        t = msg.get("t")
        if t == "config":
            self.store.set_config(msg)
        elif t == "job":
            job_id = int(msg["job_id"])
            self.store.put_job(
                job_id=str(job_id),
                bld=msg["bld"],
                room=int(msg["room"]),
                unit=int(msg["unit"]),
                type=msg["type"],
                payload=json.dumps(msg["payload"], ensure_ascii=False),
                priority=int(msg.get("priority", 5)),
                new_ver=msg.get("new_ver"),
            )
            return {"t": "job_accepted", "job_id": job_id}  # 중복이어도 회신 (멱등)
        elif t == "cancel":
            self.store.cancel_job(str(int(msg["job_id"])))
        elif t == "time_now":
            epoch = int(self._clock())
            flags = int(P.TimeFlag.REQUEST_STATUS) if msg.get("request_status") else 0
            self.store.put_job(
                job_id=f"time-{epoch}",
                bld="",
                room=0,
                unit=0,
                type="TIME",
                payload=json.dumps({"epoch": epoch, "flags": flags}),
                priority=0,
                new_ver=None,
                uploaded=1,  # 메인은 TIME 결과에 관심 없음 (S6 §4.4)
            )
        elif t == "ping":
            return {"t": "pong"}
        elif t == "pong":
            pass
        else:
            log.warning("modem %s: 모르는 t=%r 무시", self.modem_id, t)
        return None

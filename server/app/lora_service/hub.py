"""계약 ⑥ WS 허브 (spec §2.4·§2.5). 상태 전이 queued→dispatched 는 여기, acked|failed 는 api.on_job_result."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime

from fastapi import WebSocket, WebSocketDisconnect
from lora_proto import proto as P
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db import utcnow
from app.lora_service import api
from app.lora_service.models import LoraLog, Outbox
from app.settings import Settings

log = logging.getLogger("hub")
HELLO_TIMEOUT_S = 10
PING_INTERVAL_S = 30


def _json_default(o):
    if isinstance(o, datetime):
        return o.isoformat()
    raise TypeError(type(o).__name__)


class Hub:
    def __init__(self, session_factory: sessionmaker, settings: Settings):
        self._Session = session_factory
        self._settings = settings
        self._loop: asyncio.AbstractEventLoop | None = None
        self.connected: dict[str, WebSocket] = {}
        self._missed: dict[str, int] = {}

    # ---- 수명 ----
    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def stop(self) -> None:
        for mid, ws in list(self.connected.items()):
            try:
                await ws.close()
            except (RuntimeError, WebSocketDisconnect):
                pass
            api.touch_modem(mid, connected=False)
        self.connected.clear()

    # ---- HubPort (api 가 부른다. 웹 스레드 또는 루프 스레드 어디서든) ----
    def _spawn(self, coro) -> None:
        if self._loop is None:
            coro.close()
            return
        self._loop.call_soon_threadsafe(lambda: asyncio.ensure_future(coro))

    def notify(self, modem_id: str) -> None:
        self._spawn(self.flush(modem_id))

    def config_changed(self, modem_id: str) -> None:
        self._spawn(self.send_config(modem_id))

    def time_now(self) -> int:
        for mid in list(self.connected):
            self._spawn(self._send(mid, {"t": "time_now", "request_status": False}))
        return len(self.connected)

    def cancel(self, modem_id: str, job_id: int) -> None:
        self._spawn(self._send(modem_id, {"t": "cancel", "job_id": job_id}))

    # ---- 메시지 ----
    def config_msg(self, modem_id: str) -> dict:
        r = P.RADIO
        return {
            "t": "config",
            "net_id": api._topology.net_id(modem_id),
            "radio": {
                "sf": r["RP_SF"],
                "bw": r["RP_BW_KHZ"],
                "cr": r["RP_CR"],
                "tx_dbm": r["RP_TX_POWER_DBM"],
                "preamble_wake_ms": r["RP_PREAMBLE_WAKE_MS"],
            },
            "nodes": [
                {"bld": b, "room": rm, "unit": u} for b, rm, u in api._topology.nodes(modem_id)
            ],
            "qr_base_url": self._settings.qr_base_url,
            "status_hour_utc": self._settings.status_hour_utc,
        }

    @staticmethod
    def job_msg(row: Outbox) -> dict:
        return {
            "t": "job",
            "job_id": row.id,
            "bld": row.bld,
            "room": row.room,
            "unit": row.unit,
            "type": row.type,
            "payload": json.loads(row.payload),
            "priority": row.priority,
            "new_ver": row.new_ver,
        }

    def _log(self, modem_id: str, direction: str, msg: dict) -> None:
        with self._Session() as s, s.begin():
            s.add(
                LoraLog(
                    at=utcnow(),
                    modem_id=modem_id,
                    dir=direction,
                    t=msg.get("t", "?"),
                    body=json.dumps(msg, ensure_ascii=False, default=_json_default),
                )
            )

    async def _send(self, modem_id: str, msg: dict) -> bool:
        ws = self.connected.get(modem_id)
        if ws is None:
            return False
        try:
            await ws.send_json(msg)
        except (WebSocketDisconnect, RuntimeError):
            return False
        self._log(modem_id, "tx", msg)
        return True

    async def send_config(self, modem_id: str) -> None:
        await self._send(modem_id, self.config_msg(modem_id))

    async def flush(self, modem_id: str) -> None:
        """그 모뎀의 queued 전부를 job 으로. 송신은 상태를 바꾸지 않는다 — job_accepted 가 바꾼다."""
        if modem_id not in self.connected:
            return
        with self._Session() as s:
            rows = s.scalars(
                select(Outbox)
                .where(Outbox.modem_id == modem_id, Outbox.state == "queued")
                .order_by(Outbox.priority, Outbox.id)
            ).all()
        for row in rows:
            if not await self._send(modem_id, self.job_msg(row)):
                return

    # ---- 수신 ----
    def _on_message(self, modem_id: str, msg: dict) -> dict | None:
        """수신 1건 처리. 답장할 게 있으면 dict. ponytail: 동기 DB 호출을 루프에서 직접 — SQLite ms 단위."""
        t = msg.get("t")
        if t == "job_accepted":
            with self._Session() as s, s.begin():
                row = s.get(Outbox, msg["job_id"])
                if row is not None and row.state == "queued":
                    row.state, row.dispatched_at = "dispatched", utcnow()
        elif t == "job_result":
            api.on_job_result(modem_id, msg)
        elif t == "uplink":
            api.on_uplink(modem_id, msg)
        elif t == "ping":
            return {"t": "pong"}
        elif t == "pong":
            pass
        else:
            log.warning("modem %s: 모르는 t=%r 무시", modem_id, t)
        return None

    async def _pinger(self, modem_id: str, ws: WebSocket) -> None:
        self._missed[modem_id] = 0
        while True:
            await asyncio.sleep(PING_INTERVAL_S)
            if self._missed.get(modem_id, 0) >= 2:
                await ws.close(code=1001)  # pong 2회 무응답 (로드맵 §4.2)
                return
            if not await self._send(modem_id, {"t": "ping"}):
                return
            self._missed[modem_id] = self._missed.get(modem_id, 0) + 1

    async def handle(self, ws: WebSocket) -> None:
        await ws.accept()
        try:
            hello = await asyncio.wait_for(ws.receive_json(), HELLO_TIMEOUT_S)
        except (TimeoutError, WebSocketDisconnect, ValueError):
            await ws.close(code=4000)
            return
        modem_id = hello.get("modem_id", "")
        if hello.get("t") != "hello" or not api.verify_token(modem_id, hello.get("token", "")):
            await ws.close(code=4001)
            return
        old = self.connected.pop(modem_id, None)
        if old is not None:
            try:
                await old.close(code=1000)
            except (RuntimeError, WebSocketDisconnect):
                pass
        self.connected[modem_id] = ws
        pinger = asyncio.ensure_future(self._pinger(modem_id, ws))
        try:
            api.touch_modem(
                modem_id,
                connected=True,
                agent_ver=hello.get("agent_ver"),
                modem_fw=hello.get("modem_fw"),
            )
            self._log(modem_id, "rx", {**hello, "token": "***"})
            await self.send_config(modem_id)
            await self.flush(modem_id)
            while True:
                try:
                    msg = await ws.receive_json()
                except ValueError:
                    log.warning("modem %s: JSON 아님, 무시", modem_id)
                    continue
                if not isinstance(msg, dict):
                    log.warning("modem %s: dict 아님, 무시: %r", modem_id, msg)
                    continue
                self._log(modem_id, "rx", msg)
                if msg.get("t") == "pong":
                    self._missed[modem_id] = 0
                try:
                    reply = self._on_message(modem_id, msg)
                    if reply:
                        await self._send(modem_id, reply)
                except Exception:
                    log.exception("modem %s: %s 처리 실패", modem_id, msg.get("t"))
        except WebSocketDisconnect:
            pass
        finally:
            pinger.cancel()
            if self.connected.get(modem_id) is ws:
                del self.connected[modem_id]
                api.touch_modem(modem_id, connected=False)

    # ---- 안전망 ----
    async def sweep_loop(self, interval_s: float) -> None:
        while True:
            await asyncio.sleep(interval_s)
            try:
                for mid in list(self.connected):
                    await self.flush(mid)
                api.sweep_offline()
            except Exception:
                log.exception("sweep 실패")

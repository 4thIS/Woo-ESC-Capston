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


def _log_task_exc(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        log.error("spawned task 실패", exc_info=exc)


class Hub:
    def __init__(self, session_factory: sessionmaker, settings: Settings):
        self._Session = session_factory
        self._settings = settings
        self._loop: asyncio.AbstractEventLoop | None = None
        self.connected: dict[str, WebSocket] = {}
        self._missed: dict[str, int] = {}
        self._sent: dict[str, set[int]] = {}

    # ---- 수명 ----
    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def stop(self) -> None:
        for mid, ws in list(self.connected.items()):
            try:
                await ws.close()
            except (RuntimeError, WebSocketDisconnect):
                pass
            await asyncio.to_thread(api.touch_modem, mid, connected=False)
        self.connected.clear()

    # ---- HubPort (api 가 부른다. 웹 스레드 또는 루프 스레드 어디서든) ----
    def _spawn(self, coro) -> None:
        if self._loop is None:
            coro.close()
            return

        def _start():
            asyncio.ensure_future(coro).add_done_callback(_log_task_exc)

        self._loop.call_soon_threadsafe(_start)

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
        topo = api.get_topology()
        return {
            "t": "config",
            "net_id": topo.net_id(modem_id),
            "radio": {
                "sf": r["RP_SF"],
                "bw": r["RP_BW_KHZ"],
                "cr": r["RP_CR"],
                "tx_dbm": r["RP_TX_POWER_DBM"],
                "preamble_wake_ms": r["RP_PREAMBLE_WAKE_MS"],
            },
            "nodes": [{"bld": b, "room": rm, "unit": u} for b, rm, u in topo.nodes(modem_id)],
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
        await asyncio.to_thread(self._log, modem_id, "tx", msg)
        return True

    async def send_config(self, modem_id: str) -> None:
        await self._send(modem_id, await asyncio.to_thread(self.config_msg, modem_id))

    async def flush(self, modem_id: str) -> None:
        """그 모뎀의 queued 전부를 job 으로. 송신은 상태를 바꾸지 않는다 — job_accepted 가 바꾼다.
        순서는 outbox id(생성 순 = 같은 kind 안에서 버전 순) — priority 로 정렬하면 SLOT_SET(3) 이
        먼저 만든 FILE(5) 을 추월해 노드가 GAP 을 내고 옛 FILE 이 최신 편집을 덮는다(#28, 계약 ⑦ r6).
        우선순위는 모뎀Pi 가 노드끼리 고를 때만 쓴다."""
        if modem_id not in self.connected:
            return
        rows = await asyncio.to_thread(self._queued, modem_id)
        sent = self._sent.setdefault(modem_id, set())
        for row in rows:
            if row.id in sent:
                continue
            # 보내기 전에 표시 — _send 안의 await(기록) 사이에 끼어든 다른 flush 가 같은 job 을 또 보내지 않게
            sent.add(row.id)
            if not await self._send(modem_id, self.job_msg(row)):
                sent.discard(row.id)
                return

    def _queued(self, modem_id: str) -> list[Outbox]:
        with self._Session() as s:
            return list(
                s.scalars(
                    select(Outbox)
                    .where(Outbox.modem_id == modem_id, Outbox.state == "queued")
                    .order_by(Outbox.id)
                ).all()
            )

    # ---- 수신 ----
    def _on_message(self, modem_id: str, msg: dict) -> dict | None:
        """수신 1건 처리. 답장할 게 있으면 dict. 동기 DB 호출이라 루프 밖(asyncio.to_thread)에서 부른다 —
        다른 트랜잭션이 쓰기 잠금을 쥔 동안 루프 위에서 기다리면 루프 전체가 멈춘다(#43).
        루프 쪽 상태(_sent)는 여기서 만지지 않는다 — handle 이 루프에서 처리한다."""
        t = msg.get("t")
        if t == "job_accepted":
            job_id = int(msg["job_id"])  # 계약 ⑦: TEXT 로 echo 될 수 있음
            with self._Session() as s, s.begin():
                row = s.get(Outbox, job_id)
                if row is None:
                    return None
                if row.modem_id and row.modem_id != modem_id:
                    log.warning("modem %s: job %s 는 %s 소유, 무시", modem_id, row.id, row.modem_id)
                    return None
                if row.state == "queued":
                    row.state, row.dispatched_at = "dispatched", utcnow()
                elif row.state == "cancelled":  # M1: 취소 경합 — 이미 취소됐다고 알려준다
                    return {"t": "cancel", "job_id": row.id}
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
        if not isinstance(hello, dict) or hello.get("t") != "hello":
            await ws.close(code=4001)
            return
        modem_id, token = hello.get("modem_id"), hello.get("token")
        if not isinstance(modem_id, str) or not isinstance(token, str):
            await ws.close(code=4001)
            return
        if not await asyncio.to_thread(api.verify_token, modem_id, token):
            await ws.close(code=4001)
            return
        log.info(
            "modem %s: hello agent=%s fw=%s pending_results=%s",
            modem_id,
            hello.get("agent_ver"),
            hello.get("modem_fw"),
            hello.get("pending_results"),
        )
        old = self.connected.pop(modem_id, None)
        if old is not None:
            try:
                await old.close(code=1000)
            except (RuntimeError, WebSocketDisconnect):
                pass
        self.connected[modem_id] = ws
        self._sent[modem_id] = set()
        pinger = asyncio.ensure_future(self._pinger(modem_id, ws))
        try:
            await asyncio.to_thread(
                api.touch_modem,
                modem_id,
                connected=True,
                agent_ver=hello.get("agent_ver"),
                modem_fw=hello.get("modem_fw"),
            )
            await asyncio.to_thread(self._log, modem_id, "rx", {**hello, "token": "***"})
            await self.send_config(modem_id)
            await self.flush(modem_id)
            while True:
                try:
                    msg = await ws.receive_json()
                except ValueError:
                    log.warning("modem %s: JSON 아님, 무시", modem_id)
                    continue
                except RuntimeError:
                    # 같은 모뎀의 새 연결이 이 소켓을 닫았다(교체) — 기록을 기다리던 사이에 닫히면 수신이
                    # WebSocketDisconnect 가 아니라 '연결 안 됨'으로 끝난다. 조용히 끝낸다
                    break
                if not isinstance(msg, dict):
                    log.warning("modem %s: dict 아님, 무시: %r", modem_id, msg)
                    continue
                # 연결별 수신 루프가 한 건씩 await 하므로 메시지 처리 순서는 그대로다
                await asyncio.to_thread(self._log, modem_id, "rx", msg)
                if msg.get("t") == "pong":
                    self._missed[modem_id] = 0
                try:
                    if msg.get("t") == "job_accepted":  # 루프 쪽 상태는 루프에서
                        self._sent.get(modem_id, set()).discard(int(msg["job_id"]))
                    reply = await asyncio.to_thread(self._on_message, modem_id, msg)
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
                self._sent.pop(modem_id, None)
                # 연결 처리 작업이 취소돼도(종료·끊김) 끊김 기록은 끝까지 — shield 없이 await 하면 시작도 못 한다
                await asyncio.shield(asyncio.to_thread(api.touch_modem, modem_id, connected=False))

    # ---- 안전망 ----
    async def sweep_loop(self, interval_s: float) -> None:
        while True:
            await asyncio.sleep(interval_s)
            try:
                for mid in list(self.connected):
                    await self.flush(mid)
                await asyncio.to_thread(api.sweep_offline)
            except Exception:
                log.exception("sweep 실패")

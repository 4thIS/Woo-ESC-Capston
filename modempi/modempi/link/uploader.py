"""store 에 쌓인 결과·업링크를 1 s 주기로 메인Pi 에 올린다 (S5 spec §2.3)."""

from __future__ import annotations

import asyncio
import json
import logging

import websockets
from websockets.asyncio.client import ClientConnection

from modempi.link.store_port import JobRow, JobStore

log = logging.getLogger("link.upload")

_VER_KEYS = (
    ("sched_ver", "sched"),
    ("resv_ver", "resv"),
    ("exam_ver", "exam"),
    ("ident_ver", "ident"),
)


def build_job_result(row: JobRow) -> dict:
    try:
        vers = json.loads(row.node_vers) if row.node_vers else {}
    except ValueError:
        vers = {}  # node_vers 손상 — 버전 없이 보고 (M1)
    state, last_error = row.state, row.last_error
    if state == "cancelled":  # 계약 ⑥: 취소된 작업은 failed/cancelled 로 보고 (S2 §2.4)
        state, last_error = "failed", "cancelled"
    return {
        "t": "job_result",
        "job_id": int(row.job_id),
        "state": state,
        "ack_status": row.ack_status,
        "ack_detail": row.ack_detail,
        "attempts": row.attempts,
        "txn": row.txn,
        "rssi": row.rssi,
        "snr": row.snr,
        **{k: vers.get(v) for k, v in _VER_KEYS},
        "batt_mv": row.batt_mv,
        "layout": row.layout,
        "fw": row.fw,
        "last_error": last_error,
        "finished_at": int(row.finished_at) if row.finished_at is not None else None,
    }


class Uploader:
    def __init__(
        self, store: JobStore, *, interval: float = 1.0, sleep=asyncio.sleep, batch: int = 100
    ):
        self.store, self.interval, self._sleep, self.batch = store, interval, sleep, batch

    async def run(self, ws: ClientConnection, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self._sleep(self.interval)
            if stop.is_set():
                return
            try:
                await self.flush_once(ws)
            except websockets.exceptions.ConnectionClosed:
                raise  # 세션 종료 → 재접속·재송
            except Exception:
                log.exception("업로드 실패 — 다음 tick 에 재시도")

    async def flush_once(self, ws: ClientConnection) -> int:
        """job_result 먼저, uplink 다음. write 완료 즉시 mark — 실패하면 mark 안 하고 재접속 후 재송."""
        n = 0
        for row in self.store.pending_results(self.batch):
            try:
                msg = build_job_result(row)
            except (ValueError, TypeError):
                log.error("job_id %r 보고 불가 — 치움", row.job_id)
                self.store.mark_uploaded([row.job_id])
                continue
            await ws.send(json.dumps(msg))
            self.store.mark_uploaded([row.job_id])
            n += 1
        for up in self.store.pending_uplinks(self.batch):
            await ws.send(json.dumps({**up.body, "t": "uplink"}, ensure_ascii=False))
            self.store.mark_uplinks_uploaded([up.id])
            n += 1
        return n

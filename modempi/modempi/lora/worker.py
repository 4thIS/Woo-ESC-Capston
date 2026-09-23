"""JobStore 소비 루프 — v2 §8.4, 저장소만 계약 ⑦ (S6 spec §4.3)."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable

from lora_proto import codec as C
from lora_proto import proto as P

from modempi.lora.modem_client import ModemClient, TxResult
from modempi.lora.preprocess import PreprocessError, Unit, is_file_session, preprocess
from modempi.store import Job, SqliteStore

log = logging.getLogger("lora.worker")

RETRY_BACKOFF = (5.0, 20.0, 60.0)
MAX_ATTEMPTS = 3
STALE_TIME_S = 90.0  # 이보다 오래된 TIME 행은 보내지 않고 superseded 로 닫는다
BUSY_WAIT_S = 5.0
FILE_MISSING_MAX = 2

# 재시도 끝에 failed 로 닫을 때 앞 시도의 결과를 지운다 — 메인은 결과 필드를 그대로 복사한다(로드맵 §4.3).
_CLEAR = {
    "ack_status": None,
    "ack_detail": None,
    "node_vers": None,
    "batt_mv": None,
    "layout": None,
    "fw": None,
}


class Worker:
    """`received` 한 건을 집어 공중에 내보내고 `acked`/`failed` 로 닫는다. 한 번에 하나씩만 보낸다."""

    def __init__(
        self,
        store: SqliteStore,
        client: ModemClient,
        *,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], Awaitable] = asyncio.sleep,
        idle: float = 0.5,
    ) -> None:
        self.store, self.client = store, client
        self._clock, self._sleep, self._idle = clock, sleep, idle

    async def run(self, stop: asyncio.Event) -> None:
        self.store.recover()  # 송신 중 죽은 행 되돌리기 — txn 은 남는다
        while not stop.is_set():
            if not await self.once():
                await self._sleep(self._idle)

    async def once(self) -> bool:
        """한 건 처리하면 True, 집을 게 없으면 False."""
        job = self.store.pick_next()
        if job is None:
            return False
        if job.type == "TIME" and self._is_stale_time(job):
            # 파이프라인이 멈춰 있던 동안 쌓인 TIME — 가장 새 것 하나만 보낸다(로드맵 §4.3).
            self.store.update(
                job.job_id, expect_state="received", state="acked", last_error="superseded"
            )
            return True
        try:
            units = preprocess(job, clock=self._clock)
        except PreprocessError as e:
            self._finish(job, "failed", last_error=str(e))
            return True
        if is_file_session(units):
            await self._run_file(job, units)
        else:
            await self._run_single(job, units[0])
        return True

    def _is_stale_time(self, job: Job) -> bool:
        try:
            epoch = int(json.loads(job.payload)["epoch"])
        except (ValueError, KeyError, TypeError):
            return False
        return epoch < self._clock() - STALE_TIME_S

    def _claim(self, job: Job, txn: int) -> bool:
        """집기. False 면 그 사이 링크가 취소한 행이므로 보내지 않는다(로드맵 §4.3)."""
        return self.store.update(job.job_id, expect_state="received", state="sending", txn=txn)

    def _finish(self, job: Job, state: str, **fields) -> None:
        self.store.update(job.job_id, state=state, **fields)

    def _frame(self, u: Unit, txn: int) -> bytes:
        h = C.Header(type=u.type, bld=u.bld, room=u.room, unit=u.unit, txn=txn, flags=u.flags)
        return C.encode_frame(h, C.encode_payload(u.payload_obj))

    async def _tx(self, u: Unit, txn: int) -> TxResult:
        r = await self.client.tx(self._frame(u, txn), wake=u.wake, ack_ms=u.ack_ms)
        if r.status == "error" and r.reason == "busy":
            raise RuntimeError("모뎀이 busy — 워커가 tx 를 겹쳐 불렀다")
        return r

    async def _run_single(self, job: Job, u: Unit) -> None:
        # 재송(no_ack·BUSY·cad_busy·재기동 후)은 같은 TXN 이어야 노드가 DUP 으로 받는다(로드맵 §4.3).
        txn = job.txn or self.store.next_txn(job.bld, job.room, job.unit)
        if not self._claim(job, txn):
            return  # 그 사이 cancel
        res = await self._tx(u, txn)
        if res.status == "acked" and _ack_of(res).status in (
            P.AckStatus.BAD_CRC,
            P.AckStatus.STORE_FAIL,
        ):
            res = await self._tx(u, txn)  # 즉시 1회 재송
        self._apply(job, res)

    def _apply(self, job: Job, res: TxResult) -> None:
        """v2 §3.4 판정표대로 결과를 기록한다."""
        attempts = job.attempts + 1
        if res.status == "sent":
            self._finish(job, "acked", attempts=attempts)  # ack_ms=0 (TIME)
            return
        if res.status == "acked":
            ack = _ack_of(res)
            common = {
                "attempts": attempts,
                "ack_status": int(ack.status),
                "ack_detail": int(ack.detail),
                "rssi": res.rssi,
                "snr": res.snr,
                "batt_mv": ack.batt_mv,
                "layout": ack.layout,
                "fw": ack.fw,
                "node_vers": {
                    "sched": ack.sched_ver,
                    "resv": ack.resv_ver,
                    "exam": ack.exam_ver,
                    "ident": ack.ident_ver,
                },
            }
            if ack.status == P.AckStatus.BUSY:
                # 렌더 중 — attempts 는 늘리지 않는다(v2 §3.4). txn 은 그대로라 재송이 DUP 이 된다.
                self.store.update(
                    job.job_id, state="received", next_try_at=self._clock() + BUSY_WAIT_S
                )
                return
            if ack.status in (P.AckStatus.OK, P.AckStatus.DUP, P.AckStatus.GAP):
                self._finish(job, "acked", **common)  # GAP 은 메인이 FILE 재동기로 받는다
                return
            if ack.status in (P.AckStatus.BAD_PAYLOAD, P.AckStatus.UNSUPPORTED):
                log.error("job %s: 노드가 %s — 코덱/스펙 불일치 의심", job.job_id, ack.status.name)
            self._finish(
                job, "failed", last_error=f"ack_{P.AckStatus(ack.status).name.lower()}", **common
            )
            return
        if res.status in ("no_ack", "cad_busy"):
            if attempts < MAX_ATTEMPTS:
                self.store.update(
                    job.job_id,
                    state="received",
                    attempts=attempts,
                    next_try_at=self._clock() + RETRY_BACKOFF[attempts - 1],
                    last_error=res.status,
                )
            else:
                self._finish(job, "failed", attempts=attempts, last_error=res.status, **_CLEAR)
            return
        self._finish(job, "failed", attempts=attempts, last_error=res.reason or "error", **_CLEAR)

    async def _run_file(self, job: Job, units: list[Unit]) -> None:
        """BEGIN → DATA×n → END 를 한 창 안에서. TXN 은 프레임마다 새로 받는다(v2 §3.5)."""
        txn = self.store.next_txn(job.bld, job.room, job.unit)
        if not self._claim(job, txn):
            return
        i, no_ack_run, missing_used = 0, 0, 0
        res: TxResult | None = None
        while i < len(units):
            txn = self.store.next_txn(job.bld, job.room, job.unit)
            res = await self._tx(units[i], txn)
            if res.status == "acked":
                ack = _ack_of(res)
                if ack.status == P.AckStatus.BUSY:
                    await self._sleep(BUSY_WAIT_S)
                    continue  # 같은 프레임 재송, 세션 유지
                if ack.status == P.AckStatus.FILE_MISSING and missing_used < FILE_MISSING_MAX:
                    missing_used += 1
                    i = 1 + int(ack.detail)  # DATA 는 units[1] 부터
                    no_ack_run = 0
                    continue
                if ack.status not in (P.AckStatus.OK, P.AckStatus.DUP):
                    break
                no_ack_run = 0
                i += 1
                continue
            if res.status == "no_ack":
                no_ack_run += 1
                if no_ack_run >= 2:
                    break
                continue
            break
        self._apply(job, res)  # 결과는 마지막(보통 END) 프레임의 것


def _ack_of(res: TxResult) -> C.Ack:
    _, pb = C.decode_frame(res.ack)
    return C.decode_payload(P.Type.ACK, pb)

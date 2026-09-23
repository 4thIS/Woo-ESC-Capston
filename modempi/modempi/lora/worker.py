"""JobStore 소비 루프 — v2 §8.4, 저장소만 계약 ⑦ (S6 spec §4.3)."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable

from lora_proto import codec as C
from lora_proto import proto as P

from modempi.lora.clock import clock_trusted
from modempi.lora.modem_client import ModemClient, TxResult
from modempi.lora.preprocess import PreprocessError, Unit, is_file_session, preprocess
from modempi.store import Job, SqliteStore

log = logging.getLogger("lora.worker")

RETRY_BACKOFF = (5.0, 20.0, 60.0)
MAX_ATTEMPTS = 3
STALE_TIME_S = 90.0  # 이보다 오래된 TIME 행은 보내지 않고 superseded 로 닫는다
BUSY_WAIT_S = 5.0
FILE_MISSING_MAX = 2
UNTRUSTED_CLOCK_WAIT_S = 60.0  # 시계를 못 믿는 동안 TIME 을 미루는 간격
FILE_BUSY_MAX = 5  # FILE 세션 한 프레임에 허용하는 BUSY 재송 횟수 (S6 spec §9)

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
        clock_ok: Callable[[float], bool] = clock_trusted,
        net_id: Callable[[], int] = lambda: P.NET_ID,
    ) -> None:
        """`net_id` 는 프레임마다 부른다 — 메인Pi 가 학교마다 배정해 config 로 준 값(로드맵 §3)이
        재기동 없이 바로 적용되게. 기본값(lora_proto)은 게터 없이 쓰는 테스트용이다."""
        self.store, self.client = store, client
        self._clock_ok = clock_ok
        self._net_id = net_id
        self._sent_net_id = P.NET_ID  # 마지막으로 보낸 프레임의 NET_ID — 그 ACK 는 같은 망에서 온다
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
        if job.type == "TIME" and not self._clock_ok(self._clock()):
            # 옛 시각(fake-hwclock)을 모든 노드에 뿌리면 노드 시계가 망가진다 — 동기될 때까지 미룬다.
            # 그동안 90 s 가 지나면 위 superseded 로 닫히고, 스케줄러가 동기 직후 새 행을 넣는다.
            self.store.update(
                job.job_id, state="received", next_try_at=self._clock() + UNTRUSTED_CLOCK_WAIT_S
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

    def _frame(self, u: Unit, txn: int, net_id: int) -> bytes:
        h = C.Header(
            type=u.type, bld=u.bld, room=u.room, unit=u.unit, txn=txn, flags=u.flags, net_id=net_id
        )
        return C.encode_frame(h, C.encode_payload(u.payload_obj))

    def _ack_of(self, res: TxResult) -> C.Ack:
        _, pb = C.decode_frame(res.ack, net_id=self._sent_net_id)
        return C.decode_payload(P.Type.ACK, pb)

    async def _tx(self, u: Unit, txn: int) -> TxResult:
        self._sent_net_id = self._net_id()
        frame = self._frame(u, txn, self._sent_net_id)
        r = await self.client.tx(frame, wake=u.wake, ack_ms=u.ack_ms)
        if r.status == "error" and r.reason == "busy":
            raise RuntimeError("모뎀이 busy — 워커가 tx 를 겹쳐 불렀다")
        return r

    async def _run_single(self, job: Job, u: Unit) -> None:
        # TIME 은 버전이 없고 멱등이라 txn=0 으로 보낸다(v2 §3.5, S6 §9 결정 2026-09-23).
        # 노드 TXN 을 먹으면 그 노드가 기다리던 재송이 DUP 이 아니게 되어 GAP → FILE 재동기가 걸린다.
        # 재송(no_ack·BUSY·cad_busy·재기동 후)은 같은 TXN 이어야 노드가 DUP 으로 받는다(로드맵 §4.3).
        if u.type == P.Type.TIME:
            txn = 0
        else:
            txn = job.txn or self.store.next_txn(job.bld, job.room, job.unit)
        if not self._claim(job, txn):
            return  # 그 사이 cancel
        res = await self._tx(u, txn)
        if res.status == "acked" and self._ack_of(res).status in (
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
            ack = self._ack_of(res)
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
            self._retry_or_fail(job, res.status)
            return
        self._finish(job, "failed", attempts=attempts, last_error=res.reason or "error", **_CLEAR)

    def _retry_or_fail(self, job: Job, reason: str) -> None:
        """v2 §8.4 재시도 정책: 3회까지 5·20·60 s 뒤 다시, 그 뒤엔 실패로 닫는다."""
        attempts = job.attempts + 1
        if attempts < MAX_ATTEMPTS:
            self.store.update(
                job.job_id,
                state="received",
                attempts=attempts,
                next_try_at=self._clock() + RETRY_BACKOFF[attempts - 1],
                last_error=reason,
            )
        else:
            self._finish(job, "failed", attempts=attempts, last_error=reason, **_CLEAR)

    async def _run_file(self, job: Job, units: list[Unit]) -> None:
        """BEGIN → DATA×n → END 를 한 창 안에서. TXN 은 프레임마다 새로 받는다(v2 §3.5)."""
        txn = self.store.next_txn(job.bld, job.room, job.unit)
        if not self._claim(job, txn):
            return
        i, no_ack_run, missing_used, busy_used = 0, 0, 0, 0
        res: TxResult | None = None
        while i < len(units):
            txn = self.store.next_txn(job.bld, job.room, job.unit)
            res = await self._tx(units[i], txn)
            if res.status == "acked":
                ack = self._ack_of(res)
                if ack.status == P.AckStatus.BUSY:
                    # 노드가 렌더 중이면 BUSY 다. 상한이 없으면 노드가 계속 바쁠 때 워커가 영영 안 돌아와
                    # 그 모뎀Pi 의 다른 노드까지 멈춘다 (S6 spec §9: 5 회 제안).
                    busy_used += 1
                    if busy_used > FILE_BUSY_MAX:
                        # 세션 실패로 보고 일반 재시도 정책에 맡긴다 — 그냥 BUSY 로 되돌리면
                        # 노드가 계속 바쁠 때 이 행이 영원히 그 노드의 머리에 남아 FIFO 를 막는다.
                        self._retry_or_fail(job, "file_busy")
                        return
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

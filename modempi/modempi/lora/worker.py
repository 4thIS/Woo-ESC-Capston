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
        if job.type == "TIME" and self.store.newer_pending(job) and not _requests_status(job):
            # 파이프라인이 멈춰 있던 동안 쌓인 TIME — 같은 대상에 더 새 행이 있을 때만 닫는다.
            # 나이로 버리면 가장 새 것까지 사라진다. epoch 는 송신 때 다시 찍으므로 옛 행을 보내도 무해하다.
            # REQUEST_STATUS 가 붙은 행은 버리지 않는다 — 그날 일괄 STATUS 요청이 빠진다(#37 리뷰 2).
            self.store.update(
                job.job_id, expect_state="received", state="acked", last_error="superseded"
            )
            return True
        if job.type == "TIME" and not self._clock_ok(self._clock()):
            # 옛 시각(fake-hwclock)을 노드에 뿌리면 노드 시계가 망가진다 — 시계를 믿을 때까지 보내지 않는다.
            if job.bld:
                # 타겟 TIME(CLOCK_STALE)은 job_id 가 숫자가 아니라 그 노드 FIFO 의 머리에 선다. 미루기만 하면
                # 노드의 다른 작업이 영영 못 나간다(NTP 없는 직결 전시, #37 리뷰 1) — 닫는다. 노드는 동기 직후
                # 스케줄러가 내는 브로드캐스트 TIME 으로 복구된다.
                self.store.update(
                    job.job_id, expect_state="received", state="acked", last_error="clock_untrusted"
                )
            else:
                # 브로드캐스트 TIME 은 자기 큐("",0,0)라 아무도 막지 않는다 — 미룬다. 동기 직후 스케줄러가 새 행을
                # 넣으면 이 행은 위 newer_pending 으로 superseded 가 된다.
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

    def _claim(self, job: Job, txn: int) -> bool:
        """집기. False 면 그 사이 링크가 취소한 행이므로 보내지 않는다(로드맵 §4.3)."""
        return self.store.update(job.job_id, expect_state="received", state="sending", txn=txn)

    def _finish(self, job: Job, state: str, **fields) -> None:
        self.store.update(job.job_id, state=state, **fields)
        log.info(
            "job %s 끝: %s%s",
            job.job_id,
            state,
            f" ({fields['last_error']})" if fields.get("last_error") else "",
        )

    def _frame(self, u: Unit, txn: int, net_id: int) -> bytes:
        h = C.Header(
            type=u.type, bld=u.bld, room=u.room, unit=u.unit, txn=txn, flags=u.flags, net_id=net_id
        )
        return C.encode_frame(h, C.encode_payload(u.payload_obj))

    def _ack_of(self, res: TxResult) -> C.Ack:
        _, pb = C.decode_frame(res.ack, net_id=self._sent_net_id)
        return C.decode_payload(P.Type.ACK, pb)

    async def _tx(self, job: Job, u: Unit, txn: int) -> TxResult:
        self._sent_net_id = self._net_id()
        frame = self._frame(u, txn, self._sent_net_id)
        # Pi 에서 journalctl 만으로 무엇이 나갔는지 보이게(cw-10 합격 기준 "모뎀Pi 로그에 프레임 hex")
        log.info(
            "job %s → %s %s txn=%d frame=%s",
            job.job_id, P.Type(u.type).name, _addr(job), txn, frame.hex(),
        )  # fmt: skip
        r = await self.client.tx(frame, wake=u.wake, ack_ms=u.ack_ms)
        log.info("job %s ← %s%s", job.job_id, r.status, _detail(r))
        if r.status == "error" and r.reason == "busy":
            raise RuntimeError("모뎀이 busy — 워커가 tx 를 겹쳐 불렀다")
        if r.status == "acked":
            try:
                self._ack_of(r)
            except C.FrameError as e:
                # ACK 를 못 읽으면 노드가 적용했는지 모른다 — 무응답과 같다. 같은 TXN 으로 재시도하면
                # 적용된 경우 DUP 으로 닫힌다. 여기서 막지 않으면 FrameError 가 파이프라인 전체를 멈춘다.
                log.warning("ACK 해석 실패(%s) — 무응답으로 보고 재시도", e)
                return TxResult(status="no_ack", reason="bad_ack", rssi=r.rssi, snr=r.snr)
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
        res = await self._tx(job, u, txn)
        if res.status == "acked" and self._ack_of(res).status in (
            P.AckStatus.BAD_CRC,
            P.AckStatus.STORE_FAIL,
        ):
            res = await self._tx(job, u, txn)  # 즉시 1회 재송
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
                name = P.AckStatus(ack.status).name  # decode_payload 의 status 는 int
                log.error("job %s: 노드가 %s — 코덱/스펙 불일치 의심", job.job_id, name)
            self._finish(
                job, "failed", last_error=f"ack_{P.AckStatus(ack.status).name.lower()}", **common
            )
            return
        if res.status in ("no_ack", "cad_busy"):
            self._retry_or_fail(job, res.reason or res.status)
            return
        if res.reason == "modem_disconnected":
            # USB 끊김 — 프레임이 공중에 나가지 않았다. 재시도 횟수를 깎지 않고 BUSY 처럼 기다린다.
            # 깎으면 모뎀이 25 s 넘게 빠져 있을 때 쌓인 작업이 전부 failed 로 메인에 보고된다. txn 은 그대로.
            self.store.update(
                job.job_id,
                state="received",
                next_try_at=self._clock() + BUSY_WAIT_S,
                last_error="modem_disconnected",
            )
            return
        if res.reason == "modem_timeout":
            # 무응답 — 공중에 나갔을 수도 있어 횟수를 센다. 노드가 받았다면 같은 TXN 재송이 DUP.
            self._retry_or_fail(job, res.reason)
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
            res = await self._tx(job, units[i], txn)
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
                    no_ack_run, busy_used = 0, 0
                    continue
                if ack.status not in (P.AckStatus.OK, P.AckStatus.DUP):
                    break
                no_ack_run, busy_used = 0, 0  # 다음 프레임 — BUSY 상한은 프레임마다(spec §9)
                i += 1
                continue
            if res.status == "no_ack":
                no_ack_run += 1
                if no_ack_run >= 2:
                    break
                continue
            break
        self._apply(job, res)  # 결과는 마지막(보통 END) 프레임의 것


def _requests_status(job: Job) -> bool:
    """TIME 행에 REQUEST_STATUS 플래그가 붙었는가. payload 가 이상하면 False(보통 TIME 처럼 다룬다)."""
    try:
        flags = int(json.loads(job.payload).get("flags", 0))
    except (ValueError, TypeError, AttributeError):
        return False
    return bool(flags & int(P.TimeFlag.REQUEST_STATUS))


def _addr(job: Job) -> str:
    return f"{job.bld}{job.room}-{job.unit}" if job.bld else "ALL"


def _detail(r: TxResult) -> str:
    """로그용 결과 한 줄. ACK 는 상태 이름까지, 못 읽으면 그대로 둔다(판정은 호출자가 한다)."""
    if r.status == "acked" and r.ack:
        try:
            _, pb = C.decode_frame(r.ack, net_id=r.ack[1])
            ack = C.decode_payload(P.Type.ACK, pb)
            return f" {P.AckStatus(ack.status).name} rssi={r.rssi} snr={r.snr}"
        except (C.FrameError, ValueError, IndexError):
            return " (ACK 해석 불가)"
    return f" ({r.reason})" if r.reason else ""

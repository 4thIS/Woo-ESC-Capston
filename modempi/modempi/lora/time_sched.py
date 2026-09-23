"""매시 :00:05 TIME 행. 모뎀Pi 는 자기 NTP 시계로 낸다 — 메인Pi 없이도 (S6 spec §4.4)."""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import time
from collections.abc import Awaitable, Callable

from lora_proto import proto as P

from modempi.lora.clock import clock_trusted
from modempi.store import SqliteStore

log = logging.getLogger("lora.time")

OFFSET_S = 5  # 정시 + 5 초
PERIOD_S = 3600
# 방금 낸 뒤 다음 슬롯까지 이보다 짧으면 한 주기 건너뛴다. sleep 이 조금 일찍 깨면(HH:00:04.99)
# 다음 계산이 0.01 s 가 되어 1 초 차이 TIME 두 행(…04, …05)이 생긴다 — 그걸 막는다.
MIN_GAP_S = 1.0
# 기동 직후 시계를 못 믿으면(NTP 미동기) 이 간격으로 다시 본다 — 다음 정시까지 최대 1 시간 기다리지 않게.
UNTRUSTED_RETRY_S = 60.0


class TimeScheduler:
    """매시 :00:05 에 TIME 행 하나를 `jobs` 에 넣는다. 보내는 건 워커가 한다(txn=0, 90 s 지나면 버림)."""

    def __init__(
        self,
        store: SqliteStore,
        *,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], Awaitable] = asyncio.sleep,
        clock_ok: Callable[[float], bool] = clock_trusted,
    ) -> None:
        self.store, self._clock, self._sleep, self._clock_ok = store, clock, sleep, clock_ok

    def seconds_to_next(self) -> float:
        """다음 HH:00:05 까지 초. 정확히 HH:00:05 면 0 이 아니라 한 주기(3600) — 같은 슬롯을 두 번 내지 않는다."""
        return float(PERIOD_S - (self._clock() - OFFSET_S) % PERIOD_S)

    def tick(self) -> str | None:
        """TIME 행을 넣었으면 job_id, 시계를 믿을 수 없으면(`clock.clock_trusted`) None."""
        now = self._clock()
        if not self._clock_ok(now):
            log.warning("시계를 아직 믿을 수 없다(NTP 미동기) — TIME 생략")
            return None
        epoch = int(now)
        cfg = self.store.get_config() or {}
        hour = dt.datetime.fromtimestamp(epoch, dt.UTC).hour
        flags = int(P.TimeFlag.REQUEST_STATUS) if hour == cfg.get("status_hour_utc") else 0
        job_id = f"time-{epoch}"
        self.store.put_job(
            job_id=job_id,
            bld="",
            room=0,
            unit=0,
            type="TIME",
            payload=json.dumps({"epoch": epoch, "flags": flags}),
            priority=0,
            new_ver=None,
            uploaded=1,  # 메인은 TIME 결과에 관심 없음 (S6 §4.4)
        )
        return job_id

    async def run(self, stop: asyncio.Event) -> None:
        """기동 직후 1회(v2 §8.4), 이후 매시 :00:05. `stop` 은 sleep 이 끝난 뒤에만 본다 —
        한 시간 sleep 을 바로 끊으려면 호출자가 태스크를 cancel 한다."""
        while self.tick() is None:  # 기동 직후 NTP 미동기면 1 분마다 다시 — 동기되면 곧바로 1 회
            await self._sleep(UNTRUSTED_RETRY_S)
            if stop.is_set():
                return
        while not stop.is_set():
            wait = self.seconds_to_next()
            if wait < MIN_GAP_S:
                wait += PERIOD_S
            await self._sleep(wait)
            if stop.is_set():
                return
            self.tick()

import asyncio
import datetime as dt
import json

import pytest
from lora_proto import proto as P

from modempi.lora.time_sched import TimeScheduler
from modempi.store import SqliteStore

from .conftest import FakeClock

pytestmark = pytest.mark.anyio


@pytest.fixture
def db():
    s = SqliteStore(":memory:")
    yield s
    s.close()


def test_tick_inserts_hourly_time_row_not_reported_to_main(db):
    clk = FakeClock(start=1_800_000_005.0)  # UTC 08:00:05
    db.set_config({"status_hour_utc": 18})
    jid = TimeScheduler(db, clock=clk).tick()
    j = db.get_job(jid)
    assert jid == "time-1800000005"
    assert (j.type, j.priority, j.uploaded, j.bld, j.room, j.unit, j.new_ver) == (
        "TIME",
        0,
        1,
        "",
        0,
        0,
        None,
    )
    assert json.loads(j.payload) == {"epoch": int(clk.now), "flags": 0}


def test_request_status_flag_on_configured_hour(db):
    db.set_config({"status_hour_utc": 18})
    clk = FakeClock(start=1_800_036_005.0)  # 2027-01-15 UTC 18:00:05
    assert dt.datetime.fromtimestamp(clk.now, dt.UTC).hour == 18
    jid = TimeScheduler(db, clock=clk).tick()
    assert json.loads(db.get_job(jid).payload)["flags"] & int(P.TimeFlag.REQUEST_STATUS)


def test_no_time_row_before_ntp_sync(db):
    assert TimeScheduler(db, clock=lambda: 1_000.0).tick() is None


def _job_ids(db) -> list[str]:
    return [r[0] for r in db._conn.execute("SELECT job_id FROM jobs ORDER BY rowid")]


def test_seconds_to_next_lands_on_hh_00_05(db):
    clk = FakeClock(start=1_800_000_000.0)  # :00:00
    assert TimeScheduler(db, clock=clk).seconds_to_next() == 5.0
    clk.now += 5  # :00:05 — 0 이 아니라 다음 시각까지 한 주기
    assert TimeScheduler(db, clock=clk).seconds_to_next() == 3600.0
    clk.now += 1795  # :30:00
    assert TimeScheduler(db, clock=clk).seconds_to_next() == 1805.0
    clk.now += 1799.5  # :59:59.5 → 다음 정시 + 5 초까지 5.5 초
    assert TimeScheduler(db, clock=clk).seconds_to_next() == 5.5


def _stop_after(clk: FakeClock, stop: asyncio.Event, n: int):
    """clk.sleep 으로 시간을 앞당기고, n 번째 sleep 이 끝나면 stop 을 세운다."""

    async def sleep(s: float) -> None:
        await clk.sleep(s)
        if len(clk.sleeps) >= n:
            stop.set()

    return sleep


async def test_run_inserts_one_row_per_hour(db):
    clk = FakeClock(start=1_800_000_005.0)  # :00:05
    stop = asyncio.Event()
    sched = TimeScheduler(db, clock=clk, sleep=_stop_after(clk, stop, 3))
    await asyncio.wait_for(sched.run(stop), 1.0)
    # 기동 직후 1회 + sleep 두 번 뒤 각 1회. 세 번째 sleep 뒤엔 stop 이라 내지 않는다.
    assert clk.sleeps == [3600.0, 3600.0, 3600.0]
    assert _job_ids(db) == [f"time-{1_800_000_005 + 3600 * i}" for i in range(3)]
    assert all(db.get_job(j).type == "TIME" for j in _job_ids(db))


async def test_run_boot_mid_hour_then_aligns_to_hh_00_05(db):
    clk = FakeClock(start=1_800_001_800.0)  # :30:00 에 기동
    stop = asyncio.Event()
    sched = TimeScheduler(db, clock=clk, sleep=_stop_after(clk, stop, 2))
    await asyncio.wait_for(sched.run(stop), 1.0)
    assert clk.sleeps == [1805.0, 3600.0]
    assert _job_ids(db) == ["time-1800001800", "time-1800003605"]


async def test_run_early_wake_does_not_double_tick(db):
    """sleep 이 조금 일찍 깨 HH:00:04.99 에 낸 뒤엔 0.01 s 가 아니라 다음 시각까지 잔다."""
    clk = FakeClock(start=1_800_000_005.0)
    stop = asyncio.Event()

    async def early_sleep(s: float) -> None:
        await clk.sleep(s - 0.01)
        if len(clk.sleeps) >= 2:
            stop.set()

    await asyncio.wait_for(TimeScheduler(db, clock=clk, sleep=early_sleep).run(stop), 1.0)
    assert clk.sleeps[1] > 3599.0
    assert _job_ids(db) == ["time-1800000005", "time-1800003604"]


async def test_run_without_valid_clock_inserts_nothing(db):
    clk = FakeClock(start=1_000.0)
    stop = asyncio.Event()
    await asyncio.wait_for(
        TimeScheduler(db, clock=clk, sleep=_stop_after(clk, stop, 2)).run(stop), 1.0
    )
    assert _job_ids(db) == []


def test_tick_skips_when_clock_is_not_trusted(db):
    clk = FakeClock()
    assert TimeScheduler(db, clock=clk, clock_ok=lambda now: False).tick() is None
    assert _job_ids(db) == []


async def test_boot_before_ntp_sync_retries_every_minute_until_trusted(db):
    """RTC 없는 Pi 는 fake-hwclock 의 옛 시각으로 깬다. 동기 전엔 내지 않고 1 분마다 다시 보고,
    동기되면 곧바로 1 회 낸 뒤 매시 슬롯으로 돌아간다 — 다음 정시까지 최대 1 시간 기다리지 않는다."""
    clk = FakeClock(start=1_800_001_800.0)  # :30:00 기동, 2 분 뒤 NTP 동기
    synced_at = clk.now + 120
    stop = asyncio.Event()
    sched = TimeScheduler(
        db, clock=clk, sleep=_stop_after(clk, stop, 4), clock_ok=lambda now: now >= synced_at
    )
    await asyncio.wait_for(sched.run(stop), 1.0)
    assert clk.sleeps == [60.0, 60.0, 1685.0, 3600.0]
    assert _job_ids(db) == ["time-1800001920", "time-1800003605"]

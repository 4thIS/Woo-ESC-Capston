import asyncio
import socket

import pytest

from modempi.link.client import LinkClient

from .conftest import FakeHub

pytestmark = pytest.mark.anyio


async def _wait(pred, timeout=3.0):
    async with asyncio.timeout(timeout):
        while not pred():
            await asyncio.sleep(0.02)


def _closed_ephemeral_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def test_reconnect_after_hub_restart_reports_pending(store, clock):
    hub = FakeHub(token="secret")
    port = await hub.start()
    c = LinkClient(
        store,
        url=hub.url,
        modem_id="m1",
        token="secret",
        clock=clock,
        sleep=clock.sleep,
        upload_interval=0.05,
        silence_timeout=1e9,
    )
    task = asyncio.create_task(c.run())
    await asyncio.wait_for(c.connected.wait(), 3)
    await hub.stop()  # 끊김
    await _wait(lambda: c.state != "CONNECTED")
    # 끊긴 동안 파이프라인이 결과 2개를 만들었다
    for i in ("1", "2"):
        store.put_job(
            job_id=i, bld="E", room=301, unit=1, type="CMD", payload="{}", priority=3, new_ver=None
        )
        store.finish(i, state="acked")
    await asyncio.sleep(0.1)  # 재접속 시도가 몇 번 실패한다 (fake sleep 이라 즉시)
    assert c.attempts >= 2 and c.backoff > 1.0
    hub2 = FakeHub(token="secret")
    await hub2.start(port)  # 같은 포트로 복구
    try:
        await asyncio.wait_for(c.connected.wait(), 3)
        hello = await hub2.wait_for("hello")
        assert hello["pending_results"] == 2
        await _wait(lambda: sum(m["t"] == "job_result" for m in hub2.received) == 2)
        assert c.backoff == 1.0  # 성공 시 리셋
    finally:
        await c.stop()
        await asyncio.wait_for(task, 3)
        await hub2.stop()


async def test_backoff_sequence_with_jitter(store, clock):
    port = _closed_ephemeral_port()  # 아무도 안 듣는 포트
    c = LinkClient(
        store,
        url=f"ws://127.0.0.1:{port}/ws/modem",
        modem_id="m1",
        token="x",
        clock=clock,
        sleep=clock.sleep,
    )
    task = asyncio.create_task(c.run())
    # Windows 루프백 ECONNREFUSED 는 시도당 ~2 s 걸린다(OS 지연, fake sleep 과 무관) — 7회분 여유를 둔다.
    await _wait(lambda: len(clock.sleeps) >= 7, timeout=25.0)
    await c.stop()
    await asyncio.wait_for(task, 3)
    base = [1, 2, 4, 8, 16, 30, 30]
    for s, b in zip(clock.sleeps[:7], base):
        assert b * 0.8 <= s <= b * 1.2, (s, b)


async def test_auth_failure_jumps_to_max_backoff(store, fake_hub, clock):
    c = LinkClient(
        store, url=fake_hub.url, modem_id="m1", token="wrong", clock=clock, sleep=clock.sleep
    )
    task = asyncio.create_task(c.run())
    await _wait(lambda: len(clock.sleeps) >= 2)
    await c.stop()
    await asyncio.wait_for(task, 3)
    assert all(30 * 0.8 <= s <= 30 * 1.2 for s in clock.sleeps[:2])
    assert c.state == "DISCONNECTED" and store.config is None


async def test_silence_watchdog_reconnects(store, fake_hub, clock):
    c = LinkClient(
        store,
        url=fake_hub.url,
        modem_id="m1",
        token="secret",
        clock=clock,
        sleep=clock.sleep,
        silence_timeout=60,
    )
    task = asyncio.create_task(c.run())
    await asyncio.wait_for(c.connected.wait(), 3)
    first = c.attempts
    clock.now += 61  # 서버가 61 s 동안 아무 말도 안 했다
    await _wait(lambda: c.attempts > first)  # watchdog 이 닫고 재접속
    await asyncio.wait_for(c.connected.wait(), 3)
    assert len([m for m in fake_hub.received if m["t"] == "hello"]) >= 2
    await c.stop()
    await asyncio.wait_for(task, 3)

"""main.py — 링크(wj) + 파이프라인(cw) 한 프로세스. serve() 는 argv·env 없이 부를 수 있다."""

import asyncio
import contextlib
import json
import signal

import pytest
from lora_proto import proto as P

from modempi.lora.fake_modem import FakeModem
from modempi.main import _parse_args, main, serve
from modempi.store import SqliteStore

from .conftest import FakeHub

pytestmark = pytest.mark.anyio

SLOT = {
    "day": 1,
    "s_h": 9,
    "s_m": 0,
    "e_h": 9,
    "e_m": 50,
    "type": 1,
    "subject": "자료구조",
    "professor": "김교수",
}

HUB_JOB = {
    "job_id": 5,
    "bld": "E",
    "room": 302,
    "unit": 1,
    "type": "SLOT_SET",
    "payload": SLOT,
    "priority": 3,
    "new_ver": 1,
}


# ---- CLI ----


def test_cli_needs_exactly_one_of_port_or_fake(monkeypatch):
    monkeypatch.setenv("MODEMPI_STORE", "/tmp/jobs.db")
    assert _parse_args(["--fake"]).fake
    assert _parse_args(["--port", "/dev/lora-modem"]).port == "/dev/lora-modem"
    with pytest.raises(SystemExit):
        _parse_args([])
    with pytest.raises(SystemExit):
        _parse_args(["--fake", "--port", "/dev/lora-modem"])


def test_cli_store_defaults_to_env_and_is_required(monkeypatch):
    monkeypatch.setenv("MODEMPI_STORE", "/var/lib/modempi/jobs.db")
    assert _parse_args(["--fake"]).store == "/var/lib/modempi/jobs.db"
    assert _parse_args(["--fake", "--store", "x.db"]).store == "x.db"
    monkeypatch.delenv("MODEMPI_STORE")
    with pytest.raises(SystemExit):
        _parse_args(["--fake"])


def test_main_fails_before_starting_when_link_env_missing(monkeypatch, tmp_path):
    """링크 설정 누락은 태스크 안이 아니라 기동 전에 — SystemExit 가 이벤트 루프를 깨고 나가지 않게."""
    for k in ("MODEMPI_MAIN_URL", "MODEMPI_ID", "MODEMPI_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    db = tmp_path / "jobs.db"
    # main 이 env 를 --store 로 덮어쓴다 — setenv 로 등록해 두면 테스트 끝에 되돌려진다
    monkeypatch.setenv("MODEMPI_STORE", str(db))
    with pytest.raises(SystemExit, match="MODEMPI_MAIN_URL"):
        main(["--fake", "--store", str(db)])
    assert not db.exists()


# ---- serve: 감시·종료 ----


class SpyModem(FakeModem):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.closed = False

    async def close(self) -> None:
        self.closed = True
        await super().close()


class DeadModem(SpyModem):
    """읽기가 곧바로 죽는 모뎀 — 파이프라인이 예외로 끝난다."""

    async def read_line(self) -> str:
        raise RuntimeError("시리얼 읽기 죽음")


class LinkStub:
    """link.run.main(store) 자리. 멈출 때까지 돌거나, 지시대로 죽거나 정상 종료한다."""

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.finish = asyncio.Event()
        self.error: BaseException | None = None
        self.cancelled = False

    async def __call__(self, store) -> None:
        self.started.set()
        try:
            await self.finish.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        if self.error is not None:
            raise self.error


@pytest.fixture
def db():
    s = SqliteStore(":memory:")
    yield s
    s.close()


async def test_stop_ends_both_and_returns_normally(db):
    link, modem, stop = LinkStub(), SpyModem(), asyncio.Event()
    task = asyncio.create_task(serve(db, modem, stop=stop, link=link))
    await asyncio.wait_for(link.started.wait(), 1)
    stop.set()
    await asyncio.wait_for(task, 3)
    assert link.cancelled and modem.closed


async def test_link_returning_means_graceful_stop(db):
    """SIGTERM 은 link.run.main 이 건 핸들러가 받아 링크를 멈춘다 — 그때 파이프라인도 멈추고 정상 종료."""
    link, modem = LinkStub(), SpyModem()
    task = asyncio.create_task(serve(db, modem, link=link))
    await asyncio.wait_for(link.started.wait(), 1)
    link.finish.set()
    await asyncio.wait_for(task, 3)
    assert modem.closed


async def test_link_crash_stops_pipeline_and_raises(db):
    link, modem = LinkStub(), SpyModem()
    task = asyncio.create_task(serve(db, modem, link=link))
    await asyncio.wait_for(link.started.wait(), 1)
    link.error = RuntimeError("링크 죽음")
    link.finish.set()
    with pytest.raises(RuntimeError, match="링크 죽음"):
        await asyncio.wait_for(task, 3)
    assert modem.closed


async def test_pipeline_crash_cancels_link_and_raises(db):
    link, modem = LinkStub(), DeadModem()
    with pytest.raises(RuntimeError, match="시리얼 읽기 죽음"):
        await asyncio.wait_for(serve(db, modem, link=link), 3)
    assert link.cancelled and modem.closed


# ---- --fake: 가상 노드 = config.nodes ----


async def test_fake_modem_nodes_follow_config_without_duplicates(db):
    """--fake 로 Pi↔Pi 통합을 돌리면 가상 노드가 메인Pi config 의 노드 목록이어야 한다 — 아니면 전부 no_ack."""
    db.set_config({"net_id": P.NET_ID, "nodes": [{"bld": "E", "room": 301, "unit": 1}]})
    link, modem, stop = LinkStub(), FakeModem(), asyncio.Event()
    task = asyncio.create_task(serve(db, modem, stop=stop, link=link))
    await asyncio.wait_for(link.started.wait(), 1)
    E = ord("E")
    assert set(modem.nodes) == {(E, 301, 1)}  # 기동 때 이미 있던 config
    modem.nodes[(E, 301, 1)].sched_ver = 7
    other = (P.NET_ID + 1) % 256
    nodes = [{"bld": "E", "room": 301, "unit": 1}, {"bld": "E", "room": 302, "unit": 2}]
    db.set_config({"net_id": other, "nodes": [*nodes, {"bld": None, "room": 1, "unit": 1}]})
    assert set(modem.nodes) == {(E, 301, 1), (E, 302, 2)}  # 이상한 항목은 건너뛴다
    assert modem.nodes[(E, 301, 1)].sched_ver == 7  # 있던 노드는 그대로(버전 유지)
    assert modem.net_id == other  # 가상 노드도 메인Pi 가 배정한 망 번호로 받는다
    stop.set()
    await asyncio.wait_for(task, 3)


# ---- 끝에서 끝: 허브 → 링크 → store → 파이프라인 → FakeModem → 결과 업로드 ----


async def test_end_to_end_fake_mode_job_is_acked_and_reported(monkeypatch, tmp_path):
    hub = FakeHub(token="secret", jobs=[HUB_JOB])  # 기본 config 의 노드가 E302-1
    await hub.start()
    monkeypatch.setenv("MODEMPI_MAIN_URL", hub.url)
    monkeypatch.setenv("MODEMPI_ID", "mjc-eng")
    monkeypatch.setenv("MODEMPI_TOKEN", "secret")
    monkeypatch.setenv("MODEMPI_STORE", str(tmp_path / "jobs.db"))
    store = SqliteStore(str(tmp_path / "jobs.db"))
    stop = asyncio.Event()
    task = asyncio.create_task(serve(store, FakeModem(), stop=stop))
    try:
        hello = await hub.wait_for("hello", timeout=5)
        accepted = await hub.wait_for("job_accepted", timeout=5)
        async with asyncio.timeout(8):  # 업로더 주기 1 s
            while not [m for m in hub.received if m.get("t") == "job_result"]:
                assert not task.done(), task
                await asyncio.sleep(0.05)
        [result] = [m for m in hub.received if m.get("t") == "job_result"]
        assert accepted["job_id"] == 5
        assert (result["job_id"], result["state"], result["ack_status"]) == (5, "acked", 0)
        assert result["sched_ver"] == 1
        # 파이프라인이 ready 를 받아 meta 에 쓴 fw — 링크 WS 접속보다 먼저 끝난다(아래 설명)
        assert hello["modem_fw"] == "gw-2.0.0"
        types = [m["t"] for m in hub.received]
        assert types.index("job_accepted") < types.index("job_result")
    finally:
        stop.set()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(task, 5)
        store.close()
        await hub.stop()
        _drop_link_signal_handlers()
    assert task.done() and task.exception() is None


def _drop_link_signal_handlers() -> None:
    """link.run.main 이 리눅스에서 이 테스트 루프에 건 SIGINT/SIGTERM 핸들러를 걷는다(다음 테스트 격리)."""
    loop = asyncio.get_running_loop()
    for sig in ("SIGINT", "SIGTERM"):
        with contextlib.suppress(NotImplementedError, AttributeError, ValueError, RuntimeError):
            loop.remove_signal_handler(getattr(signal, sig))


def test_hub_job_payload_is_codec_slotset_without_new_ver():
    """e2e 입력이 계약 ⑥ 모양인지(S6 §5: job.payload 키 = codec 필드명, new_ver 는 바깥)."""
    from dataclasses import fields

    from lora_proto import codec as C

    assert {f.name for f in fields(C.SlotSet)} - {"new_ver"} == set(HUB_JOB["payload"])
    assert json.loads(json.dumps(HUB_JOB))["new_ver"] == 1

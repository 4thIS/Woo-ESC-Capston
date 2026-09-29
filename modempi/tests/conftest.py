import asyncio
import importlib.util
import json
import pathlib

import pytest
from lora_proto import codec as C
from lora_proto import proto as P

from modempi.lora.fake_modem import FakeModem

# server/tests/fake_hub.py 를 파일 경로로 import — modempi/tests 도 `tests` 패키지라 이름이 겹친다.
_FAKE_HUB = pathlib.Path(__file__).resolve().parents[2] / "server" / "tests" / "fake_hub.py"
_spec = importlib.util.spec_from_file_location("server_fake_hub", _FAKE_HUB)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
FakeHub = _mod.FakeHub

from .fake_store import MemoryStore

E = ord("E")


def hexs(b: bytes) -> str:
    return " ".join(f"{x:02x}" for x in b)


def frame(type_, payload, *, bld=E, room=301, unit=1, txn=7, flags=P.FLAG_ACK_REQ) -> bytes:
    return C.encode_frame(
        C.Header(type=type_, bld=bld, room=room, unit=unit, txn=txn, flags=flags),
        C.encode_payload(payload),
    )


async def send(m: FakeModem, msg: dict) -> dict:
    """한 줄 보내고 다음 응답 한 줄을 받는다."""
    await m.write_line(json.dumps(msg))
    return json.loads(await m.read_line())


@pytest.fixture
async def modem():
    m = FakeModem()
    m.add_node(E, 301, 1, sched_ver=2)
    assert json.loads(await m.read_line())["op"] == "ready"
    yield m
    await m.close()


@pytest.fixture
def anyio_backend():
    return "asyncio"


class FakeClock:
    """주입용 시계. sleep 은 시간을 앞당기고 실제로는 한 틱만 양보한다."""

    def __init__(self, start: float = 1_800_000_000.0):
        self.now = start
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.now += s
        await asyncio.sleep(0.005)


@pytest.fixture
def store():
    return MemoryStore()


@pytest.fixture
async def fake_hub():
    hub = FakeHub(token="secret")
    await hub.start()
    yield hub
    await hub.stop()


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture(autouse=True)
def _no_host_timesyncd(monkeypatch, tmp_path):
    """시계 신뢰 판정이 테스트를 돌리는 기계(CI 리눅스의 timesyncd 상태)에 따라 달라지지 않게 한다.
    timesyncd 가 없는 것으로 보고 임계값만 쓰게 한다 — 동기 표시 분기는 test_lora_clock 이 직접 본다."""
    monkeypatch.setattr("modempi.lora.clock.TIMESYNC_DIR", str(tmp_path / "no-timesyncd"))

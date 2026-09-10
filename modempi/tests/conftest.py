import json

import pytest
from lora_proto import codec as C
from lora_proto import proto as P

from modempi.lora.fake_modem import FakeModem

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

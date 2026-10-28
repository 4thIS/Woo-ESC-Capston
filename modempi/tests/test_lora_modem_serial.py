"""실물 시리얼 SerialTransport — 윈도우엔 pty 가 없어 TCP 소켓 한 쌍으로 포트를 흉내 낸다(open_fn 주입)."""

import asyncio
import json
import logging

import pytest

from modempi.lora.modem import MAX_LINE, SerialTransport

pytestmark = pytest.mark.anyio


class FakePort:
    """서버 쪽을 '모뎀'으로 쓰는 TCP. 연결마다 (reader, writer) 가 `conns` 큐에 들어온다 — 재연결 확인용."""

    def __init__(self) -> None:
        self.conns: asyncio.Queue[tuple[asyncio.StreamReader, asyncio.StreamWriter]] = (
            asyncio.Queue()
        )
        self.opens = 0
        self.writers: list[asyncio.StreamWriter] = []
        self.present = True  # False 면 포트가 없는 것처럼 open 이 실패한다(USB 뽑힘)
        self._server: asyncio.Server | None = None
        self._port = 0

    async def start(self) -> None:
        async def handle(reader, writer):
            self.writers.append(writer)
            await self.conns.put((reader, writer))

        self._server = await asyncio.start_server(handle, "127.0.0.1", 0)
        self._port = self._server.sockets[0].getsockname()[1]

    async def open_fn(self):
        self.opens += 1
        if not self.present:
            raise FileNotFoundError("/dev/lora-modem 없음")
        return await asyncio.open_connection("127.0.0.1", self._port)

    async def next_conn(self):
        return await asyncio.wait_for(self.conns.get(), 2)

    async def stop(self) -> None:
        for w in self.writers:  # 서버 쪽 연결을 닫지 않으면 wait_closed 가 영영 기다린다
            w.close()
        self._server.close()
        await self._server.wait_closed()


@pytest.fixture
async def port():
    p = FakePort()
    await p.start()
    yield p
    await p.stop()


async def say(writer: asyncio.StreamWriter, raw: bytes) -> None:
    writer.write(raw)
    await writer.drain()


async def test_write_and_read_one_line(port):
    t = SerialTransport("dummy", open_fn=port.open_fn)
    await t.open()
    modem_r, modem_w = await port.next_conn()
    await t.write_line('{"op":"ping"}')
    assert (await modem_r.readline()).decode().strip() == '{"op":"ping"}'
    await say(modem_w, b'{"op":"pong","uptime_s":7}\r\n')  # 아두이노 println 은 \r\n
    assert await asyncio.wait_for(t.read_line(), 2) == '{"op":"pong","uptime_s":7}'
    await t.close()


async def test_reconnects_after_port_drops(port):
    """모뎀이 사라지면(EOF) reconnect_s 뒤 다시 연다. 재연결 뒤 모뎀의 ready 가 읽힌다."""
    t = SerialTransport("dummy", open_fn=port.open_fn, reconnect_s=0.01)
    await t.open()
    _, first_w = await port.next_conn()
    reading = asyncio.create_task(t.read_line())
    first_w.close()  # USB 뽑힘
    _, second_w = await port.next_conn()  # read_line 이 다시 열었다
    await say(second_w, json.dumps({"op": "ready", "fw": "gw-2.0.0"}).encode() + b"\n")
    assert json.loads(await asyncio.wait_for(reading, 2))["op"] == "ready"
    assert port.opens == 2
    await t.close()


async def test_write_while_disconnected_raises_connection_error(port):
    """끊긴 동안의 쓰기는 ConnectionError — ModemClient 가 modem_disconnected 로 바꾼다."""
    t = SerialTransport("dummy", open_fn=port.open_fn, reconnect_s=5)
    with pytest.raises(ConnectionError):
        await t.write_line('{"op":"ping"}')  # 아직 안 열림
    await t.open()
    _, w = await port.next_conn()
    reading = asyncio.create_task(t.read_line())
    w.close()
    for _ in range(100):  # read_line 이 EOF 를 보고 재연결 대기에 들어갈 때까지
        await asyncio.sleep(0.01)
        if not t.connected:
            break
    with pytest.raises(ConnectionError):
        await t.write_line('{"op":"ping"}')
    await asyncio.wait_for(t.close(), 0.5)  # 5 s 재연결 대기 중이어도 바로 끝난다
    with pytest.raises(ConnectionError):
        await asyncio.wait_for(reading, 0.5)


async def test_absent_port_does_not_spin_and_close_is_prompt(port):
    """포트가 없는 동안 read_line 은 reconnect_s 마다 한 번만 열어 본다(바쁜 루프 금지)."""
    port.present = False
    t = SerialTransport("dummy", open_fn=port.open_fn, reconnect_s=0.05)
    with pytest.raises(OSError):
        await t.open()  # 기동 때 포트가 없으면 바로 알린다
    reading = asyncio.create_task(t.read_line())
    await asyncio.sleep(0.3)
    assert 3 <= port.opens <= 9  # 0.3 s / 0.05 s ≈ 6 (+ 처음 open 1)
    port.present = True
    _, w = await port.next_conn()
    await say(w, b'{"op":"ready"}\n')
    assert await asyncio.wait_for(reading, 2) == '{"op":"ready"}'
    await t.close()


async def test_overlong_and_blank_lines_are_dropped(port, caplog):
    """v2 §4.5 라인 상한 1,024 B — 넘으면 버리고 경고. 빈 줄도 버린다."""
    t = SerialTransport("dummy", open_fn=port.open_fn)
    await t.open()
    _, w = await port.next_conn()
    with caplog.at_level(logging.WARNING, logger="lora.serial"):
        await say(w, b"x" * (MAX_LINE + 1) + b"\n" + b"\r\n" + b"y" * MAX_LINE + b"\n")
        assert await asyncio.wait_for(t.read_line(), 2) == "y" * MAX_LINE
    assert "1024" in caplog.text
    await t.close()


async def test_line_beyond_stream_limit_is_dropped_not_fatal():
    """StreamReader 한도(기본 64 KiB)를 넘는 쓰레기 줄은 ValueError 로 온다 — 읽기를 죽이지 않는다."""
    reader = asyncio.StreamReader(limit=64)
    reader.feed_data(b"z" * 200 + b"\n" + b'{"op":"pong"}\n')

    class _W:
        def is_closing(self):
            return False

        def close(self):
            pass

    async def open_fn():
        return reader, _W()

    t = SerialTransport("dummy", open_fn=open_fn)
    await t.open()
    assert await asyncio.wait_for(t.read_line(), 2) == '{"op":"pong"}'
    await t.close()


async def test_close_before_read_ends_read_with_connection_error(port):
    t = SerialTransport("dummy", open_fn=port.open_fn)
    await t.open()
    await t.close()
    with pytest.raises(ConnectionError):
        await asyncio.wait_for(t.read_line(), 0.5)

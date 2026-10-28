"""실물 모뎀 시리얼 LineTransport — 포트 열기·재연결·라인 상한. 프로토콜은 ModemClient 가 안다 (S6 spec §4).

v2 §4.1·§4.5: USB 시리얼 115200, JSON lines(UTF-8, `\\n` 종단), 한 줄 최대 1,024 B.

- 끊김(EOF·`OSError`)은 `read_line` 안에서 `reconnect_s` 마다 다시 열어 본다 — 포트가 없는 동안 바쁜 루프를
  돌지 않는다. 재연결 뒤 모뎀이 `ready` 를 보내면 ModemClient 가 마지막 `cfg` 를 다시 보낸다.
- 끊긴 동안의 `write_line` 은 `ConnectionError` — ModemClient 가 `tx` 를 `modem_disconnected` 로 바꾸고
  워커가 재시도한다. 서비스는 죽지 않는다.
- `close()` 뒤 `read_line` 은 `ConnectionError` 로 끝난다(재연결 대기 중이어도 바로).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

log = logging.getLogger("lora.serial")

MAX_LINE = 1024  # v2 §4.5 — 종단(\r\n) 제외 본문 길이

Streams = tuple[asyncio.StreamReader, asyncio.StreamWriter]


async def _open_serial(port: str, baud: int) -> Streams:
    import serial_asyncio  # 실기에서만 필요 — 테스트·윈도우 개발은 open_fn 을 주입한다

    return await serial_asyncio.open_serial_connection(url=port, baudrate=baud)


class SerialTransport:
    """`LineTransport` 구현(pyserial-asyncio). `open_fn` 은 테스트 주입점 — `(reader, writer)` 를 돌려준다."""

    def __init__(
        self,
        port: str,
        *,
        baud: int = 115200,
        open_fn: Callable[[], Awaitable[Streams]] | None = None,
        reconnect_s: float = 2.0,
    ) -> None:
        self._port, self._reconnect_s = port, reconnect_s
        self._open_fn = open_fn or (lambda: _open_serial(port, baud))
        self._r: asyncio.StreamReader | None = None
        self._w: asyncio.StreamWriter | None = None
        self._closed = asyncio.Event()

    @property
    def connected(self) -> bool:
        return self._w is not None and not self._w.is_closing()

    async def open(self) -> None:
        """한 번 열어 본다. 포트가 없으면 `OSError`(pyserial `SerialException`) 를 그대로 올린다."""
        self._r, self._w = await self._open_fn()
        log.info("모뎀 시리얼 열림: %s", self._port)

    def _drop(self) -> None:
        """지금 연결을 버린다 — 다음 read_line 이 재연결한다."""
        if self._w is not None:
            self._w.close()
        self._r = self._w = None

    async def _reopen(self) -> None:
        """열릴 때까지 `reconnect_s` 마다 시도. `close()` 면 바로 돌아온다."""
        failures = 0
        while not self._closed.is_set():
            try:
                await asyncio.wait_for(self._closed.wait(), self._reconnect_s)
                return  # 닫혔다
            except TimeoutError:
                pass
            try:
                await self.open()
                log.info("모뎀 시리얼 재연결 성공: %s", self._port)
                return
            except OSError as e:
                failures += 1
                # 뽑힌 채 오래 두면 2 s 마다 한 줄씩 쌓인다 — 처음과 그 뒤 1 분쯤마다만 경고한다.
                level = logging.WARNING if failures % 30 == 1 else logging.DEBUG
                log.log(level, "모뎀 시리얼 재연결 실패 %d 회(%s) — 계속 시도", failures, e)

    async def write_line(self, line: str) -> None:
        if not self.connected:
            raise ConnectionError(f"모뎀 시리얼이 끊겨 있다: {self._port}")
        try:
            self._w.write(line.encode() + b"\n")
            await self._w.drain()
        except OSError as e:
            # 쓰다 끊겼다 — 연결을 닫아 읽기 쪽도 EOF 를 보고 재연결하게 한다.
            self._drop()
            raise ConnectionError(f"모뎀 시리얼 쓰기 실패: {e}") from e

    async def read_line(self) -> str:
        while not self._closed.is_set():
            if self._r is None:
                await self._reopen()
                continue
            try:
                raw = await self._r.readline()
            except ValueError:
                # StreamReader 한도(64 KiB)를 넘는 쓰레기 — 그 줄(또는 버퍼)은 이미 버려졌다.
                log.warning("시리얼 라인이 버퍼 한도를 넘었다 — 버림")
                continue
            except OSError as e:
                log.warning("모뎀 시리얼 끊김(%s) — %s s 뒤 재연결", e, self._reconnect_s)
                self._drop()
                continue
            if raw == b"":  # EOF = 포트가 사라짐
                if not self._closed.is_set():
                    log.warning("모뎀 시리얼 EOF — %s s 뒤 재연결", self._reconnect_s)
                self._drop()
                continue
            body = raw.rstrip(b"\r\n")
            if len(body) > MAX_LINE:
                log.warning("시리얼 라인 %d B > %d B — 버림", len(body), MAX_LINE)
                continue
            if not body.strip():
                continue
            return body.decode(errors="replace")
        raise ConnectionError("모뎀 시리얼 전송이 닫혔다")

    async def close(self) -> None:
        """재연결을 멈추고 포트를 닫는다. 여러 번 불러도 된다."""
        self._closed.set()
        self._drop()

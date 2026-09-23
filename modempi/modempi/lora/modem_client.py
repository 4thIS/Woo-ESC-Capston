"""모뎀 시리얼(JSON lines, v2 §4.2·4.3) 위의 요청/응답 계층. 프레임 내용은 모른다."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

from modempi.lora.transport import LineTransport

log = logging.getLogger("lora.modem")


@dataclass(frozen=True)
class RxEvent:
    """모뎀이 올린 비요청 업링크 한 건(v2 §4.3 `rx`)."""

    frame: bytes
    rssi: int
    snr: float


@dataclass(frozen=True)
class TxResult:
    """`tx_done` 한 줄을 그대로 옮긴 것. 판정은 워커가 한다."""

    status: str
    ack: bytes | None = None
    rssi: int | None = None
    snr: float | None = None
    air_ms: int | None = None
    tries: int | None = None
    reason: str | None = None


def _bytes(hexs: str) -> bytes:
    return bytes.fromhex(hexs.replace(" ", ""))


class ModemClient:
    """`LineTransport` 위의 요청/응답. 전역 단일 인플라이트(v2 §4.4)를 여기서 강제한다."""

    def __init__(
        self,
        transport: LineTransport,
        *,
        ready_timeout: float = 10.0,
        request_timeout: float = 15.0,
    ) -> None:
        self._t = transport
        self._ready_timeout = ready_timeout
        self._request_timeout = request_timeout
        self.rx: asyncio.Queue[RxEvent] = asyncio.Queue()
        self.fw: str | None = None
        self._ready = asyncio.Event()
        self._reader: asyncio.Task | None = None
        self._id = 0
        self._pending: asyncio.Future | None = None
        self._pending_id: int | None = None
        self._slot = asyncio.Lock()  # 모뎀은 반이중 — 요청 하나씩. ping 은 순번을 기다린다
        self._tx_inflight = False
        self._last_cfg: dict | None = None

    async def start(self) -> None:
        """읽기 태스크를 띄우고 `ready` 를 기다린다. 그 전에 읽기가 죽으면 그 예외를 바로 올린다."""
        self._reader = asyncio.create_task(self._read_loop(), name="lora.modem_reader")
        ready = asyncio.create_task(self._ready.wait())
        try:
            await asyncio.wait(
                [ready, self._reader],
                timeout=self._ready_timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            ready.cancel()
        if self._ready.is_set():
            return
        if self._reader.done():
            await self.wait_closed()  # 읽기 태스크의 예외를 올린다
        raise TimeoutError(f"모뎀 ready 가 {self._ready_timeout} s 안에 오지 않았다")

    async def wait_closed(self) -> None:
        """읽기 태스크가 끝날 때까지 기다렸다가 그 예외를 올린다(예외 없이 끝났으면 `ConnectionError`).

        읽기가 끝나면 이후 모든 요청이 타임아웃으로 떨어진다 — 파이프라인이 이걸 자식 태스크처럼 감시해
        반쯤 죽은 채 돌지 않고 멈춘다(systemd 가 다시 띄운다, #37 리뷰 3). 이 대기를 취소해도 읽기 태스크는
        그대로다(멈추는 건 `stop()`).
        """
        if self._reader is None:
            raise RuntimeError("start() 전이다")
        await asyncio.shield(self._reader)
        raise ConnectionError("모뎀 읽기 태스크가 끝났다")

    async def stop(self) -> None:
        if self._reader is not None:
            self._reader.cancel()
            # 이미 예외로 죽은 읽기 태스크면 그 예외는 wait_closed 로 이미 알렸다 — 여기서 다시 올리지 않는다.
            await asyncio.gather(self._reader, return_exceptions=True)
        await self._t.close()

    async def _read_loop(self) -> None:
        """모뎀 줄을 계속 읽는다. 한 줄이 이상해도(필드 누락·hex 아님·객체 아님) 버리고 계속 —
        이 루프가 끝나면 이후 모든 요청이 타임아웃으로 떨어진다(#35 리뷰 6)."""
        while True:
            line = await self._t.read_line()
            try:
                msg = json.loads(line)
            except ValueError:
                log.warning("모뎀 라인 파싱 실패: %r", line[:120])
                continue
            if not isinstance(msg, dict):
                log.warning("모뎀 라인이 객체가 아님: %r", line[:120])
                continue
            try:
                await self._on_message(msg)
            except (KeyError, ValueError, TypeError) as e:  # 필드 누락·hex 아님·타입 틀림
                log.warning("모뎀 라인 버림(%s): %r", e, line[:120])

    async def _on_message(self, msg: dict) -> None:
        op = msg.get("op")
        if op == "ready":
            self.fw = msg.get("fw")
            was_ready = self._ready.is_set()
            self._ready.set()
            if was_ready and self._last_cfg is not None:
                # 모뎀이 재부팅했다(또는 끊긴 동안 cfg 를 못 보냈다) — 마지막 cfg 를 다시 보낸다.
                try:
                    await self._t.write_line(json.dumps({"op": "cfg", **self._last_cfg}))
                except OSError as e:  # 또 끊겼다 — 다음 ready 에 다시. 읽기 루프는 살려 둔다
                    log.warning("모뎀 cfg 재전송 실패(%s) — 다음 ready 에 다시 보낸다", e)
        elif op == "rx":
            await self.rx.put(RxEvent(_bytes(msg["frame"]), int(msg["rssi"]), float(msg["snr"])))
        elif op in ("tx_done", "pong", "stats"):
            self._resolve(op, msg)
        elif op == "log":
            log.info("모뎀 로그[%s] %s", msg.get("level"), msg.get("msg"))

    def _resolve(self, op: str, msg: dict) -> None:
        if self._pending is None or self._pending.done():
            log.warning("짝 없는 %s 무시: %s", op, msg)
            return
        if op == "tx_done" and msg.get("id") != self._pending_id:
            log.warning("늦게 온 tx_done id=%s (현재 %s) 무시", msg.get("id"), self._pending_id)
            return
        self._pending.set_result(msg)

    async def _request(self, req: dict, *, timeout: float) -> dict:
        """한 요청을 보내고 짝이 되는 한 줄을 기다린다. 슬롯은 하나뿐이라 순번을 기다린다.

        타임아웃이 필요한 이유: 모뎀이 죽었거나 `tx_done` 의 id 가 어긋나 무시되면(v2 §4.3) 이
        future 는 영영 안 풀린다. 워커가 거기 매달리면 그 모뎀Pi 전체가 멈춘다.
        """
        async with self._slot:
            self._pending = asyncio.get_running_loop().create_future()
            self._pending_id = req.get("id")
            try:
                await self._t.write_line(json.dumps(req))
                return await asyncio.wait_for(self._pending, timeout)
            finally:
                self._pending = None
                self._pending_id = None

    async def tx(self, frame: bytes, *, wake: bool, ack_ms: int) -> TxResult:
        """`tx` 끼리 겹치면 워커 버그다(v2 §4.4 전역 단일 인플라이트) — 기다리지 않고 바로 알린다."""
        if self._tx_inflight:
            raise RuntimeError("tx 가 이미 진행 중이다 — 전역 단일 인플라이트 위반")
        self._id += 1
        self._tx_inflight = True
        try:
            msg = await self._request(
                {"op": "tx", "id": self._id, "frame": frame.hex(), "wake": wake, "ack_ms": ack_ms},
                # ACK 대기 + 최대 에어타임(SF9 wake 프레임 ≈ 4.3 s) + 여유
                timeout=self._request_timeout + ack_ms / 1000,
            )
        except TimeoutError:
            log.error("tx_done 이 오지 않았다(%s s) — 모뎀 무응답", self._request_timeout)
            return TxResult(status="error", reason="modem_timeout")
        except OSError as e:
            # USB 가 잠깐 빠졌다(SerialTransport.write_line 이 ConnectionError). 공중에 나가지 않았으니
            # 워커가 modem_timeout 처럼 같은 TXN 으로 재시도한다 — 예외를 올리면 파이프라인이 통째로 멈춘다.
            log.error("모뎀 시리얼 끊김(%s) — tx 못 보냄", e)
            return TxResult(status="error", reason="modem_disconnected")
        finally:
            self._tx_inflight = False
        ack = msg.get("ack")
        return TxResult(
            status=msg["status"],
            ack=_bytes(ack) if ack else None,
            rssi=msg.get("rssi"),
            snr=msg.get("snr"),
            air_ms=msg.get("air_ms"),
            tries=msg.get("tries"),
            reason=msg.get("reason"),
        )

    async def ping(self) -> int:
        """v2 §4.5 워치독. 송신 중이면 끝날 때까지 기다린다 — 겹쳤다고 예외를 내면 파이프라인이 죽는다.
        무응답이면 `TimeoutError`, 시리얼이 끊겼으면 `OSError` 를 올린다(호출자가 로그로 남긴다)."""
        return int((await self._request({"op": "ping"}, timeout=self._request_timeout))["uptime_s"])

    async def cfg(self, **radio) -> None:
        """§4.2 cfg 는 응답이 없지만 슬롯은 잡는다 — 전파를 쏘는 도중 무선 설정이 바뀌면 안 된다.
        (모뎀 재부팅 뒤 `ready` 에서의 재전송은 읽기 루프 안이라 슬롯을 잡지 않는다 — 그때 인플라이트는 이미 잃었다.)"""
        self._last_cfg = dict(radio)
        async with self._slot:
            try:
                await self._t.write_line(json.dumps({"op": "cfg", **radio}))
            except OSError as e:
                # 끊긴 동안이면 기억만 해 둔다 — 재연결 뒤 모뎀이 ready 를 보내면 그때 보낸다.
                log.warning("모뎀 시리얼 끊김(%s) — cfg 는 다음 ready 에 보낸다", e)

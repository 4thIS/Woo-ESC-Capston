"""모뎀 시리얼(JSON lines, v2 §4.2·4.3) 위의 요청/응답 계층. 프레임 내용은 모른다."""

from __future__ import annotations

import asyncio
import contextlib
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
        self._reader = asyncio.create_task(self._read_loop())
        await asyncio.wait_for(self._ready.wait(), self._ready_timeout)

    async def stop(self) -> None:
        if self._reader is not None:
            self._reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader
        await self._t.close()

    async def _read_loop(self) -> None:
        while True:
            line = await self._t.read_line()
            try:
                msg = json.loads(line)
            except ValueError:
                log.warning("모뎀 라인 파싱 실패: %r", line[:120])
                continue
            await self._on_message(msg)

    async def _on_message(self, msg: dict) -> None:
        op = msg.get("op")
        if op == "ready":
            self.fw = msg.get("fw")
            was_ready = self._ready.is_set()
            self._ready.set()
            if was_ready and self._last_cfg is not None:
                # 모뎀이 재부팅했다 — 무선 설정을 잃었으므로 마지막 cfg 를 다시 보낸다.
                await self._t.write_line(json.dumps({"op": "cfg", **self._last_cfg}))
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
        무응답이면 `TimeoutError` 를 올려 호출자가 모뎀을 다시 잡게 한다."""
        return int((await self._request({"op": "ping"}, timeout=self._request_timeout))["uptime_s"])

    async def cfg(self, **radio) -> None:
        """§4.2 cfg 는 응답이 없지만 슬롯은 잡는다 — 전파를 쏘는 도중 무선 설정이 바뀌면 안 된다.
        (모뎀 재부팅 뒤 `ready` 에서의 재전송은 읽기 루프 안이라 슬롯을 잡지 않는다 — 그때 인플라이트는 이미 잃었다.)"""
        self._last_cfg = dict(radio)
        async with self._slot:
            await self._t.write_line(json.dumps({"op": "cfg", **radio}))

"""v2 §4.2·4.3 모뎀 시리얼 프로토콜을 그대로 말하는 가짜 모뎀 + 가상 ESP노드.

워커·드라이버를 하드웨어 없이 검증하기 위한 것. 재시도·TXN 배정은 여기 없다(파이프라인 책임).

TXN 은 프레임 단위(§3.5): FILE 세션의 BEGIN/DATA/END 는 각각 다른 TXN 이어야 하며, 같은 TXN 재수신은 DUP 이다.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import random
from dataclasses import dataclass, field

from lora_proto import codec as C
from lora_proto import proto as P

_TOKENS = {"auto", "no_ack", "cad_busy", "bad_crc8"} | {f"ack:{s.name}" for s in P.AckStatus}
_KIND_OF_TYPE = {
    P.Type.SLOT_SET: P.FileKind.SCHEDULE,
    P.Type.SLOT_DEL: P.FileKind.SCHEDULE,
    P.Type.DAY_CLEAR: P.FileKind.SCHEDULE,
    P.Type.RESV_SET: P.FileKind.RESV,
    P.Type.RESV_DEL: P.FileKind.RESV,
    P.Type.EXAM_SET: P.FileKind.EXAM,
    P.Type.EXAM_DEL: P.FileKind.EXAM,
}


@dataclass
class NodeState:
    bld: int
    room: int
    unit: int
    sched_ver: int = 0
    resv_ver: int = 0
    exam_ver: int = 0
    ident_ver: int = 1
    batt_mv: int = 4000
    fw: int = 20
    layout: int = P.Layout.EMPTY
    last_txn: int | None = None
    files: dict[int, list] = field(default_factory=dict)  # kind → 마지막 FILE 로 받은 레코드
    _file: dict | None = None  # 진행 중 FILE 세션

    def ver(self, kind: int) -> int:
        return {
            P.FileKind.SCHEDULE: self.sched_ver,
            P.FileKind.RESV: self.resv_ver,
            P.FileKind.EXAM: self.exam_ver,
        }[kind]

    def set_ver(self, kind: int, v: int) -> None:
        if kind == P.FileKind.SCHEDULE:
            self.sched_ver = v
        elif kind == P.FileKind.RESV:
            self.resv_ver = v
        else:
            self.exam_ver = v

    def ack(self, status: int, detail: int = 0) -> C.Ack:
        return C.Ack(
            status,
            detail,
            self.batt_mv,
            self.sched_ver,
            self.resv_ver,
            self.exam_ver,
            self.ident_ver,
            self.fw,
            self.layout,
        )

    def status(self) -> C.Status:
        return C.Status(self.ack(P.AckStatus.OK), -95, 24, 0, 100)


def _hex(b: bytes) -> str:
    return " ".join(f"{x:02x}" for x in b)


def _air_ms(frame_len: int, wake: bool) -> int:
    # SF9/BW125 대략치: 심볼 4.096 ms, 페이로드 ~ 8 심볼/16 B + 헤더. wake 프리앰블은 RP_PREAMBLE_WAKE_MS.
    return int((P.RADIO["RP_PREAMBLE_WAKE_MS"] if wake else 8 * 4.096) + 60 + frame_len * 5.5)


class FakeModem:
    """LineTransport 구현. 생성 직후 `ready` 한 줄이 큐에 들어 있다."""

    def __init__(self, *, net_id: int = P.NET_ID, latency_ms: int = 0, fw: str = "gw-2.0.0"):
        self.net_id, self.latency_ms, self.fw = net_id, latency_ms, fw
        self.nodes: dict[tuple[int, int, int], NodeState] = {}
        self.unprovisioned: dict[bytes, NodeState] = {}
        self.log: list[tuple[str, dict]] = []
        self.stats = {"tx": 0, "acked": 0, "no_ack": 0, "cad_busy": 0, "rx": 0}
        self._script: list[str] = []
        self._out: asyncio.Queue[str] = asyncio.Queue()
        self._inflight: asyncio.Task | None = None
        self._rng = random.Random(1)
        self._drop_file_seq: int | None = None
        self._emit(
            {"op": "ready", "fw": fw, "sf": P.RADIO["RP_SF"], "freq": P.RADIO["RP_FREQ_MHZ"]}
        )

    # ----- 테스트 제어 -----
    def add_node(self, bld: int, room: int, unit: int, **kw) -> NodeState:
        n = NodeState(bld, room, unit, **kw)
        self.nodes[(bld, room, unit)] = n
        return n

    def add_unprovisioned(self, mac: bytes, **kw) -> NodeState:
        n = NodeState(P.BLD_UNPROVISIONED, 0, 0, ident_ver=0, **kw)
        self.unprovisioned[bytes(mac)] = n
        return n

    def script(self, outcomes: list[str]) -> None:
        bad = [t for t in outcomes if t not in _TOKENS]
        if bad:
            raise ValueError(f"알 수 없는 스크립트 토큰 {bad}; 허용: {sorted(_TOKENS)}")
        self._script.extend(outcomes)

    def drop_next_file_data(self, seq: int) -> None:
        """다음 FILE 세션에서 이 seq 의 DATA 를 한 번 버린다 → 노드가 END 에 FILE_MISSING(seq) 로 답한다."""
        self._drop_file_seq = seq

    def inject_uplink(self, frame: bytes, *, rssi: int = -100, snr: float = 5.0) -> None:
        self.stats["rx"] += 1
        self._emit({"op": "rx", "rssi": rssi, "snr": snr, "frame": _hex(frame)})

    # ----- LineTransport -----
    async def write_line(self, line: str) -> None:
        if len(line) > 1024:
            self._emit({"op": "log", "level": "warn", "msg": "line too long"})
            return
        try:
            msg = json.loads(line)
            op = msg["op"]
        except (ValueError, KeyError, TypeError):
            self._emit({"op": "log", "level": "warn", "msg": f"parse error: {line[:60]!r}"})
            return
        self.log.append(("host", msg))
        if op == "ping":
            self._emit({"op": "pong", "uptime_s": 12345})
        elif op == "stats":
            self._emit({"op": "stats", **self.stats})
        elif op == "reset":
            self._emit(
                {
                    "op": "ready",
                    "fw": self.fw,
                    "sf": P.RADIO["RP_SF"],
                    "freq": P.RADIO["RP_FREQ_MHZ"],
                }
            )
        elif op == "cfg":
            pass  # §4.2: 응답 없음. 기록만.
        elif op == "tx":
            if self._inflight and not self._inflight.done():
                self._emit(
                    {"op": "tx_done", "id": msg.get("id"), "status": "error", "reason": "busy"}
                )
                return
            self._inflight = asyncio.create_task(self._do_tx(msg))
        else:
            self._emit({"op": "log", "level": "warn", "msg": f"unknown op {op!r}"})

    async def read_line(self) -> str:
        return await self._out.get()

    async def close(self) -> None:
        if self._inflight and not self._inflight.done():
            self._inflight.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._inflight

    # ----- 내부 -----
    def _emit(self, msg: dict) -> None:
        self.log.append(("modem", msg))
        self._out.put_nowait(json.dumps(msg))

    def _next_token(self) -> str:
        return self._script.pop(0) if self._script else "auto"

    async def _do_tx(self, msg: dict) -> None:
        id_ = msg.get("id")
        wake = bool(msg.get("wake"))
        ack_ms = int(msg.get("ack_ms", 0))
        self.stats["tx"] += 1
        raw = bytes.fromhex(str(msg.get("frame", "")).replace(" ", ""))
        try:
            try:
                h, pb = C.decode_frame(raw, net_id=self.net_id)
            except C.FrameError:
                self._emit({"op": "tx_done", "id": id_, "status": "error", "reason": "bad_crc8"})
                return
            if self.latency_ms:
                await asyncio.sleep(self.latency_ms / 1000)
            tok = self._next_token()
            if tok == "bad_crc8":
                self._emit({"op": "tx_done", "id": id_, "status": "error", "reason": "bad_crc8"})
                return
            if tok == "cad_busy":
                self.stats["cad_busy"] += 1
                self._emit(
                    {
                        "op": "tx_done",
                        "id": id_,
                        "status": "cad_busy",
                        "tries": P.RADIO["RP_CAD_MAX_TRIES"],
                    }
                )
                return
            if ack_ms == 0:
                self._emit({"op": "tx_done", "id": id_, "status": "sent"})
                return
            node = self._target(h, pb)
            if tok == "no_ack" or node is None:
                self.stats["no_ack"] += 1
                self._emit({"op": "tx_done", "id": id_, "status": "no_ack"})
                return
            forced = P.AckStatus[tok[4:]] if tok.startswith("ack:") else None
            ack = node.ack(forced) if forced is not None else self._apply(node, h, pb)
            ack_frame = C.encode_frame(
                C.Header(P.Type.ACK, h.bld, h.room, h.unit, h.txn, net_id=self.net_id),
                C.encode_payload(ack),
            )
            self.stats["acked"] += 1
            self._emit(
                {
                    "op": "tx_done",
                    "id": id_,
                    "status": "acked",
                    "rssi": -90 - self._rng.randint(0, 15),
                    "snr": round(self._rng.uniform(2.0, 9.0), 1),
                    "ack": _hex(ack_frame),
                    "air_ms": _air_ms(len(raw), wake),
                }
            )
            if h.type == P.Type.CMD and C.decode_payload(h.type, pb).cmd == P.Cmd.REQUEST_STATUS:
                st = C.encode_frame(
                    C.Header(P.Type.STATUS, node.bld, node.room, node.unit, 0, net_id=self.net_id),
                    C.encode_payload(node.status()),
                )
                self.inject_uplink(st)
        except Exception as e:  # noqa: BLE001 - 워커가 죽지 않게 내부 오류를 tx_done error로 변환
            self._emit(
                {
                    "op": "tx_done",
                    "id": id_,
                    "status": "error",
                    "reason": f"internal: {type(e).__name__}",
                }
            )

    def _target(self, h: C.Header, pb: bytes) -> NodeState | None:
        if h.type == P.Type.SET_ROOM and h.bld == P.BLD_UNPROVISIONED:
            return self.unprovisioned.get(bytes(C.decode_payload(h.type, pb).mac))
        return self.nodes.get((h.bld, h.room, h.unit))

    def _apply(self, node: NodeState, h: C.Header, pb: bytes) -> C.Ack:
        """v2 §3.5 멱등·§3.4 상태 규칙대로 가상 노드에 적용하고 ACK 를 만든다."""
        if h.type == P.Type.TIME:
            # TIME 은 버전이 없고 멱등이라 txn=0 으로 오며 DUP 판정도 lastTxn 갱신도 하지 않는다
            # (v2 §3.5, 2026-09-23 결정). 안 그러면 타겟 TIME 이 그 노드의 재송을 DUP 에서 떨어뜨린다.
            return node.ack(P.AckStatus.OK)
        if node.last_txn == h.txn:
            return node.ack(P.AckStatus.DUP)
        node.last_txn = h.txn
        try:
            p = C.decode_payload(h.type, pb)
        except C.FrameError:
            return node.ack(P.AckStatus.BAD_PAYLOAD)
        t = h.type
        if t in _KIND_OF_TYPE:
            kind = _KIND_OF_TYPE[t]
            gap = (p.new_ver - node.ver(kind)) % 255 != 1
            node.set_ver(kind, p.new_ver)
            return node.ack(P.AckStatus.GAP if gap else P.AckStatus.OK)
        if t == P.Type.FILE_BEGIN:
            node._file = {
                "kind": p.kind,
                "new_ver": p.new_ver,
                "n": p.n_chunks,
                "total": p.total_len,
                "chunks": {},
            }
            return node.ack(P.AckStatus.OK)
        if t == P.Type.FILE_DATA and self._drop_file_seq == pb[0]:
            self._drop_file_seq = None
            return node.ack(P.AckStatus.OK)  # 받은 척하고 버린다 (pb[0] = seq)
        if t == P.Type.FILE_DATA:
            if node._file is None:
                return node.ack(P.AckStatus.BAD_PAYLOAD)
            node._file["chunks"][p.seq] = p.data
            return node.ack(P.AckStatus.OK)
        if t == P.Type.FILE_END:
            f = node._file
            if f is None:
                return node.ack(P.AckStatus.BAD_PAYLOAD)
            missing = [s for s in range(f["n"]) if s not in f["chunks"]]
            if missing:
                return node.ack(P.AckStatus.FILE_MISSING, missing[0])
            body = b"".join(f["chunks"][s] for s in range(f["n"]))
            if len(body) != f["total"] or C.crc16_ccitt(body) != p.crc16:
                return node.ack(P.AckStatus.BAD_CRC)
            node.files[f["kind"]] = C.decode_records(f["kind"], body)
            gap = (f["new_ver"] - node.ver(f["kind"])) % 255 != 1
            node.set_ver(f["kind"], f["new_ver"])
            node._file = None
            return node.ack(P.AckStatus.GAP if gap else P.AckStatus.OK)
        if t == P.Type.SET_ROOM:
            node.bld, node.room, node.unit, node.ident_ver = p.bld, p.room, p.unit, p.new_ver
            self.nodes[(p.bld, p.room, p.unit)] = node
            for mac, n in list(self.unprovisioned.items()):
                if n is node:
                    del self.unprovisioned[mac]
            return node.ack(P.AckStatus.OK)
        if t == P.Type.CMD:
            if p.cmd == P.Cmd.TEST_RENDER and p.args:
                node.layout = p.args[0]
            return node.ack(P.AckStatus.OK)
        if t == P.Type.TIME:  # 타겟(ack_ms>0) TIME 재동기 — v2 §8.5
            return node.ack(P.AckStatus.OK)
        return node.ack(P.AckStatus.UNSUPPORTED)

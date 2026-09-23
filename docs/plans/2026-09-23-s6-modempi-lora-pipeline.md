# S6 — 모뎀Pi LoRa 파이프라인 구현 계획 (plan)

> **작업자(사람·AI 공통):** 이 계획은 Task 단위로 실행한다. 각 Task는 **실패하는 테스트 → 구현 → 통과 → 커밋** 순서(TDD)를 지킨다. 체크박스(`- [ ]`)로 진행을 표시한다.

- 생성일시: 2026-09-23
- 담당: cw @ssenu · 영역 `modempi/modempi/lora/` (+ `modempi/main.py` 공용, wj 리뷰)
- spec: `docs/specs/2026-09-10-s6-modempi-lora-pipeline-design.md` (r3)
- 계약: 로드맵 `docs/specs/2026-09-09-roadmap-design.md` §4.2(⑥)·§4.3(⑦ 구현) · v2 `docs/specs/2026-09-09-lora-v2-wor-design.md` §3(프레임)·§4(모뎀 시리얼)·§8.4(워커)
- progress: cw-09

**목표:** 메인Pi가 준 작업을 모뎀Pi가 LoRa 프레임으로 바꿔 ESP노드에 보내고 결과를 `JobStore`에 기록하는 파이프라인을, **하드웨어 없이 가짜 모뎀만으로 끝까지 도는 상태**로 만든다.

**구조:** `store(계약 ⑦) → worker → ModemClient → LineTransport(가짜/실물 모뎀)`. 워커·시간 스케줄러·업링크 세 개의 asyncio 태스크를 `pipeline.run()`이 묶어 띄운다. 프레임 만들기는 전부 `lora_proto.codec`이 하고 이 영역은 **무엇을 언제 보낼지**만 정한다.

**스택:** Python 3.12 / asyncio / uv / pytest(anyio) · `lora_proto`(계약 ①) · `modempi.store.SqliteStore`(계약 ⑦) · `pyserial-asyncio`(Task 7에서만)

## 전역 제약 (모든 Task에 적용)

- **동기 store, 단일 연결.** `store.*`는 `await` 없이 루프에서 직접 부른다. store를 다른 스레드에서 부르지 않는다(연결이 `check_same_thread=True`).
- **전역 단일 인플라이트.** 모뎀은 반이중이라 `ModemClient.tx()`는 한 번에 하나만. 동시에 부르면 `RuntimeError`(워커 버그를 테스트로 드러내기 위함, v2 §4.4).
- **TXN은 프레임마다 하나** (v2 §3.5). 단 **비-FILE 프레임의 재송(no_ack·BUSY·cad_busy·재기동 후)은 `jobs.txn`을 다시 쓴다** — 새 TXN으로 재송하면 이미 적용한 노드가 DUP이 아니라 GAP을 낸다(로드맵 §4.3 r6).
- **무선 파라미터·NET_ID를 코드에 쓰지 않는다.** `store.get_config()["radio"]`와 `lora_proto`에서만 온다.
- **시간·대기는 주입한다.** 모든 모듈은 `clock: Callable[[], float] = time.time`, `sleep: Callable[[float], Awaitable] = asyncio.sleep`을 생성자/인자로 받는다. 테스트는 `tests/conftest.py`의 `FakeClock`을 쓴다(이미 있음: `clock.now`, `await clock.sleep(s)`).
- **문자열 bld ↔ 정수 bld**: 계약 ⑥/⑦의 `bld`는 `"E"` 같은 **한 글자 문자열**, 프레임 헤더의 `bld`는 **ASCII 정수**(`ord("E") == 0x45`). 변환은 `preprocess.py` 한 곳에서만 한다.
- 커밋: `feat(modempi): …` / `fix(modempi): …`. Task마다 1커밋 이상. PR은 Task 1~3, 4~6, 7 세 번으로 나눠 올린다(리뷰 단위).
- 게이트: `cd modempi && uv run pytest -q && uv run ruff check . && uv run ruff format --check .`

## 파일 구조

| 파일 | 책임 | Task |
|---|---|---|
| `modempi/modempi/lora/modem_client.py` | 시리얼 JSON 한 줄 ↔ 요청/응답. `tx`/`ping`/`cfg`, `rx` 큐, 단일 인플라이트 | 1 |
| `modempi/modempi/lora/preprocess.py` | `jobs` 행 → 보낼 `Unit` 목록. 주소·플래그·FILE 청킹·payload 변환 | 2 |
| `modempi/modempi/lora/worker.py` | 집기 → 송신 → 판정 → 재시도/완료. v2 §8.4 | 3 |
| `modempi/modempi/lora/time_sched.py` | 매시 `:00:05` TIME 행 생성 | 4 |
| `modempi/modempi/lora/uplink.py` | `rx` 프레임 → STATUS/HELLO → `store.put_uplink` | 5 |
| `modempi/modempi/lora/pipeline.py` | 세 태스크 기동·종료, `cfg` 재전송, 일 1회 `prune` | 6 |
| `modempi/modempi/lora/modem.py` | 실물 시리얼 `LineTransport`(pyserial-asyncio) + 재연결 | 7 |
| `modempi/main.py` | 링크(wj) + 파이프라인(cw)을 한 프로세스로. **공용 — wj 리뷰** | 7 |
| `modempi/tests/test_lora_*.py` | 위 각각의 테스트 | 각 |

---

## Task 1: `modem_client.py` — 모뎀 요청/응답 계층

**파일**
- 생성: `modempi/modempi/lora/modem_client.py`
- 생성: `modempi/tests/test_lora_modem_client.py`

**인터페이스**
- 소비: `modempi.lora.transport.LineTransport`(`write_line`/`read_line`/`close`), `modempi.lora.fake_modem.FakeModem`
- 제공:
  ```python
  @dataclass(frozen=True)
  class RxEvent:
      frame: bytes
      rssi: int
      snr: float

  @dataclass(frozen=True)
  class TxResult:
      status: str                    # "acked" | "no_ack" | "cad_busy" | "error" | "sent"
      ack: bytes | None = None
      rssi: int | None = None
      snr: float | None = None
      air_ms: int | None = None
      tries: int | None = None
      reason: str | None = None

  class ModemClient:
      rx: asyncio.Queue[RxEvent]
      fw: str | None                          # ready.fw ("gw-2.0.0")
      def __init__(self, transport: LineTransport, *, ready_timeout: float = 10.0): ...
      async def start(self) -> None           # 읽기 루프 시작 + ready 대기
      async def stop(self) -> None
      async def tx(self, frame: bytes, *, wake: bool, ack_ms: int) -> TxResult
      async def ping(self) -> int             # uptime_s
      async def cfg(self, **radio) -> None    # 마지막 값을 기억해 ready 재수신 시 재전송
  ```

- [ ] **Step 1: 실패 테스트 — ready 대기와 tx 왕복**

`modempi/tests/test_lora_modem_client.py`:
```python
import asyncio

import pytest
from lora_proto import codec as C
from lora_proto import proto as P

from modempi.lora.fake_modem import FakeModem
from modempi.lora.modem_client import ModemClient, RxEvent

from .conftest import frame

pytestmark = pytest.mark.anyio

F = frame(P.Type.DAY_CLEAR, C.DayClear(3, 2), txn=7)


@pytest.fixture
async def client():
    m = FakeModem()
    m.add_node(ord("E"), 301, 1, sched_ver=1)
    c = ModemClient(m)
    await c.start()
    yield c
    await c.stop()


async def test_start_waits_for_ready_and_records_fw(client):
    assert client.fw == "gw-2.0.0"


async def test_tx_acked_carries_ack_frame_and_radio_stats(client):
    r = await client.tx(F, wake=True, ack_ms=100)
    assert r.status == "acked" and r.rssi is not None and r.air_ms is not None
    h, pb = C.decode_frame(r.ack)
    assert h.type == P.Type.ACK and h.txn == 7
    assert C.decode_payload(P.Type.ACK, pb).status == P.AckStatus.OK
```

- [ ] **Step 2: 실패 확인**

`cd modempi && uv run pytest tests/test_lora_modem_client.py -q`
기대: `ModuleNotFoundError: No module named 'modempi.lora.modem_client'`

- [ ] **Step 3: 최소 구현**

`modempi/modempi/lora/modem_client.py`:
```python
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
    frame: bytes
    rssi: int
    snr: float


@dataclass(frozen=True)
class TxResult:
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
    def __init__(self, transport: LineTransport, *, ready_timeout: float = 10.0) -> None:
        self._t = transport
        self._ready_timeout = ready_timeout
        self.rx: asyncio.Queue[RxEvent] = asyncio.Queue()
        self.fw: str | None = None
        self._ready = asyncio.Event()
        self._reader: asyncio.Task | None = None
        self._id = 0
        self._pending: asyncio.Future | None = None
        self._pending_id: int | None = None
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

    async def _request(self, req: dict) -> dict:
        if self._pending is not None and not self._pending.done():
            raise RuntimeError("모뎀 요청이 이미 진행 중이다 — 전역 단일 인플라이트 위반")
        self._pending = asyncio.get_running_loop().create_future()
        self._pending_id = req.get("id")
        try:
            await self._t.write_line(json.dumps(req))
            return await self._pending
        finally:
            self._pending = None
            self._pending_id = None

    async def tx(self, frame: bytes, *, wake: bool, ack_ms: int) -> TxResult:
        self._id += 1
        msg = await self._request(
            {"op": "tx", "id": self._id, "frame": frame.hex(), "wake": wake, "ack_ms": ack_ms}
        )
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
        return int((await self._request({"op": "ping"}))["uptime_s"])

    async def cfg(self, **radio) -> None:
        self._last_cfg = dict(radio)
        await self._t.write_line(json.dumps({"op": "cfg", **radio}))
```

- [ ] **Step 4: 통과 확인**

`uv run pytest tests/test_lora_modem_client.py -q` → 2 passed

- [ ] **Step 5: 나머지 동작 테스트 추가 (전부 실패 → 구현은 위 코드로 이미 충족되는지 확인하고, 실패하면 고친다)**

```python
async def test_concurrent_tx_is_runtime_error(client):
    async def send():
        return await client.tx(F, wake=True, ack_ms=100)

    with pytest.raises(RuntimeError):
        await asyncio.gather(send(), send())


async def test_no_ack_and_cad_busy_pass_through(client):
    client._t.script(["no_ack", "cad_busy"])
    assert (await client.tx(F, wake=True, ack_ms=50)).status == "no_ack"
    r = await client.tx(F, wake=True, ack_ms=50)
    assert r.status == "cad_busy" and r.tries == P.RADIO["RP_CAD_MAX_TRIES"]


async def test_ack_ms_zero_returns_sent(client):
    r = await client.tx(frame(P.Type.TIME, C.Time(1_800_000_000, 0), txn=0, flags=P.FLAG_BROADCAST,
                              bld=P.BLD_ALL, room=P.ROOM_ALL, unit=0), wake=True, ack_ms=0)
    assert r.status == "sent"


async def test_unsolicited_uplink_goes_to_rx_queue(client):
    up = frame(P.Type.HELLO, C.Hello(bytes.fromhex("a0b1c2d3e4f5"), 20, 4000),
               bld=P.BLD_UNPROVISIONED, room=0, unit=0, txn=0, flags=0)
    client._t.inject_uplink(up)
    ev = await asyncio.wait_for(client.rx.get(), 2)
    assert isinstance(ev, RxEvent) and ev.frame == up


async def test_ping_returns_uptime(client):
    assert await client.ping() >= 0
```

- [ ] **Step 6: 전체 게이트 + 커밋**

```bash
cd modempi && uv run pytest -q && uv run ruff check . && uv run ruff format --check .
git add modempi/modempi/lora/modem_client.py modempi/tests/test_lora_modem_client.py
git commit -m "feat(modempi): ModemClient — 모뎀 시리얼 요청/응답 계층 (S6 §4.1)"
```

---

## Task 2: `preprocess.py` — 작업 행 → 보낼 단위

**파일**
- 생성: `modempi/modempi/lora/preprocess.py`
- 생성: `modempi/tests/test_lora_preprocess.py`

**인터페이스**
- 소비: `modempi.store.Job`(계약 ⑦ 행), `lora_proto.codec`, `lora_proto.jsonio`
- 제공:
  ```python
  class PreprocessError(ValueError): ...      # last_error 문자열을 str(e) 로 쓴다

  @dataclass(frozen=True)
  class Unit:
      bld: int          # ASCII 정수
      room: int
      unit: int
      type: int         # P.Type
      payload_obj: object
      wake: bool
      ack_ms: int
      flags: int        # FLAG_ACK_REQ / FLAG_BROADCAST

  def preprocess(job: Job, *, clock: Callable[[], float] = time.time) -> list[Unit]
  def is_file_session(units: list[Unit]) -> bool
  ```

**규칙(S6 spec §4.2 + r3)**
- `type == "TIME"`: `payload.epoch`를 **호출 시각으로 다시 찍는다**(쌓여 있던 행이 옛 시각을 뿌리지 않게). 주소는 `bld` 가 빈 문자열이면 브로드캐스트(`BLD_ALL`, `ROOM_ALL`, unit 0, `FLAG_BROADCAST`), 아니면 그 노드로 보내는 타겟 TIME. 둘 다 `wake=True, ack_ms=0`, `flags`에 `ACK_REQ` 없음.
- `type == "FILE"`: `payload = {"kind": int, "records": [ {...}, ... ]}` → 각 레코드를 `jsonio.from_json(_REC_TYPE[kind], rec, new_ver=job.new_ver)`로 codec 객체화 → `C.build_file(kind, records, job.new_ver)` → BEGIN만 `wake=True`, 나머지 `wake=False`, 전부 `ack_ms=3000`, `flags=FLAG_ACK_REQ`.
- 그 외: `jsonio.from_json(P.Type[job.type], json.loads(job.payload), new_ver=job.new_ver)` 한 개 → `wake=True, ack_ms=3000, flags=FLAG_ACK_REQ`.
- `job.unit == 0` 이고 TIME이 아니면 `PreprocessError("unit0")`.
- 변환 실패는 전부 `PreprocessError(f"bad_payload: {e}")`.

- [ ] **Step 1: 실패 테스트**

`modempi/tests/test_lora_preprocess.py`:
```python
import json

import pytest
from lora_proto import codec as C
from lora_proto import proto as P

from modempi.lora.preprocess import PreprocessError, Unit, is_file_session, preprocess
from modempi.store import SqliteStore

from .conftest import FakeClock


@pytest.fixture
def db():
    s = SqliteStore(":memory:")
    yield s
    s.close()


def job(db, *, job_id="10", bld="E", room=301, unit=1, type="SLOT_SET", payload=None, new_ver=3):
    db.put_job(
        job_id=job_id, bld=bld, room=room, unit=unit, type=type,
        payload=json.dumps(payload if payload is not None else {
            "day": 1, "s_h": 9, "s_m": 0, "e_h": 9, "e_m": 50, "type": 1,
            "subject": "자료구조", "professor": "김교수",
        }),
        priority=3, new_ver=new_ver,
    )
    return db.get_job(job_id)


def test_normal_downlink_is_one_wake_unit_with_ack_req(db):
    [u] = preprocess(job(db))
    assert isinstance(u, Unit)
    assert (u.bld, u.room, u.unit, u.type) == (ord("E"), 301, 1, P.Type.SLOT_SET)
    assert (u.wake, u.ack_ms, u.flags) == (True, 3000, P.FLAG_ACK_REQ)
    assert u.payload_obj == C.SlotSet(3, 1, 9, 0, 9, 50, 1, "자료구조", "김교수")
    assert is_file_session([u]) is False


def test_unit_zero_non_time_is_rejected(db):
    with pytest.raises(PreprocessError, match="unit0"):
        preprocess(job(db, unit=0))


def test_bad_payload_is_reported_with_reason(db):
    with pytest.raises(PreprocessError, match="bad_payload"):
        preprocess(job(db, payload={"day": 1}))
```

- [ ] **Step 2: 실패 확인** — `uv run pytest tests/test_lora_preprocess.py -q` → `ModuleNotFoundError`

- [ ] **Step 3: 구현**

```python
"""jobs 행 → 공중에 실제로 나갈 단위 목록. 프레임 바이트는 worker 가 만든다 (S6 spec §4.2)."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass

from lora_proto import codec as C
from lora_proto import jsonio
from lora_proto import proto as P

from modempi.store import Job

_REC_TYPE = {
    P.FileKind.SCHEDULE: P.Type.SLOT_SET,
    P.FileKind.RESV: P.Type.RESV_SET,
    P.FileKind.EXAM: P.Type.EXAM_SET,
}


class PreprocessError(ValueError):
    """이 작업은 보낼 수 없다. str(e) 가 그대로 jobs.last_error 가 된다."""


@dataclass(frozen=True)
class Unit:
    bld: int
    room: int
    unit: int
    type: int
    payload_obj: object
    wake: bool
    ack_ms: int
    flags: int


def is_file_session(units: list[Unit]) -> bool:
    return bool(units) and units[0].type == P.Type.FILE_BEGIN


def preprocess(job: Job, *, clock: Callable[[], float] = time.time) -> list[Unit]:
    try:
        payload = json.loads(job.payload)
    except ValueError as e:
        raise PreprocessError(f"bad_payload: {e}") from e

    if job.type == "TIME":
        return [_time_unit(job, payload, clock)]
    if job.unit == 0:
        raise PreprocessError("unit0")
    if job.type == "FILE":
        return _file_units(job, payload)
    return [_plain_unit(job, payload)]


def _addr(job: Job) -> tuple[int, int, int]:
    return ord(job.bld), job.room, job.unit


def _time_unit(job: Job, payload: dict, clock: Callable[[], float]) -> Unit:
    flags = int(payload.get("flags", 0))
    obj = C.Time(int(clock()), flags)  # 쌓여 있던 행이 옛 시각을 뿌리지 않게 지금 시각으로
    if job.bld == "":
        return Unit(P.BLD_ALL, P.ROOM_ALL, 0, P.Type.TIME, obj, True, 0, P.FLAG_BROADCAST)
    bld, room, unit = _addr(job)
    return Unit(bld, room, unit, P.Type.TIME, obj, True, 0, 0)


def _plain_unit(job: Job, payload: dict) -> Unit:
    try:
        type_ = P.Type[job.type]
        obj = jsonio.from_json(type_, payload, new_ver=job.new_ver)
    except (KeyError, ValueError, TypeError) as e:
        raise PreprocessError(f"bad_payload: {e}") from e
    bld, room, unit = _addr(job)
    return Unit(bld, room, unit, type_, obj, True, 3000, P.FLAG_ACK_REQ)


def _file_units(job: Job, payload: dict) -> list[Unit]:
    try:
        kind = int(payload["kind"])
        rec_type = _REC_TYPE[P.FileKind(kind)]
        records = [jsonio.from_json(rec_type, r, new_ver=job.new_ver) for r in payload["records"]]
        parts = C.build_file(kind, records, job.new_ver)
    except (KeyError, ValueError, TypeError, C.FrameError) as e:
        raise PreprocessError(f"bad_payload: {e}") from e
    bld, room, unit = _addr(job)
    return [
        Unit(bld, room, unit, C.type_of(p), p, i == 0, 3000, P.FLAG_ACK_REQ)
        for i, p in enumerate(parts)
    ]
```

- [ ] **Step 4: 통과 확인** — 3 passed

- [ ] **Step 5: TIME·FILE 테스트 추가**

```python
def test_broadcast_time_restamps_epoch_and_has_no_ack(db):
    clk = FakeClock()
    j = job(db, job_id="time-1", bld="", room=0, unit=0, type="TIME", new_ver=None,
            payload={"epoch": 1_700_000_000, "flags": int(P.TimeFlag.REQUEST_STATUS)})
    [u] = preprocess(j, clock=clk)
    assert (u.bld, u.room, u.unit) == (P.BLD_ALL, P.ROOM_ALL, 0)
    assert (u.wake, u.ack_ms, u.flags) == (True, 0, P.FLAG_BROADCAST)
    assert u.payload_obj == C.Time(int(clk.now), int(P.TimeFlag.REQUEST_STATUS))


def test_targeted_time_keeps_node_address_and_no_broadcast_flag(db):
    j = job(db, job_id="time-2-E301-1", type="TIME", new_ver=None, payload={"epoch": 1, "flags": 0})
    [u] = preprocess(j)
    assert (u.bld, u.room, u.unit, u.flags, u.ack_ms) == (ord("E"), 301, 1, 0, 0)


def test_file_becomes_begin_data_end_with_only_begin_waking(db):
    recs = [{"day": d, "s_h": 9, "s_m": 0, "e_h": 9, "e_m": 50, "type": 1,
             "subject": f"과목{d}", "professor": "김교수"} for d in range(1, 6)]
    j = job(db, type="FILE", new_ver=7, payload={"kind": int(P.FileKind.SCHEDULE), "records": recs})
    units = preprocess(j)
    assert is_file_session(units) is True
    assert [u.type for u in units] == [P.Type.FILE_BEGIN] + [P.Type.FILE_DATA] * (len(units) - 2) + [P.Type.FILE_END]
    assert [u.wake for u in units] == [True] + [False] * (len(units) - 1)
    assert all(u.ack_ms == 3000 and u.flags == P.FLAG_ACK_REQ for u in units)
    assert units[0].payload_obj.new_ver == 7 and units[0].payload_obj.kind == P.FileKind.SCHEDULE


def test_file_with_wrong_kind_is_bad_payload(db):
    j = job(db, type="FILE", new_ver=7,
            payload={"kind": int(P.FileKind.RESV),
                     "records": [{"day": 1, "s_h": 9, "s_m": 0, "e_h": 9, "e_m": 50, "type": 1,
                                  "subject": "a", "professor": "b"}]})
    with pytest.raises(PreprocessError, match="bad_payload"):
        preprocess(j)
```

- [ ] **Step 6: 게이트 + 커밋**

```bash
cd modempi && uv run pytest -q && uv run ruff check . && uv run ruff format --check .
git add modempi/modempi/lora/preprocess.py modempi/tests/test_lora_preprocess.py
git commit -m "feat(modempi): preprocess — jobs 행을 송신 단위로 (TIME 재스탬프·FILE 청킹·unit0 거절)"
```

---

## Task 3: `worker.py` — 소비 루프와 결과 판정

**파일**
- 생성: `modempi/modempi/lora/worker.py`
- 생성: `modempi/tests/test_lora_worker.py`

**인터페이스**
- 소비: `SqliteStore`(`recover`/`pick_next`/`update`/`next_txn`), `ModemClient.tx`, `preprocess`
- 제공:
  ```python
  RETRY_BACKOFF = (5.0, 20.0, 60.0)
  MAX_ATTEMPTS = 3
  STALE_TIME_S = 90.0        # 이보다 오래된 TIME 행은 보내지 않고 superseded 로 닫는다

  class Worker:
      def __init__(self, store, client, *, clock=time.time, sleep=asyncio.sleep, idle: float = 0.5): ...
      async def run(self, stop: asyncio.Event) -> None    # recover() 후 루프
      async def once(self) -> bool                        # 한 건 처리하면 True, 없으면 False
  ```

**판정표(v2 §3.4·§8.4, S6 spec §4.3)** — `once()`가 이대로 구현한다.

| 결과 | 처리 |
|---|---|
| `sent` (TIME) | `acked` |
| `acked` + ACK `OK`/`DUP` | `acked` + ACK 필드 기록 |
| `acked` + `GAP` | `acked`, `ack_status=GAP` (메인이 FILE 큐잉) |
| `acked` + `BUSY` | `received`, `next_try_at = now + 5`, `attempts` 그대로 |
| `acked` + `BAD_CRC`/`STORE_FAIL` | 같은 프레임 즉시 1회 재송 → 그래도면 `failed` |
| `acked` + `BAD_PAYLOAD`/`UNSUPPORTED` | `failed` (코덱 버그 의심, `log.error`) |
| `no_ack` / `cad_busy` | `attempts+1`; < 3 → `received`, `next_try_at = now + RETRY_BACKOFF[attempts-1]`; ≥ 3 → `failed` |
| `error(reason)` | `failed(last_error=reason)`. 단 `reason == "busy"` 는 워커 버그 → `RuntimeError` |

- `failed`로 닫을 때는 앞 시도의 `ack_status`·`ack_detail`·`node_vers`·`batt_mv`·`layout`·`fw`를 `None`으로 함께 넘긴다(메인이 그대로 복사하므로).
- FILE 세션: 프레임마다 `next_txn()`. `FILE_MISSING`(ACK `detail` = 빠진 seq)이면 그 seq부터 DATA를 다시 보내고 END를 다시 보낸다(최대 2회). `no_ack` 2회 연속이면 세션 실패 → 위 재시도 정책. `BUSY`는 5 s 후 같은 프레임 재송(세션 유지).
- 비-FILE: `txn = job.txn or store.next_txn(bld, room, unit)`, `update(expect_state="received", state="sending", txn=txn)`가 False면 취소된 것이므로 건너뛴다.

- [ ] **Step 1: 실패 테스트 — 정상 1건**

`modempi/tests/test_lora_worker.py`:
```python
import json

import pytest
from lora_proto import codec as C
from lora_proto import proto as P

from modempi.lora.fake_modem import FakeModem
from modempi.lora.modem_client import ModemClient
from modempi.lora.worker import Worker
from modempi.store import SqliteStore

from .conftest import FakeClock

pytestmark = pytest.mark.anyio

SLOT = {"day": 1, "s_h": 9, "s_m": 0, "e_h": 9, "e_m": 50, "type": 1,
        "subject": "자료구조", "professor": "김교수"}


@pytest.fixture
def clk():
    return FakeClock()


@pytest.fixture
async def rig(clk):
    db = SqliteStore(":memory:", clock=clk)
    modem = FakeModem()
    modem.add_node(ord("E"), 301, 1, sched_ver=2)
    client = ModemClient(modem)
    await client.start()
    yield db, modem, client, Worker(db, client, clock=clk, sleep=clk.sleep)
    await client.stop()
    db.close()


def put(db, job_id="10", *, type="SLOT_SET", payload=None, new_ver=3, unit=1, priority=3, **kw):
    db.put_job(job_id=job_id, bld="E", room=301, unit=unit, type=type,
               payload=json.dumps(payload if payload is not None else SLOT),
               priority=priority, new_ver=new_ver, **kw)


async def test_acked_job_records_ack_fields(rig):
    db, _, _, w = rig
    put(db, new_ver=3)
    assert await w.once() is True
    j = db.get_job("10")
    assert (j.state, j.ack_status, j.attempts) == ("acked", int(P.AckStatus.OK), 1)
    assert j.txn == 1 and j.finished_at is not None
    assert json.loads(j.node_vers)["sched"] == 3
    assert j.batt_mv and j.layout is not None and j.fw is not None
    assert j.rssi is not None and j.snr is not None
```

- [ ] **Step 2: 실패 확인** — `ModuleNotFoundError: modempi.lora.worker`

- [ ] **Step 3: 구현**

```python
"""JobStore 소비 루프 — v2 §8.4, 저장소만 계약 ⑦ (S6 spec §4.3)."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable

from lora_proto import codec as C
from lora_proto import proto as P

from modempi.lora.modem_client import ModemClient, TxResult
from modempi.lora.preprocess import PreprocessError, Unit, is_file_session, preprocess
from modempi.store import Job, SqliteStore

log = logging.getLogger("lora.worker")

RETRY_BACKOFF = (5.0, 20.0, 60.0)
MAX_ATTEMPTS = 3
STALE_TIME_S = 90.0
BUSY_WAIT_S = 5.0
FILE_MISSING_MAX = 2

_CLEAR = {"ack_status": None, "ack_detail": None, "node_vers": None,
          "batt_mv": None, "layout": None, "fw": None}


class Worker:
    def __init__(self, store: SqliteStore, client: ModemClient, *, clock: Callable[[], float] = time.time,
                 sleep: Callable[[float], Awaitable] = asyncio.sleep, idle: float = 0.5) -> None:
        self.store, self.client = store, client
        self._clock, self._sleep, self._idle = clock, sleep, idle

    async def run(self, stop: asyncio.Event) -> None:
        self.store.recover()
        while not stop.is_set():
            if not await self.once():
                await self._sleep(self._idle)

    async def once(self) -> bool:
        job = self.store.pick_next()
        if job is None:
            return False
        if job.type == "TIME" and self._is_stale_time(job):
            self.store.update(job.job_id, expect_state="received", state="acked",
                              last_error="superseded")
            return True
        try:
            units = preprocess(job, clock=self._clock)
        except PreprocessError as e:
            self._finish(job, "failed", last_error=str(e))
            return True
        if is_file_session(units):
            await self._run_file(job, units)
        else:
            await self._run_single(job, units[0])
        return True

    def _is_stale_time(self, job: Job) -> bool:
        try:
            epoch = int(json.loads(job.payload)["epoch"])
        except (ValueError, KeyError, TypeError):
            return False
        return epoch < self._clock() - STALE_TIME_S

    def _claim(self, job: Job, txn: int) -> bool:
        return self.store.update(job.job_id, expect_state="received", state="sending", txn=txn)

    def _finish(self, job: Job, state: str, **fields) -> None:
        self.store.update(job.job_id, state=state, **fields)

    def _frame(self, u: Unit, txn: int) -> bytes:
        h = C.Header(type=u.type, bld=u.bld, room=u.room, unit=u.unit, txn=txn, flags=u.flags)
        return C.encode_frame(h, C.encode_payload(u.payload_obj))

    async def _tx(self, u: Unit, txn: int) -> TxResult:
        r = await self.client.tx(self._frame(u, txn), wake=u.wake, ack_ms=u.ack_ms)
        if r.status == "error" and r.reason == "busy":
            raise RuntimeError("모뎀이 busy — 워커가 tx 를 겹쳐 불렀다")
        return r

    async def _run_single(self, job: Job, u: Unit) -> None:
        txn = job.txn or self.store.next_txn(job.bld, job.room, job.unit)  # 재송은 같은 TXN
        if not self._claim(job, txn):
            return  # 그 사이 cancel
        res = await self._tx(u, txn)
        if res.status == "acked" and _ack_of(res).status in (P.AckStatus.BAD_CRC, P.AckStatus.STORE_FAIL):
            res = await self._tx(u, txn)  # 즉시 1회 재송
        self._apply(job, res)

    def _apply(self, job: Job, res: TxResult) -> None:
        attempts = job.attempts + 1
        if res.status == "sent":
            self._finish(job, "acked", attempts=attempts)
            return
        if res.status == "acked":
            ack = _ack_of(res)
            common = {"attempts": attempts, "ack_status": int(ack.status), "ack_detail": int(ack.detail),
                      "rssi": res.rssi, "snr": res.snr, "batt_mv": ack.batt_mv, "layout": ack.layout,
                      "fw": ack.fw,
                      "node_vers": {"sched": ack.sched_ver, "resv": ack.resv_ver,
                                    "exam": ack.exam_ver, "ident": ack.ident_ver}}
            if ack.status == P.AckStatus.BUSY:
                self.store.update(job.job_id, state="received",
                                  next_try_at=self._clock() + BUSY_WAIT_S)
                return
            if ack.status in (P.AckStatus.OK, P.AckStatus.DUP, P.AckStatus.GAP):
                self._finish(job, "acked", **common)
                return
            if ack.status in (P.AckStatus.BAD_PAYLOAD, P.AckStatus.UNSUPPORTED):
                log.error("job %s: 노드가 %s — 코덱/스펙 불일치 의심", job.job_id, ack.status.name)
            self._finish(job, "failed", last_error=f"ack_{P.AckStatus(ack.status).name.lower()}",
                         **common)
            return
        if res.status in ("no_ack", "cad_busy"):
            if attempts < MAX_ATTEMPTS:
                self.store.update(job.job_id, state="received", attempts=attempts,
                                  next_try_at=self._clock() + RETRY_BACKOFF[attempts - 1],
                                  last_error=res.status)
            else:
                self._finish(job, "failed", attempts=attempts, last_error=res.status, **_CLEAR)
            return
        self._finish(job, "failed", attempts=attempts, last_error=res.reason or "error", **_CLEAR)

    async def _run_file(self, job: Job, units: list[Unit]) -> None:
        txn = self.store.next_txn(job.bld, job.room, job.unit)
        if not self._claim(job, txn):
            return
        i, no_ack_run, missing_used = 0, 0, 0
        res: TxResult | None = None
        while i < len(units):
            txn = self.store.next_txn(job.bld, job.room, job.unit)  # FILE 은 프레임마다 새 TXN
            res = await self._tx(units[i], txn)
            if res.status == "acked":
                ack = _ack_of(res)
                if ack.status == P.AckStatus.BUSY:
                    await self._sleep(BUSY_WAIT_S)
                    continue  # 같은 프레임 재송, 세션 유지
                if ack.status == P.AckStatus.FILE_MISSING and missing_used < FILE_MISSING_MAX:
                    missing_used += 1
                    i = 1 + int(ack.detail)  # DATA 는 units[1] 부터
                    no_ack_run = 0
                    continue
                if ack.status not in (P.AckStatus.OK, P.AckStatus.DUP):
                    break
                no_ack_run = 0
                i += 1
                continue
            if res.status == "no_ack":
                no_ack_run += 1
                if no_ack_run >= 2:
                    break
                continue
            break
        self._apply(job, res)


def _ack_of(res: TxResult) -> C.Ack:
    _, pb = C.decode_frame(res.ack)
    return C.decode_payload(P.Type.ACK, pb)
```

- [ ] **Step 4: 통과 확인** — `uv run pytest tests/test_lora_worker.py -q` → 1 passed

- [ ] **Step 5: 시나리오 테스트 추가 (spec §8 성공 기준 목록 그대로)**

```python
async def test_no_ack_retries_with_backoff_then_fails(rig, clk):
    db, modem, _, w = rig
    modem.script(["no_ack", "no_ack", "no_ack"])
    put(db)
    for expect_attempts, backoff in ((1, 5.0), (2, 20.0), (3, None)):
        await w.once()
        j = db.get_job("10")
        assert j.attempts == expect_attempts
        if backoff is None:
            assert (j.state, j.last_error) == ("failed", "no_ack") and j.ack_status is None
        else:
            assert (j.state, j.next_try_at) == ("received", clk.now + backoff)
            clk.now += backoff


async def test_retry_reuses_same_txn_so_node_answers_dup(rig):
    """ACK 유실 후 재송이 새 TXN 이면 노드는 (v−v) mod 255 = 0 → GAP. 같은 TXN 이어야 DUP."""
    db, modem, _, w = rig
    modem.script(["no_ack"])
    put(db, new_ver=3)
    await w.once()                      # 노드는 받아서 적용했지만 ACK 가 사라짐
    first_txn = db.get_job("10").txn
    await w.once()                      # 재송
    j = db.get_job("10")
    assert j.txn == first_txn
    assert (j.state, j.ack_status) == ("acked", int(P.AckStatus.DUP))


async def test_busy_requeues_after_5s_without_counting_attempt(rig, clk):
    db, modem, _, w = rig
    modem.script(["ack:BUSY"])
    put(db)
    await w.once()
    j = db.get_job("10")
    assert (j.state, j.attempts, j.next_try_at) == ("received", 0, clk.now + 5.0)


async def test_gap_is_acked_and_reported(rig):
    db, modem, _, w = rig
    put(db, new_ver=9)                  # 노드 sched_ver=2 → 버전 불연속
    await w.once()
    j = db.get_job("10")
    assert (j.state, j.ack_status) == ("acked", int(P.AckStatus.GAP))


async def test_bad_crc_resends_once_then_fails(rig):
    db, modem, _, w = rig
    modem.script(["ack:BAD_CRC", "ack:BAD_CRC"])
    put(db)
    await w.once()
    j = db.get_job("10")
    assert (j.state, j.last_error) == ("failed", "ack_bad_crc")


async def test_cancelled_between_pick_and_claim_is_not_sent(rig):
    db, modem, _, w = rig
    put(db)
    job = db.pick_next()
    db.cancel_job(job.job_id)
    await w.once()
    assert db.get_job("10").state == "cancelled"


async def test_unit0_job_fails_with_unit0(rig):
    db, _, _, w = rig
    put(db, unit=0)
    await w.once()
    assert (db.get_job("10").state, db.get_job("10").last_error) == ("failed", "unit0")


async def test_time_row_is_sent_without_ack_and_stale_one_is_superseded(rig, clk):
    db, _, _, w = rig
    db.put_job(job_id="time-old", bld="", room=0, unit=0, type="TIME",
               payload=json.dumps({"epoch": int(clk.now) - 3600, "flags": 0}),
               priority=0, new_ver=None, uploaded=1)
    db.put_job(job_id="time-new", bld="", room=0, unit=0, type="TIME",
               payload=json.dumps({"epoch": int(clk.now), "flags": 0}),
               priority=0, new_ver=None, uploaded=1)
    await w.once()
    assert (db.get_job("time-old").state, db.get_job("time-old").last_error) == ("acked", "superseded")
    await w.once()
    assert db.get_job("time-new").state == "acked"


async def test_file_session_sends_begin_data_end_each_with_new_txn(rig):
    db, modem, _, w = rig
    node = modem.nodes[(ord("E"), 301, 1)]
    recs = [{"day": d, "s_h": 9, "s_m": 0, "e_h": 9, "e_m": 50, "type": 1,
             "subject": f"과목{d}", "professor": "김교수"} for d in range(1, 8)]
    put(db, type="FILE", new_ver=3, payload={"kind": int(P.FileKind.SCHEDULE), "records": recs})
    await w.once()
    j = db.get_job("10")
    assert (j.state, j.ack_status) == ("acked", int(P.AckStatus.OK))
    assert node.sched_ver == 3 and len(node.files[int(P.FileKind.SCHEDULE)]) == len(recs)


async def test_file_missing_resends_from_that_seq(rig):
    db, modem, _, w = rig
    recs = [{"day": d, "s_h": 9, "s_m": 0, "e_h": 9, "e_m": 50, "type": 1,
             "subject": f"과목{d}", "professor": "김교수"} for d in range(1, 8)]
    put(db, type="FILE", new_ver=3, payload={"kind": int(P.FileKind.SCHEDULE), "records": recs})
    modem.drop_next_file_data(1)        # Step 6 에서 fake_modem 에 추가하는 헬퍼
    await w.once()
    assert db.get_job("10").state == "acked"


async def test_many_jobs_in_a_row_never_hit_modem_busy(rig):
    """워커는 한 번에 하나씩만 보낸다(루프가 직렬). busy 가 한 번이라도 나면 RuntimeError 로 터진다."""
    db, modem, _, w = rig
    modem.add_node(ord("E"), 301, 2)
    for i in range(10):
        put(db, job_id=str(100 + i), unit=1 + i % 2)
    for _ in range(10):
        assert await w.once() is True
    assert await w.once() is False
    assert [m for m in modem.log if m[0] == "modem" and m[1].get("reason") == "busy"] == []
    assert all(db.get_job(str(100 + i)).state == "acked" for i in range(10))
```

- [ ] **Step 6: `fake_modem`에 `drop_next_file_data(seq)` 추가 (테스트 지원, S1 영역 cw 소유)**

`FILE_END` 는 이미 빠진 청크가 있으면 `FILE_MISSING(missing[0])` 을 돌려준다(`fake_modem.py` 288~290행). 따라서 **DATA 한 개를 버리는 수단만** 추가하면 된다.

`modempi/modempi/lora/fake_modem.py`에 추가:
```python
    def drop_next_file_data(self, seq: int) -> None:
        """다음 FILE 세션에서 이 seq 의 DATA 를 한 번 버린다 → 노드가 END 에 FILE_MISSING(seq) 로 답한다."""
        self._drop_file_seq = seq
```
`_apply`의 `FILE_DATA` 처리 앞에:
```python
        if h.type == P.Type.FILE_DATA and getattr(self, "_drop_file_seq", None) == pb[0]:
            self._drop_file_seq = None
            return node.ack(P.AckStatus.OK)   # 받은 척하고 버린다
```
`__init__` 에 `self._drop_file_seq: int | None = None` 을 추가한다. `pb[0]` 은 `FILE_DATA` 의 `seq` 바이트다.

- [ ] **Step 7: 게이트 + 커밋 + PR 1 (Task 1~3)**

```bash
cd modempi && uv run pytest -q && uv run ruff check . && uv run ruff format --check .
git add modempi/modempi/lora/worker.py modempi/modempi/lora/fake_modem.py modempi/tests/test_lora_worker.py
git commit -m "feat(modempi): worker — 집기·송신·판정·재시도, FILE 세션과 TIME 정리 (v2 §8.4)"
git push origin cw
```

PR 본문에는 (1) 이 계획서 링크와 Task 번호, (2) 검증 명령 결과(`uv run pytest -q`, ruff), (3) 가짜 모뎀 시나리오 중 이번 PR 이 덮은 목록, (4) wj 확인 요청 — 계약 ⑦ 사용 방식(`expect_state` 로 집기, 재송 시 `jobs.txn` 재사용)이 링크 쪽 기대와 어긋나지 않는지 — 를 적는다. 템플릿은 `.github/pull_request_template.md`.

---

## Task 4: `time_sched.py` — 매시 TIME 행

**파일**
- 생성: `modempi/modempi/lora/time_sched.py`
- 생성: `modempi/tests/test_lora_time_sched.py`

**인터페이스**
- 제공:
  ```python
  CLOCK_VALID_AFTER = 1_700_000_000     # v2 §5.2 clockValid 와 같은 기준

  class TimeScheduler:
      def __init__(self, store, *, clock=time.time, sleep=asyncio.sleep): ...
      async def run(self, stop: asyncio.Event) -> None
      def tick(self) -> str | None        # 넣었으면 job_id, 아니면 None
      def seconds_to_next(self) -> float  # 다음 :00:05 까지
  ```
- 규칙: 매시 `:00:05`에 `put_job(job_id=f"time-{epoch}", bld="", room=0, unit=0, type="TIME", payload={"epoch": epoch, "flags": flags}, priority=0, new_ver=None, uploaded=1)`. `flags`는 UTC 시(hour)가 `config["status_hour_utc"]`와 같으면 `TimeFlag.REQUEST_STATUS`. 시계가 유효하지 않으면(`clock() <= CLOCK_VALID_AFTER`) 넣지 않고 `log.warning`.

- [ ] **Step 1: 실패 테스트**

```python
import json

import pytest
from lora_proto import proto as P

from modempi.lora.time_sched import TimeScheduler
from modempi.store import SqliteStore

from .conftest import FakeClock


@pytest.fixture
def db():
    s = SqliteStore(":memory:")
    yield s
    s.close()


def test_tick_inserts_hourly_time_row_not_reported_to_main(db):
    clk = FakeClock(start=1_800_000_005.0)
    db.set_config({"status_hour_utc": 18})
    jid = TimeScheduler(db, clock=clk).tick()
    j = db.get_job(jid)
    assert (j.type, j.priority, j.uploaded, j.bld, j.unit) == ("TIME", 0, 1, "", 0)
    assert json.loads(j.payload) == {"epoch": int(clk.now), "flags": 0}


def test_request_status_flag_on_configured_hour(db):
    db.set_config({"status_hour_utc": 18})
    clk = FakeClock(start=1_800_064_805.0)   # UTC 18:00:05 인 시각
    import datetime as dt
    assert dt.datetime.fromtimestamp(clk.now, dt.UTC).hour == 18
    jid = TimeScheduler(db, clock=clk).tick()
    assert json.loads(db.get_job(jid).payload)["flags"] & int(P.TimeFlag.REQUEST_STATUS)


def test_no_time_row_before_ntp_sync(db):
    assert TimeScheduler(db, clock=lambda: 1_000.0).tick() is None
```

- [ ] **Step 2: 실패 확인** — `ModuleNotFoundError`

- [ ] **Step 3: 구현**

```python
"""매시 :00:05 TIME 행. 모뎀Pi 는 자기 NTP 시계로 낸다 — 메인Pi 없이도 (S6 spec §4.4)."""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import time
from collections.abc import Awaitable, Callable

from lora_proto import proto as P

from modempi.store import SqliteStore

log = logging.getLogger("lora.time")

CLOCK_VALID_AFTER = 1_700_000_000
OFFSET_S = 5  # 정시 + 5 초


class TimeScheduler:
    def __init__(self, store: SqliteStore, *, clock: Callable[[], float] = time.time,
                 sleep: Callable[[float], Awaitable] = asyncio.sleep) -> None:
        self.store, self._clock, self._sleep = store, clock, sleep

    def seconds_to_next(self) -> float:
        now = self._clock()
        return (3600 - (now - OFFSET_S) % 3600) % 3600 or 3600.0

    def tick(self) -> str | None:
        now = self._clock()
        if now <= CLOCK_VALID_AFTER:
            log.warning("시계가 아직 유효하지 않다(NTP 미동기) — TIME 생략")
            return None
        epoch = int(now)
        cfg = self.store.get_config() or {}
        hour = dt.datetime.fromtimestamp(epoch, dt.UTC).hour
        flags = int(P.TimeFlag.REQUEST_STATUS) if hour == cfg.get("status_hour_utc") else 0
        job_id = f"time-{epoch}"
        self.store.put_job(job_id=job_id, bld="", room=0, unit=0, type="TIME",
                           payload=json.dumps({"epoch": epoch, "flags": flags}),
                           priority=0, new_ver=None, uploaded=1)
        return job_id

    async def run(self, stop: asyncio.Event) -> None:
        self.tick()  # 기동 직후 1회 (v2 §8.4)
        while not stop.is_set():
            await self._sleep(self.seconds_to_next())
            if stop.is_set():
                return
            self.tick()
```

- [ ] **Step 4: 통과 확인** — 3 passed

- [ ] **Step 5: 스케줄 간격 테스트 추가**

```python
def test_seconds_to_next_lands_on_hh_00_05(db):
    clk = FakeClock(start=1_800_000_000.0)      # :00:00
    assert TimeScheduler(db, clock=clk).seconds_to_next() == 5.0
    clk.now += 5                                 # :00:05
    assert TimeScheduler(db, clock=clk).seconds_to_next() == 3600.0


# 파일 상단에 `import asyncio` 와 `pytestmark = pytest.mark.anyio` 를 추가한다.
async def test_run_inserts_one_row_per_hour(db):
    clk = FakeClock(start=1_800_000_005.0)
    stop = asyncio.Event()
    sched = TimeScheduler(db, clock=clk, sleep=clk.sleep)
    task = asyncio.create_task(sched.run(stop))
    await asyncio.sleep(0.05)          # FakeClock.sleep 이 시간을 앞당기며 세 번 돈다
    stop.set()
    task.cancel()
    made = [j for j in (db.get_job(f"time-{int(1_800_000_005 + 3600 * i)}") for i in range(3)) if j]
    assert len(made) >= 2 and all(j.type == "TIME" for j in made)
```

- [ ] **Step 6: 게이트 + 커밋**

```bash
git add modempi/modempi/lora/time_sched.py modempi/tests/test_lora_time_sched.py
git commit -m "feat(modempi): time_sched — 매시 :00:05 TIME 행, 시계 미동기 시 생략"
```

---

## Task 5: `uplink.py` — 업링크 파싱

**파일**
- 생성: `modempi/modempi/lora/uplink.py`
- 생성: `modempi/tests/test_lora_uplink.py`

**인터페이스**
- 제공:
  ```python
  class UplinkReader:
      def __init__(self, store, client, *, clock=time.time): ...
      async def run(self, stop: asyncio.Event) -> None
      def handle(self, ev: RxEvent) -> str | None   # "STATUS" | "HELLO" | None
  ```
- 규칙(S6 spec §4.5):
  - `decode_frame` 실패·NET_ID 불일치 → `log.warning` 후 버린다.
  - `STATUS` → `put_uplink({"kind": "STATUS", "bld": chr(h.bld), "room": h.room, "unit": h.unit, "mac": None, "ack_status": …, "sched_ver": …, "resv_ver": …, "exam_ver": …, "ident_ver": …, "batt_mv": …, "layout": …, "fw": …, "rssi": ev.rssi, "snr": ev.snr, "flags": st.flags, "uptime_h": st.uptime_h})`
  - `HELLO` → `put_uplink({"kind": "HELLO", "bld": 0, "room": 0, "unit": 0, "mac": hello.mac.hex(), "fw": …, "batt_mv": …, "rssi": …, "snr": …})` — **MAC은 소문자 hex 문자열**(계약 ⑥ 인코딩 규칙, bytes 는 JSON 불가).
  - `ACK` 가 rx 로 오면(늦은 ACK) `log.info` 만.
  - `STATUS.flags & CLOCK_STALE` → 그 노드로 **타겟 TIME 1건** 큐잉: `put_job(job_id=f"time-{epoch}-{bld}{room}-{unit}", bld=chr(h.bld), room=h.room, unit=h.unit, type="TIME", payload={"epoch": epoch, "flags": 0}, priority=0, new_ver=None, uploaded=1)`.

- [ ] **Step 1: 실패 테스트**

```python
import pytest
from lora_proto import codec as C
from lora_proto import proto as P

from modempi.lora.modem_client import RxEvent
from modempi.lora.uplink import UplinkReader
from modempi.store import SqliteStore

from .conftest import FakeClock, frame

pytestmark = pytest.mark.anyio


@pytest.fixture
def db():
    s = SqliteStore(":memory:")
    yield s
    s.close()


def status_frame(flags=0):
    ack = C.Ack(P.AckStatus.OK, 0, 3900, 2, 1, 0, 1, 20, int(P.Layout.CLASS))
    return frame(P.Type.STATUS, C.Status(ack, -90, 20, flags, 42),
                 bld=ord("E"), room=301, unit=1, txn=0, flags=0)


def test_status_becomes_uplink_row(db):
    r = UplinkReader(db, client=None)
    assert r.handle(RxEvent(status_frame(), -95, 4.0)) == "STATUS"
    [row] = db.pending_uplinks()
    assert row.body["kind"] == "STATUS" and row.body["bld"] == "E" and row.body["room"] == 301
    assert row.body["sched_ver"] == 2 and row.body["rssi"] == -95 and row.body["uptime_h"] == 42


def test_hello_mac_is_hex_string(db):
    r = UplinkReader(db, client=None)
    f = frame(P.Type.HELLO, C.Hello(bytes.fromhex("a0b1c2d3e4f5"), 20, 4000),
              bld=P.BLD_UNPROVISIONED, room=0, unit=0, txn=0, flags=0)
    assert r.handle(RxEvent(f, -100, 3.0)) == "HELLO"
    [row] = db.pending_uplinks()
    assert row.body["mac"] == "a0b1c2d3e4f5" and row.body["bld"] == 0


def test_clock_stale_queues_targeted_time(db):
    clk = FakeClock()
    r = UplinkReader(db, client=None, clock=clk)
    r.handle(RxEvent(status_frame(int(P.StatusFlag.CLOCK_STALE)), -95, 4.0))
    job = db.pick_next()
    assert (job.type, job.bld, job.room, job.unit, job.uploaded) == ("TIME", "E", 301, 1, 1)


def test_garbage_frame_is_dropped(db):
    assert UplinkReader(db, client=None).handle(RxEvent(b"\x00\x01\x02", -95, 4.0)) is None
    assert db.pending_uplinks() == []
```

- [ ] **Step 2: 실패 확인** — `ModuleNotFoundError`

- [ ] **Step 3: 구현**

```python
"""rx 프레임 → STATUS/HELLO 업링크 행. 올리는 것은 링크(wj) (S6 spec §4.5)."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable

from lora_proto import codec as C
from lora_proto import proto as P

from modempi.lora.modem_client import ModemClient, RxEvent
from modempi.store import SqliteStore

log = logging.getLogger("lora.uplink")


class UplinkReader:
    def __init__(self, store: SqliteStore, client: ModemClient | None, *,
                 clock: Callable[[], float] = time.time) -> None:
        self.store, self.client, self._clock = store, client, clock

    async def run(self, stop: asyncio.Event) -> None:
        assert self.client is not None
        while not stop.is_set():
            ev = await self.client.rx.get()
            try:
                self.handle(ev)
            except Exception:
                log.exception("업링크 처리 실패 — 버리고 계속")

    def handle(self, ev: RxEvent) -> str | None:
        try:
            h, pb = C.decode_frame(ev.frame)
            obj = C.decode_payload(h.type, pb)
        except C.FrameError as e:
            log.warning("업링크 프레임 버림: %s", e)
            return None
        if h.type == P.Type.STATUS:
            self._status(h, obj, ev)
            return "STATUS"
        if h.type == P.Type.HELLO:
            self.store.put_uplink({"kind": "HELLO", "bld": 0, "room": 0, "unit": 0,
                                   "mac": obj.mac.hex(), "fw": obj.fw, "batt_mv": obj.batt_mv,
                                   "rssi": ev.rssi, "snr": ev.snr})
            return "HELLO"
        log.info("요청하지 않은 %s 프레임 — 무시", P.Type(h.type).name)
        return None

    def _status(self, h: C.Header, st: C.Status, ev: RxEvent) -> None:
        a = st.ack
        self.store.put_uplink({
            "kind": "STATUS", "bld": chr(h.bld), "room": h.room, "unit": h.unit, "mac": None,
            "ack_status": int(a.status), "ack_detail": int(a.detail), "batt_mv": a.batt_mv,
            "sched_ver": a.sched_ver, "resv_ver": a.resv_ver, "exam_ver": a.exam_ver,
            "ident_ver": a.ident_ver, "fw": a.fw, "layout": a.layout,
            "rssi": ev.rssi, "snr": ev.snr, "flags": st.flags, "uptime_h": st.uptime_h,
        })
        if st.flags & int(P.StatusFlag.CLOCK_STALE):
            epoch = int(self._clock())
            self.store.put_job(job_id=f"time-{epoch}-{chr(h.bld)}{h.room}-{h.unit}",
                               bld=chr(h.bld), room=h.room, unit=h.unit, type="TIME",
                               payload=json.dumps({"epoch": epoch, "flags": 0}),
                               priority=0, new_ver=None, uploaded=1)
```

- [ ] **Step 4: 통과 확인** — 4 passed

- [ ] **Step 5: 게이트 + 커밋**

```bash
git add modempi/modempi/lora/uplink.py modempi/tests/test_lora_uplink.py
git commit -m "feat(modempi): uplink — STATUS/HELLO 를 업링크 행으로, CLOCK_STALE 타겟 TIME"
```

---

## Task 6: `pipeline.py` — 태스크 묶음

**파일**
- 생성: `modempi/modempi/lora/pipeline.py`
- 생성: `modempi/tests/test_lora_pipeline.py`

**인터페이스**
- 제공:
  ```python
  PRUNE_EVERY_S = 86400.0
  PRUNE_KEEP_S = 7 * 86400.0

  class Pipeline:
      def __init__(self, store, transport, *, clock=time.time, sleep=asyncio.sleep): ...
      async def run(self, stop: asyncio.Event) -> None
  ```
- 하는 일:
  1. `ModemClient.start()` → `store.set_meta("modem_fw", client.fw)` (링크가 hello 에 실어 올린다, 계약 ⑦)
  2. `cfg(**store.get_config()["radio"])` — config 가 아직 없으면 올 때까지 기다린다(`on_config_changed`가 `asyncio.Event`를 세움)
  3. `on_config_changed` → 이벤트만 세우고, 실제 `cfg` 재전송은 파이프라인 태스크가 한다(**콜백 안에서 await 하지 않는다** — 링크 수신 루프가 막힌다. PR #29 wj 리뷰 2번)
  4. worker / time_sched / uplink 세 태스크 기동, `stop` 으로 함께 종료
  5. 하루 1회 `store.prune(older_than=PRUNE_KEEP_S)`

- [ ] **Step 1: 실패 테스트 — 저장부터 결과까지 한 바퀴**

```python
import asyncio
import json

import pytest
from lora_proto import proto as P

from modempi.lora.fake_modem import FakeModem
from modempi.lora.pipeline import Pipeline
from modempi.store import SqliteStore

pytestmark = pytest.mark.anyio

SLOT = {"day": 1, "s_h": 9, "s_m": 0, "e_h": 9, "e_m": 50, "type": 1,
        "subject": "자료구조", "professor": "김교수"}


async def test_job_goes_out_and_result_lands_in_store():
    db = SqliteStore(":memory:")
    modem = FakeModem()
    modem.add_node(ord("E"), 301, 1, sched_ver=2)
    db.set_config({"net_id": P.NET_ID, "radio": {"sf": 9, "bw": 125.0, "cr": 5, "tx_dbm": 14,
                                                 "preamble_wake_ms": 3000},
                   "nodes": [{"bld": "E", "room": 301, "unit": 1}], "status_hour_utc": 18})
    db.put_job(job_id="10", bld="E", room=301, unit=1, type="SLOT_SET",
               payload=json.dumps(SLOT), priority=3, new_ver=3)
    stop = asyncio.Event()
    task = asyncio.create_task(Pipeline(db, modem).run(stop))
    for _ in range(100):
        await asyncio.sleep(0.02)
        if db.get_job("10").state == "acked":
            break
    stop.set()
    await asyncio.wait_for(task, 3)
    assert db.get_job("10").state == "acked"
    assert db.get_meta("modem_fw") == "gw-2.0.0"
    db.close()
```

- [ ] **Step 2: 실패 확인** — `ModuleNotFoundError`

- [ ] **Step 3: 구현**

```python
"""worker · time_sched · uplink 를 한 묶음으로 기동/종료 (S6 spec §4.6)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable

from modempi.lora.modem_client import ModemClient
from modempi.lora.time_sched import TimeScheduler
from modempi.lora.transport import LineTransport
from modempi.lora.uplink import UplinkReader
from modempi.lora.worker import Worker
from modempi.store import SqliteStore

log = logging.getLogger("lora.pipeline")

PRUNE_EVERY_S = 86400.0
PRUNE_KEEP_S = 7 * 86400.0


class Pipeline:
    def __init__(self, store: SqliteStore, transport: LineTransport, *,
                 clock: Callable[[], float] = time.time,
                 sleep: Callable[[float], Awaitable] = asyncio.sleep) -> None:
        self.store, self._transport = store, transport
        self._clock, self._sleep = clock, sleep
        self._config_changed = asyncio.Event()

    async def run(self, stop: asyncio.Event) -> None:
        client = ModemClient(self._transport)
        await client.start()
        if client.fw:
            self.store.set_meta("modem_fw", client.fw)
        self.store.on_config_changed(lambda cfg: self._config_changed.set())  # 콜백은 신호만
        await self._apply_config(client, wait=True)
        worker = Worker(self.store, client, clock=self._clock, sleep=self._sleep)
        sched = TimeScheduler(self.store, clock=self._clock, sleep=self._sleep)
        reader = UplinkReader(self.store, client, clock=self._clock)
        tasks = [asyncio.create_task(t) for t in (
            worker.run(stop), sched.run(stop), reader.run(stop),
            self._config_loop(client, stop), self._prune_loop(stop),
        )]
        try:
            await stop.wait()
        finally:
            for t in tasks:
                t.cancel()
            for t in tasks:
                with contextlib.suppress(asyncio.CancelledError):
                    await t
            await client.stop()

    async def _apply_config(self, client: ModemClient, *, wait: bool) -> None:
        cfg = self.store.get_config()
        while cfg is None and wait:
            log.info("메인Pi config 대기 중 — 받을 때까지 송신하지 않는다")
            await self._config_changed.wait()
            self._config_changed.clear()
            cfg = self.store.get_config()
        if cfg is not None:
            await client.cfg(**cfg.get("radio", {}))

    async def _config_loop(self, client: ModemClient, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self._config_changed.wait()
            self._config_changed.clear()
            await self._apply_config(client, wait=False)

    async def _prune_loop(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self._sleep(PRUNE_EVERY_S)
            if stop.is_set():
                return
            n = self.store.prune(older_than=PRUNE_KEEP_S)
            if n:
                log.info("오래된 행 %d 개 정리", n)
```

- [ ] **Step 4: 통과 확인** — 1 passed

- [ ] **Step 5: config 대기·재전송 테스트 추가**

```python
async def test_waits_for_config_then_sends_cfg_and_resends_on_change():
    db = SqliteStore(":memory:")
    modem = FakeModem()
    modem.add_node(ord("E"), 301, 1)
    stop = asyncio.Event()
    task = asyncio.create_task(Pipeline(db, modem).run(stop))
    await asyncio.sleep(0.05)
    assert modem.cfg_count == 0                      # config 없으면 cfg 를 안 보낸다
    db.set_config({"radio": {"sf": 9, "bw": 125.0, "cr": 5, "tx_dbm": 14, "preamble_wake_ms": 3000}})
    await asyncio.sleep(0.05)
    assert modem.cfg_count == 1
    db.set_config({"radio": {"sf": 10, "bw": 125.0, "cr": 5, "tx_dbm": 14, "preamble_wake_ms": 3000}})
    await asyncio.sleep(0.05)
    assert modem.cfg_count == 2 and modem.radio["sf"] == 10
    stop.set()
    await asyncio.wait_for(task, 3)
    db.close()
```
이 테스트를 위해 `fake_modem.py` 를 먼저 고친다(S1 영역, cw 소유). `__init__` 에 `self.cfg_count = 0` 과 `self.radio: dict = {}` 를 추가하고, `write_line` 의 `cfg` 분기를 다음으로 바꾼다:

```python
        elif op == "cfg":  # §4.2: 응답 없음. 적용만 한다.
            self.cfg_count += 1
            self.radio = {k: v for k, v in msg.items() if k != "op"}
```

- [ ] **Step 6: 게이트 + 커밋 + PR 2 (Task 4~6)**

```bash
cd modempi && uv run pytest -q && uv run ruff check . && uv run ruff format --check .
git add modempi/modempi/lora/pipeline.py modempi/modempi/lora/fake_modem.py modempi/tests/test_lora_pipeline.py
git commit -m "feat(modempi): pipeline — worker·time_sched·uplink 묶음 기동, config 대기·재전송, 일일 prune"
git push origin cw
```

---

## Task 7: `modem.py`(실물 시리얼) + `main.py`(공용)

**파일**
- 생성: `modempi/modempi/lora/modem.py`
- 생성: `modempi/main.py` (**공용 — wj 리뷰 필수**)
- 생성: `modempi/tests/test_lora_modem_serial.py`
- 수정: `modempi/pyproject.toml` (`uv add pyserial-asyncio`)

**인터페이스**
- 제공:
  ```python
  class SerialTransport:                  # LineTransport 구현
      def __init__(self, port: str, *, baud: int = 115200, open_fn=None, reconnect_s: float = 2.0): ...
      async def open(self) -> None
      async def write_line(self, line: str) -> None
      async def read_line(self) -> str
      async def close(self) -> None

  async def main() -> None               # modempi/main.py: 링크(wj) + 파이프라인(cw)
  ```
- `open_fn`은 테스트 주입점이다. 기본값은 `serial_asyncio.open_serial_connection(url=port, baudrate=baud)`이고, 테스트는 TCP 소켓 한 쌍(`asyncio.start_server` + `asyncio.open_connection`)을 돌려주는 함수를 넣는다 — **윈도우에는 pty가 없으므로 소켓으로 대신한다.**
- 읽다 끊기면(`ConnectionResetError`·`SerialException`) `reconnect_s` 뒤 다시 연다. 재연결 후 모뎀이 `ready`를 보내면 `ModemClient`가 `cfg`를 다시 보낸다(Task 1에 이미 있음).
- 줄 길이 상한 1,024 B(v2 §4.5) 초과 라인은 버리고 `log.warning`.

- [ ] **Step 1: 실패 테스트 (소켓 한 쌍으로 시리얼 흉내)**

```python
import asyncio

import pytest

from modempi.lora.modem import SerialTransport

pytestmark = pytest.mark.anyio


@pytest.fixture
async def paired():
    """서버 쪽을 '모뎀'으로 쓰는 TCP 한 쌍. 시리얼 대신 (reader, writer) 를 주입한다."""
    got = {}

    async def handle(reader, writer):
        got["reader"], got["writer"] = reader, writer

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    async def open_fn():
        return await asyncio.open_connection("127.0.0.1", port)

    yield open_fn, got
    server.close()
    await server.wait_closed()


async def test_write_and_read_one_line(paired):
    open_fn, got = paired
    t = SerialTransport("dummy", open_fn=open_fn)
    await t.open()
    await asyncio.sleep(0.02)
    await t.write_line('{"op":"ping"}')
    assert (await got["reader"].readline()).decode().strip() == '{"op":"ping"}'
    got["writer"].write(b'{"op":"pong","uptime_s":7}\n')
    await got["writer"].drain()
    assert await t.read_line() == '{"op":"pong","uptime_s":7}'
    await t.close()


async def test_reconnects_after_peer_drops(paired):
    open_fn, got = paired
    t = SerialTransport("dummy", open_fn=open_fn, reconnect_s=0.01)
    await t.open()
    await asyncio.sleep(0.02)
    got["writer"].close()                      # 모뎀이 사라짐(USB 뽑힘)
    await asyncio.sleep(0.05)
    got["writer"].write(b'{"op":"ready","fw":"gw-2.0.0"}\n')
    await got["writer"].drain()
    assert (await asyncio.wait_for(t.read_line(), 2)).startswith('{"op":"ready"')
    await t.close()
```

- [ ] **Step 2: 실패 확인** — `ModuleNotFoundError: modempi.lora.modem`

- [ ] **Step 3: 의존성 추가**

```bash
cd modempi && uv add pyserial-asyncio
git add pyproject.toml uv.lock
```

- [ ] **Step 4: 구현**

```python
"""실물 모뎀 시리얼 LineTransport — 포트 열기·재연결. 프로토콜은 ModemClient 가 안다 (S6 spec §4)."""

from __future__ import annotations

import asyncio
import logging

log = logging.getLogger("lora.serial")

MAX_LINE = 1024


async def _open_serial(port: str, baud: int):
    import serial_asyncio  # 실기에서만 필요

    return await serial_asyncio.open_serial_connection(url=port, baudrate=baud)


class SerialTransport:
    def __init__(self, port: str, *, baud: int = 115200, open_fn=None, reconnect_s: float = 2.0) -> None:
        self._port, self._baud, self._reconnect_s = port, baud, reconnect_s
        self._open_fn = open_fn or (lambda: _open_serial(port, baud))
        self._r: asyncio.StreamReader | None = None
        self._w: asyncio.StreamWriter | None = None
        self._closed = False

    async def open(self) -> None:
        self._r, self._w = await self._open_fn()

    async def _reopen(self) -> None:
        while not self._closed:
            await asyncio.sleep(self._reconnect_s)
            try:
                await self.open()
                log.info("모뎀 시리얼 재연결 성공: %s", self._port)
                return
            except OSError as e:
                log.warning("모뎀 시리얼 재연결 실패(%s) — 다시 시도", e)

    async def write_line(self, line: str) -> None:
        if self._w is None:
            raise RuntimeError("시리얼이 아직 열리지 않았다")
        self._w.write(line.encode() + b"\n")
        await self._w.drain()

    async def read_line(self) -> str:
        while not self._closed:
            if self._r is None:
                await self._reopen()
                continue
            try:
                raw = await self._r.readline()
            except (ConnectionResetError, OSError) as e:
                log.warning("모뎀 시리얼 끊김(%s) — 재연결", e)
                self._r = None
                continue
            if raw == b"":                      # EOF = 포트가 사라짐
                self._r = None
                continue
            if len(raw) > MAX_LINE:
                log.warning("시리얼 라인 %d B > %d — 버림", len(raw), MAX_LINE)
                continue
            return raw.decode(errors="replace").strip()
        raise asyncio.CancelledError

    async def close(self) -> None:
        self._closed = True
        if self._w is not None:
            self._w.close()
```

- [ ] **Step 5: 통과 확인** — 2 passed

- [ ] **Step 6: `main.py` — 링크 + 파이프라인 한 프로세스 (공용)**

```python
"""모뎀Pi 서비스 진입점. 링크(wj)와 파이프라인(cw)이 store 하나를 공유한다 (modempi/CLAUDE.md).

CLI: modempi --store /var/lib/modempi/jobs.db --port /dev/lora-modem
     modempi --store ./jobs.db --fake
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os

from modempi.link import run as link_run
from modempi.lora.fake_modem import FakeModem
from modempi.lora.modem import SerialTransport
from modempi.lora.pipeline import Pipeline
from modempi.store import SqliteStore


def _args() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="modempi")
    p.add_argument("--store", default=os.environ.get("MODEMPI_STORE", "/var/lib/modempi/jobs.db"))
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--port", help="모뎀 시리얼 포트 (예 /dev/lora-modem)")
    g.add_argument("--fake", action="store_true", help="가짜 모뎀으로 기동 (하드웨어 없이)")
    return p.parse_args()


async def _main() -> None:
    a = _args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    store = SqliteStore(a.store)
    transport = FakeModem() if a.fake else SerialTransport(a.port)
    if not a.fake:
        await transport.open()
    stop = asyncio.Event()
    try:
        await asyncio.gather(link_run.main(store), Pipeline(store, transport).run(stop))
    finally:
        stop.set()
        store.close()


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
```
`pyproject.toml`에 진입점 추가:
```toml
[project.scripts]
modempi = "modempi.main:main"
```

- [ ] **Step 7: 게이트 + 커밋 + PR 3 (Task 7)**

```bash
cd modempi && uv run pytest -q && uv run ruff check . && uv run ruff format --check .
git add modempi/modempi/lora/modem.py modempi/main.py modempi/pyproject.toml modempi/uv.lock modempi/tests/test_lora_modem_serial.py
git commit -m "feat(modempi): 실물 시리얼 SerialTransport + main.py 진입점 (링크·파이프라인 공용)"
git push origin cw
```
PR 본문에 **wj 리뷰 요청**을 명시한다: `main.py`가 공용이고, `link.run.main(store)` 호출 형태와 `MODEMPI_STORE` 를 main 이 여는 것(S5 spec §6 ③, PR #29 wj 코멘트 3)이 맞는지.

---

## 완료 기준 (S6 spec §8)

- [ ] 가짜 모뎀 시나리오 전부 녹색: acked / DUP / GAP / BUSY / BAD_CRC / STORE_FAIL / no_ack×3 / cad_busy / FILE_MISSING 재송 / **ACK 유실 후 같은 TXN 재송 = DUP** / 재기동 후 같은 TXN / TIME 누적 → 1건만 송신 / CLOCK_STALE 타겟 TIME / TXN 1→255→1
- [ ] `ModemClient.tx` 동시 호출이 `RuntimeError`
- [ ] 로컬 큐 100건 연속 처리에 `busy` 오류 0건
- [ ] `uv run pytest -q` 녹색, ruff clean, CI `modempi` job 통과
- [ ] `docs/progress.html` cw-09 체크 + PR 번호
- [ ] (cw-10에서) 메인Pi 웹 저장 → 모뎀Pi(fake) → `job_result` 왕복을 Pi 2대로 확인

## 실행 순서 요약

| PR | Task | 리뷰어 |
|---|---|---|
| 1/3 | 1·2·3 (ModemClient·preprocess·worker) | wj (계약 ⑦ 사용 방식) |
| 2/3 | 4·5·6 (time_sched·uplink·pipeline) | wj |
| 3/3 | 7 (modem.py·main.py) | **wj 필수** — `main.py` 공용 |

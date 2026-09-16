# S5 — 모뎀Pi 링크 구현 계획 (plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

- 생성일시: 2026-09-16
- 기준 spec: `docs/specs/2026-09-16-s5-modempi-link-design.md` (+ 계약 ⑥ `docs/specs/2026-09-09-roadmap-design.md` §4.2·인코딩 규칙 표, 계약 ⑦ §4.3, 허브 동작 `docs/specs/2026-09-14-s2-server-design.md` §2.4)
- 담당: wj @leemonta9482. 브랜치 `feature/s5-link`. 커밋 scope `feat(modempi)`. PR은 사용자 지시 시.

**Goal:** 모뎀Pi가 메인Pi 허브에 WS로 붙어 `config`·`job`·`cancel`·`time_now`를 받아 JobStore에 넣고, 파이프라인이 끝낸 결과·업링크를 `job_result`·`uplink`로 올리며, 끊기면 백오프로 재접속해 밀린 것을 몰아 올리는 링크를 — `store.py`(cw-08) 없이도 Protocol + 메모리 fake로 — 완성한다.

**Architecture:** `modempi/link/` 4파일. `store_port.py`가 링크가 요구하는 계약 ⑦ 인터페이스(Protocol)이고, `client.py`의 `LinkClient`가 접속·hello·수신 루프·재접속·watchdog을, `uploader.py`의 `Uploader`가 1 s 폴링 송신을 맡는다. 셋 다 `websockets` 하나에 의존하고 `lora/`는 import하지 않는다. 테스트는 `server/tests/fake_hub.py`(파일 경로로 import) + `tests/fake_store.py`(메모리) 상대. 시간(`clock`)과 대기(`sleep`)는 주입해 백오프·무응답 테스트가 실제로 기다리지 않게 한다.

**Tech Stack:** Python 3.12 · uv · asyncio · `websockets` ≥13 · pytest + anyio(asyncio) · ruff

## Global Constraints

- `link/`는 `lora/`를 import하지 않는다. `store.py`를 우회해 SQLite를 열지 않는다(modempi/CLAUDE.md). 이 plan에서는 `store.py`가 없으므로 `JobStore` Protocol만 소비한다.
- 계약 ⑥ 메시지 키·인코딩은 로드맵 §4.2 표 그대로: `job_id`는 정수(저장은 `str`), `job.payload`는 JSON 문자열로 저장(검증 없음), `job_result` 필드 = `job_id, state, ack_status, ack_detail, attempts, txn, rssi, snr, sched_ver, resv_ver, exam_ver, ident_ver, batt_mv, layout, fw, last_error, finished_at`.
- 같은 `job_id` 재수신은 무시하되 `job_accepted`는 회신. `cancel`은 `received`만. `time_now` → TIME 행 `uploaded=1`. `ping` → `pong`.
- 백오프 1→2→4→8→16→30 s ±20 %, 성공(config 수신) 시 리셋. 4001 → 즉시 30 s. config 10 s 타임아웃. 서버 메시지 60 s 무응답 → 재접속. 링크는 ping을 보내지 않는다.
- 업로더 1 s 폴링, 배치 ≤ 100, `job_result` 먼저 `uplink` 다음, write 완료 즉시 `mark_*`. `cancelled` 행 → `state="failed", last_error="cancelled"`.
- 토큰은 로그에 마스킹. env: `MODEMPI_MAIN_URL`, `MODEMPI_ID`, `MODEMPI_TOKEN`, `MODEMPI_STORE`.
- uv only; ruff 100/py312; 커밋 `feat(modempi): ...`, AI 표기 없음. 모든 명령은 `modempi/`에서.
- `server/tests/fake_hub.py`는 additive 변경만(`start(port=0)` 인자 추가).

---

## 파일 구조

```
modempi/
├── pyproject.toml                  # + websockets>=13 (runtime)
├── modempi/link/
│   ├── __init__.py
│   ├── store_port.py               # JobRow, UplinkRow, JobStore Protocol
│   ├── client.py                   # LinkClient, AuthError, ProtocolError
│   ├── uploader.py                 # Uploader, build_job_result()
│   └── run.py                      # LinkSettings.from_env(), main(store)
└── tests/
    ├── conftest.py                 # + FakeHub 파일 import, fake_store/hub/link 픽스처, FakeClock
    ├── fake_store.py               # MemoryStore (JobStore 구현)
    ├── test_link_store_port.py     # Task 1
    ├── test_link_client.py         # Task 2
    ├── test_link_uploader.py       # Task 3
    ├── test_link_reconnect.py      # Task 4
    └── test_link_run.py            # Task 5
server/tests/fake_hub.py            # start(port: int = 0)  (additive)
```

---

### Task 1: `store_port.py` Protocol + 메모리 fake store + 픽스처 기반

**Files:**
- Create: `modempi/modempi/link/__init__.py`, `modempi/modempi/link/store_port.py`, `modempi/tests/fake_store.py`
- Modify: `modempi/pyproject.toml` (websockets), `modempi/tests/conftest.py` (FakeHub 파일 import + 픽스처), `server/tests/fake_hub.py` (`start(port=0)`)
- Test: `modempi/tests/test_link_store_port.py`

**Interfaces:**
- Produces: `JobRow(job_id, state, attempts, txn, ack_status, ack_detail, rssi, snr, node_vers, batt_mv, layout, fw, last_error, finished_at)`, `UplinkRow(id, body)`, `JobStore` Protocol(7 함수, spec §4.2 시그니처), `MemoryStore` with extra test hooks `.jobs: dict[str, dict]`, `.config: dict | None`, `.finish(job_id, **fields)` (파이프라인 흉내: state/결과 필드/finished_at 세팅), `.put_uplink(body) -> int`. conftest: `FakeHub`, `fake_hub` 픽스처(`token="secret"`), `store` 픽스처, `FakeClock`(`now`, `sleep`), `link_factory`.

- [ ] **Step 1: 의존·fake_hub additive**

`modempi/pyproject.toml` `dependencies`에 `"websockets>=13"` 추가. `uv sync`.

`server/tests/fake_hub.py`의 `start`를 포트를 받을 수 있게(기본 0 유지):
```python
    async def start(self, port: int = 0) -> int:
        self._server = await serve(self._handle, "127.0.0.1", port)
```

- [ ] **Step 2: 실패하는 테스트**

`modempi/tests/test_link_store_port.py`:
```python
from modempi.link.store_port import JobRow, JobStore, UplinkRow

from .fake_store import MemoryStore


def test_memory_store_satisfies_protocol():
    s: JobStore = MemoryStore()  # 타입상 만족 — runtime 은 아래 동작으로 확인
    assert isinstance(s, MemoryStore)


def test_put_job_is_idempotent_and_returns_false_on_dup():
    s = MemoryStore()
    assert s.put_job(job_id="7", bld="E", room=301, unit=1, type="SLOT_SET",
                     payload='{"day":1}', priority=3, new_ver=1) is True
    assert s.put_job(job_id="7", bld="E", room=301, unit=1, type="SLOT_SET",
                     payload='{"day":9}', priority=3, new_ver=2) is False
    assert s.jobs["7"]["payload"] == '{"day":1}' and s.jobs["7"]["state"] == "received"


def test_cancel_only_received_and_sets_finished_at():
    s = MemoryStore()
    s.put_job(job_id="1", bld="E", room=301, unit=1, type="CMD", payload="{}", priority=3, new_ver=None)
    assert s.cancel_job("1") is True and s.jobs["1"]["state"] == "cancelled"
    assert s.jobs["1"]["finished_at"] is not None
    assert s.cancel_job("1") is False  # 이미 cancelled
    assert s.cancel_job("nope") is False


def test_pending_results_and_mark_uploaded():
    s = MemoryStore()
    for i in ("1", "2", "3"):
        s.put_job(job_id=i, bld="E", room=301, unit=1, type="CMD", payload="{}", priority=3, new_ver=None)
    s.put_job(job_id="time-1", bld="", room=0, unit=0, type="TIME", payload="{}", priority=0,
              new_ver=None, uploaded=1)
    s.finish("1", state="acked", ack_status=0, rssi=-90)
    s.finish("2", state="failed", last_error="no_ack")
    s.finish("time-1", state="acked")
    rows = s.pending_results()
    assert [r.job_id for r in rows] == ["1", "2"]  # 3 은 안 끝남, time-1 은 uploaded=1
    assert isinstance(rows[0], JobRow) and rows[0].rssi == -90
    s.mark_uploaded(["1"])
    assert [r.job_id for r in s.pending_results()] == ["2"]
    assert s.pending_results(limit=0) == []


def test_uplinks_roundtrip():
    s = MemoryStore()
    a = s.put_uplink({"kind": "HELLO", "mac": "aabbccddeeff"})
    b = s.put_uplink({"kind": "STATUS", "bld": "E"})
    rows = s.pending_uplinks()
    assert [r.id for r in rows] == [a, b] and isinstance(rows[0], UplinkRow)
    s.mark_uplinks_uploaded([a])
    assert [r.id for r in s.pending_uplinks()] == [b]


def test_set_config():
    s = MemoryStore()
    s.set_config({"net_id": 75, "nodes": []})
    assert s.config == {"net_id": 75, "nodes": []}
```

Run: `uv run pytest tests/test_link_store_port.py -q` → FAIL (`modempi.link` 없음).

- [ ] **Step 3: 구현**

`modempi/modempi/link/__init__.py`: 빈 파일.

`modempi/modempi/link/store_port.py`:
```python
"""계약 ⑦ JobStore 중 링크가 쓰는 인터페이스 (S5 spec §4.2). 실물은 modempi/store.py (cw-08)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class JobRow:
    job_id: str
    state: str  # acked | failed | cancelled
    attempts: int = 0
    txn: int | None = None
    ack_status: int | None = None
    ack_detail: int | None = None
    rssi: int | None = None
    snr: float | None = None
    node_vers: str | None = None  # JSON {"sched","resv","exam","ident"}
    batt_mv: int | None = None
    layout: int | None = None
    fw: int | None = None
    last_error: str | None = None
    finished_at: float | None = None


@dataclass
class UplinkRow:
    id: int
    body: dict


class JobStore(Protocol):
    def put_job(
        self,
        *,
        job_id: str,
        bld: str,
        room: int,
        unit: int,
        type: str,
        payload: str,
        priority: int,
        new_ver: int | None,
        uploaded: int = 0,
    ) -> bool: ...
    def cancel_job(self, job_id: str) -> bool: ...
    def pending_results(self, limit: int = 100) -> list[JobRow]: ...
    def mark_uploaded(self, job_ids: list[str]) -> None: ...
    def set_config(self, config: dict) -> None: ...
    def pending_uplinks(self, limit: int = 100) -> list[UplinkRow]: ...
    def mark_uplinks_uploaded(self, ids: list[int]) -> None: ...
```

`modempi/tests/fake_store.py`:
```python
"""메모리 JobStore — 링크 테스트용. 계약 ⑦ 의미만 흉내 낸다 (S5 spec §4.2)."""

from __future__ import annotations

import time

from modempi.link.store_port import JobRow, UplinkRow

_ROW_FIELDS = (
    "state", "attempts", "txn", "ack_status", "ack_detail", "rssi", "snr", "node_vers",
    "batt_mv", "layout", "fw", "last_error", "finished_at",
)


class MemoryStore:
    def __init__(self) -> None:
        self.jobs: dict[str, dict] = {}
        self.uplinks: list[dict] = []
        self.config: dict | None = None
        self._next_uplink = 1

    # ---- 링크가 쓰는 7 함수 ----
    def put_job(self, *, job_id, bld, room, unit, type, payload, priority, new_ver, uploaded=0) -> bool:
        if job_id in self.jobs:
            return False
        self.jobs[job_id] = {
            "job_id": job_id, "bld": bld, "room": room, "unit": unit, "type": type,
            "payload": payload, "priority": priority, "new_ver": new_ver,
            "state": "received", "attempts": 0, "txn": None, "ack_status": None,
            "ack_detail": None, "rssi": None, "snr": None, "node_vers": None,
            "batt_mv": None, "layout": None, "fw": None, "last_error": None,
            "received_at": time.time(), "finished_at": None, "uploaded": uploaded,
        }
        return True

    def cancel_job(self, job_id: str) -> bool:
        j = self.jobs.get(job_id)
        if j is None or j["state"] != "received":
            return False
        j["state"], j["finished_at"] = "cancelled", time.time()
        return True

    def pending_results(self, limit: int = 100) -> list[JobRow]:
        rows = [j for j in self.jobs.values() if j["finished_at"] is not None and not j["uploaded"]]
        rows.sort(key=lambda j: j["finished_at"])
        return [JobRow(job_id=j["job_id"], **{k: j[k] for k in _ROW_FIELDS}) for j in rows[:limit]]

    def mark_uploaded(self, job_ids: list[str]) -> None:
        for i in job_ids:
            if i in self.jobs:
                self.jobs[i]["uploaded"] = 1

    def set_config(self, config: dict) -> None:
        self.config = dict(config)

    def pending_uplinks(self, limit: int = 100) -> list[UplinkRow]:
        return [UplinkRow(u["id"], u["body"]) for u in self.uplinks if not u["uploaded"]][:limit]

    def mark_uplinks_uploaded(self, ids: list[int]) -> None:
        for u in self.uplinks:
            if u["id"] in ids:
                u["uploaded"] = 1

    # ---- 파이프라인 흉내 (테스트 전용) ----
    def finish(self, job_id: str, **fields) -> None:
        j = self.jobs[job_id]
        j.update(fields)
        j.setdefault("finished_at", None)
        if j["finished_at"] is None:
            j["finished_at"] = time.time()

    def put_uplink(self, body: dict) -> int:
        i = self._next_uplink
        self._next_uplink += 1
        self.uplinks.append({"id": i, "body": body, "uploaded": 0})
        return i
```

`modempi/tests/conftest.py`에 추가 (기존 내용 유지):
```python
import importlib.util
import pathlib

# server/tests/fake_hub.py 를 파일 경로로 import — modempi/tests 도 `tests` 패키지라 이름이 겹친다.
_FAKE_HUB = pathlib.Path(__file__).resolve().parents[2] / "server" / "tests" / "fake_hub.py"
_spec = importlib.util.spec_from_file_location("server_fake_hub", _FAKE_HUB)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
FakeHub = _mod.FakeHub

from .fake_store import MemoryStore  # noqa: E402


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
```
(`import asyncio` 상단 추가.)

- [ ] **Step 4: 통과 + 커밋**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check .` → PASS (기존 29 + 6).

```bash
git add modempi/pyproject.toml modempi/uv.lock modempi/modempi/link modempi/tests/fake_store.py modempi/tests/conftest.py modempi/tests/test_link_store_port.py server/tests/fake_hub.py
git commit -m "feat(modempi): link/store_port — 계약 ⑦ 링크 측 Protocol + 메모리 fake store"
```

---

### Task 2: `LinkClient` — 접속·hello·config·수신 처리

**Files:**
- Create: `modempi/modempi/link/client.py`
- Modify: `modempi/tests/conftest.py` (`link` 픽스처)
- Test: `modempi/tests/test_link_client.py`

**Interfaces:**
- Consumes: `JobStore`, `FakeHub(token, jobs, config)`, `.url`, `.send(msg)`, `.wait_for(t)`, `.received`.
- Produces: `class LinkClient(store, *, url, modem_id, token, agent_ver="0.0.0", modem_fw="unknown", clock=time.time, sleep=asyncio.sleep, upload_interval=1.0, silence_timeout=60.0, config_timeout=10.0, backoff_max=30.0)`; `async run()`, `async stop()`, `state`, `connected: asyncio.Event`, `backoff: float`, `attempts: int`; `AuthError`, `ProtocolError`. Task 3의 `Uploader`는 이 Task에서 **스텁 없이** — `run()`이 업로더 없이 recv 루프만 돈다. Task 3에서 붙인다.

- [ ] **Step 1: 실패하는 테스트**

`modempi/tests/test_link_client.py`:
```python
import asyncio
import json

import pytest
from lora_proto import proto as P

from modempi.link.client import LinkClient

pytestmark = pytest.mark.anyio

JOB = {"job_id": 5, "bld": "E", "room": 301, "unit": 1, "type": "SLOT_SET",
       "payload": {"day": 1, "s_h": 9, "s_m": 0, "e_h": 10, "e_m": 0, "type": 1,
                   "subject": "a", "professor": "b"}, "priority": 3, "new_ver": 1}


async def _run(store, hub, **kw):
    c = LinkClient(store, url=hub.url, modem_id="m1", token="secret", agent_ver="0.1", **kw)
    task = asyncio.create_task(c.run())
    await asyncio.wait_for(c.connected.wait(), 3)
    return c, task


async def _stop(c, task):
    await c.stop()
    await asyncio.wait_for(task, 3)


async def test_hello_then_config_stored(store, fake_hub):
    c, task = await _run(store, fake_hub)
    hello = await fake_hub.wait_for("hello")
    assert hello["modem_id"] == "m1" and hello["token"] == "secret"
    assert hello["agent_ver"] == "0.1" and hello["modem_fw"] == "unknown"
    assert hello["pending_results"] == 0
    assert store.config["net_id"] == 0x4B and c.state == "CONNECTED"
    await _stop(c, task)
    assert c.state == "DISCONNECTED"


async def test_job_stored_and_accepted_dup_ignored(store, fake_hub):
    fake_hub.jobs = [JOB, JOB]  # 같은 job_id 두 번 (서버 안전망 재송 흉내)
    c, task = await _run(store, fake_hub)
    await fake_hub.wait_for("job_accepted")
    await asyncio.sleep(0.1)
    accepted = [m for m in fake_hub.received if m["t"] == "job_accepted"]
    assert [m["job_id"] for m in accepted] == [5, 5]  # 둘 다 회신 (int)
    assert list(store.jobs) == ["5"]  # 한 번만 저장 (str)
    j = store.jobs["5"]
    assert j["type"] == "SLOT_SET" and j["priority"] == 3 and j["new_ver"] == 1
    assert json.loads(j["payload"])["subject"] == "a"  # 검증 없이 문자열로
    await _stop(c, task)


async def test_time_now_puts_time_row_uploaded(store, fake_hub):
    c, task = await _run(store, fake_hub)
    await fake_hub.send({"t": "time_now", "request_status": True})
    await fake_hub.send({"t": "ping"})
    await fake_hub.wait_for("pong")
    rows = [j for j in store.jobs.values() if j["type"] == "TIME"]
    assert len(rows) == 1 and rows[0]["uploaded"] == 1 and rows[0]["priority"] == 0
    p = json.loads(rows[0]["payload"])
    assert p["flags"] & P.TimeFlag.REQUEST_STATUS and isinstance(p["epoch"], int)
    await _stop(c, task)


async def test_cancel_and_unknown_and_garbage_keep_connection(store, fake_hub):
    fake_hub.jobs = [JOB]
    c, task = await _run(store, fake_hub)
    await fake_hub.wait_for("job_accepted")
    await fake_hub.send({"t": "cancel", "job_id": 5})
    await fake_hub.send({"t": "cancel", "job_id": 999})
    await fake_hub.send({"t": "whatever"})
    await fake_hub._conn.send("not json")
    await fake_hub.send({"t": "ping"})
    await fake_hub.wait_for("pong")
    assert store.jobs["5"]["state"] == "cancelled" and c.state == "CONNECTED"
    await _stop(c, task)
```

Run: `uv run pytest tests/test_link_client.py -q` → FAIL (`modempi.link.client` 없음).

- [ ] **Step 2: 구현**

`modempi/modempi/link/client.py`:
```python
"""계약 ⑥ 소비 측 WS 클라이언트 (S5 spec §2.1·§2.2). 파이프라인과는 JobStore 로만 만난다."""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from typing import Literal

import websockets
from lora_proto import proto as P
from websockets.asyncio.client import ClientConnection

from modempi.link.store_port import JobStore

log = logging.getLogger("link")

State = Literal["DISCONNECTED", "CONNECTING", "CONNECTED"]


class AuthError(Exception):
    """서버가 4001 로 닫음 — 토큰 불일치."""


class ProtocolError(Exception):
    """hello 뒤 config 가 안 옴."""


class LinkClient:
    def __init__(
        self,
        store: JobStore,
        *,
        url: str,
        modem_id: str,
        token: str,
        agent_ver: str = "0.0.0",
        modem_fw: str = "unknown",
        clock=time.time,
        sleep=asyncio.sleep,
        upload_interval: float = 1.0,
        silence_timeout: float = 60.0,
        config_timeout: float = 10.0,
        backoff_max: float = 30.0,
    ):
        self.store = store
        self.url, self.modem_id, self._token = url, modem_id, token
        self.agent_ver, self.modem_fw = agent_ver, modem_fw
        self._clock, self._sleep = clock, sleep
        self.upload_interval, self.silence_timeout = upload_interval, silence_timeout
        self.config_timeout, self.backoff_max = config_timeout, backoff_max
        self.state: State = "DISCONNECTED"
        self.connected = asyncio.Event()
        self.backoff = 1.0
        self.attempts = 0
        self._stop = asyncio.Event()
        self._ws: ClientConnection | None = None
        self._last_rx = 0.0

    # ---- 수명 ----
    async def run(self) -> None:
        while not self._stop.is_set():
            self.state = "CONNECTING"
            self.attempts += 1
            try:
                await self._session()
            except AuthError:
                log.error("modem %s: 토큰 불일치(4001) — %.0f s 뒤 재시도", self.modem_id, self.backoff_max)
                self.backoff = self.backoff_max
            except (OSError, ProtocolError, websockets.exceptions.WebSocketException, TimeoutError) as e:
                log.warning("modem %s: 연결 종료 %s", self.modem_id, e)
            finally:
                self.state = "DISCONNECTED"
                self.connected.clear()
                self._ws = None
            if self._stop.is_set():
                break
            await self._sleep(self.backoff * random.uniform(0.8, 1.2))
            self.backoff = min(self.backoff * 2, self.backoff_max)

    async def stop(self) -> None:
        self._stop.set()
        if self._ws is not None:
            await self._ws.close()

    # ---- 세션 1회 ----
    def _hello(self) -> dict:
        return {
            "t": "hello",
            "modem_id": self.modem_id,
            "token": self._token,
            "agent_ver": self.agent_ver,
            "modem_fw": self.modem_fw,
            "pending_results": len(self.store.pending_results()),
        }

    async def _session(self) -> None:
        async with websockets.connect(self.url) as ws:
            self._ws = ws
            hello = self._hello()
            log.info("modem %s: hello (pending_results=%s)", self.modem_id, hello["pending_results"])
            await ws.send(json.dumps(hello))
            try:
                first = json.loads(await asyncio.wait_for(ws.recv(), self.config_timeout))
            except websockets.exceptions.ConnectionClosed as e:
                if e.rcvd is not None and e.rcvd.code == 4001:
                    raise AuthError from e
                raise
            if not isinstance(first, dict) or first.get("t") != "config":
                raise ProtocolError(f"config 대신 {first!r}")
            self._on_message(first)
            self.state = "CONNECTED"
            self.backoff = 1.0
            self._last_rx = self._clock()
            self.connected.set()
            await self._recv_loop(ws)

    async def _recv_loop(self, ws: ClientConnection) -> None:
        async for raw in ws:
            self._last_rx = self._clock()
            try:
                msg = json.loads(raw)
            except ValueError:
                log.warning("modem %s: JSON 아님, 무시", self.modem_id)
                continue
            if not isinstance(msg, dict):
                continue
            try:
                reply = self._on_message(msg)
            except Exception:
                log.exception("modem %s: %s 처리 실패", self.modem_id, msg.get("t"))
                continue
            if reply is not None:
                await ws.send(json.dumps(reply))

    # ---- 메시지 → store ----
    def _on_message(self, msg: dict) -> dict | None:
        t = msg.get("t")
        if t == "config":
            self.store.set_config(msg)
        elif t == "job":
            job_id = int(msg["job_id"])
            self.store.put_job(
                job_id=str(job_id),
                bld=msg["bld"],
                room=int(msg["room"]),
                unit=int(msg["unit"]),
                type=msg["type"],
                payload=json.dumps(msg["payload"], ensure_ascii=False),
                priority=int(msg.get("priority", 5)),
                new_ver=msg.get("new_ver"),
            )
            return {"t": "job_accepted", "job_id": job_id}  # 중복이어도 회신 (멱등)
        elif t == "cancel":
            self.store.cancel_job(str(int(msg["job_id"])))
        elif t == "time_now":
            epoch = int(self._clock())
            flags = int(P.TimeFlag.REQUEST_STATUS) if msg.get("request_status") else 0
            self.store.put_job(
                job_id=f"time-{epoch}",
                bld="",
                room=0,
                unit=0,
                type="TIME",
                payload=json.dumps({"epoch": epoch, "flags": flags}),
                priority=0,
                new_ver=None,
                uploaded=1,  # 메인은 TIME 결과에 관심 없음 (S6 §4.4)
            )
        elif t == "ping":
            return {"t": "pong"}
        elif t == "pong":
            pass
        else:
            log.warning("modem %s: 모르는 t=%r 무시", self.modem_id, t)
        return None
```

- [ ] **Step 3: 통과 + 커밋**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check .` → PASS.

```bash
git add modempi/modempi/link/client.py modempi/tests/test_link_client.py
git commit -m "feat(modempi): LinkClient — hello·config·job/cancel/time_now/ping 수신 → JobStore (계약 ⑥ 소비)"
```

---

### Task 3: `Uploader` — job_result / uplink 송신

**Files:**
- Create: `modempi/modempi/link/uploader.py`
- Modify: `modempi/modempi/link/client.py` (`_session`에서 업로더 태스크 기동·정리)
- Test: `modempi/tests/test_link_uploader.py`

**Interfaces:**
- Produces: `build_job_result(row: JobRow) -> dict`, `class Uploader(store, *, interval=1.0, sleep=asyncio.sleep, batch=100)`; `async run(ws, stop: asyncio.Event)`; `async flush_once(ws) -> int`(보낸 메시지 수).
- `LinkClient._session`: `connected.set()` 뒤 `uploader.run(ws, self._stop)`를 태스크로 띄우고 `_recv_loop` 종료 시 취소.

- [ ] **Step 1: 실패하는 테스트**

`modempi/tests/test_link_uploader.py`:
```python
import asyncio
import json

import pytest

from modempi.link.client import LinkClient
from modempi.link.store_port import JobRow
from modempi.link.uploader import build_job_result

pytestmark = pytest.mark.anyio


def test_build_job_result_flattens_node_vers_and_int_job_id():
    row = JobRow(job_id="12", state="acked", attempts=2, txn=9, ack_status=0, ack_detail=0,
                 rssi=-88, snr=7.5, node_vers=json.dumps({"sched": 3, "resv": 1, "exam": 0, "ident": 1}),
                 batt_mv=3900, layout=1, fw=20, last_error=None, finished_at=1_800_000_123.4)
    m = build_job_result(row)
    assert m == {"t": "job_result", "job_id": 12, "state": "acked", "ack_status": 0, "ack_detail": 0,
                 "attempts": 2, "txn": 9, "rssi": -88, "snr": 7.5, "sched_ver": 3, "resv_ver": 1,
                 "exam_ver": 0, "ident_ver": 1, "batt_mv": 3900, "layout": 1, "fw": 20,
                 "last_error": None, "finished_at": 1_800_000_123}


def test_build_job_result_cancelled_and_missing_vers():
    row = JobRow(job_id="3", state="cancelled", finished_at=1.0)
    m = build_job_result(row)
    assert m["state"] == "failed" and m["last_error"] == "cancelled"
    assert m["sched_ver"] is None and m["ident_ver"] is None


async def _run(store, hub, **kw):
    c = LinkClient(store, url=hub.url, modem_id="m1", token="secret", upload_interval=0.05, **kw)
    task = asyncio.create_task(c.run())
    await asyncio.wait_for(c.connected.wait(), 3)
    return c, task


async def test_results_and_uplinks_are_uploaded_and_marked(store, fake_hub):
    for i in ("1", "2", "3"):
        store.put_job(job_id=i, bld="E", room=301, unit=1, type="CMD", payload="{}", priority=3, new_ver=None)
    store.finish("1", state="acked", ack_status=0)
    store.cancel_job("2")
    store.put_uplink({"kind": "HELLO", "bld": 0, "room": 0, "unit": 0, "mac": "aabbccddeeff",
                      "fw": 20, "batt_mv": 4000, "rssi": -100, "snr": 3.0})
    c, task = await _run(store, fake_hub)
    hello = await fake_hub.wait_for("hello")
    assert hello["pending_results"] == 2
    await fake_hub.wait_for("uplink")
    await asyncio.sleep(0.1)
    results = [m for m in fake_hub.received if m["t"] == "job_result"]
    assert [(m["job_id"], m["state"], m["last_error"]) for m in results] == [
        (1, "acked", None), (2, "failed", "cancelled")]
    uplinks = [m for m in fake_hub.received if m["t"] == "uplink"]
    assert uplinks[0]["mac"] == "aabbccddeeff" and uplinks[0]["kind"] == "HELLO"
    # job_result 가 uplink 보다 먼저
    order = [m["t"] for m in fake_hub.received if m["t"] in ("job_result", "uplink")]
    assert order.index("uplink") > order.index("job_result")
    assert store.jobs["1"]["uploaded"] == 1 and store.jobs["2"]["uploaded"] == 1
    assert store.jobs["3"]["uploaded"] == 0 and store.uplinks[0]["uploaded"] == 1
    # 이후 새로 끝난 것도 올라간다
    store.finish("3", state="failed", last_error="no_ack")
    await asyncio.sleep(0.2)
    assert any(m["t"] == "job_result" and m["job_id"] == 3 for m in fake_hub.received)
    await c.stop()
    await asyncio.wait_for(task, 3)


async def test_non_numeric_job_id_row_is_marked_and_skipped(store, fake_hub, caplog):
    store.put_job(job_id="weird", bld="E", room=1, unit=1, type="CMD", payload="{}", priority=3, new_ver=None)
    store.finish("weird", state="acked")
    c, task = await _run(store, fake_hub)
    await asyncio.sleep(0.2)
    assert store.jobs["weird"]["uploaded"] == 1
    assert not any(m["t"] == "job_result" for m in fake_hub.received)
    assert "weird" in caplog.text
    await c.stop()
    await asyncio.wait_for(task, 3)
```

Run: `uv run pytest tests/test_link_uploader.py -q` → FAIL (`uploader` 없음).

- [ ] **Step 2: 구현**

`modempi/modempi/link/uploader.py`:
```python
"""store 에 쌓인 결과·업링크를 1 s 주기로 메인Pi 에 올린다 (S5 spec §2.3)."""

from __future__ import annotations

import asyncio
import json
import logging

from websockets.asyncio.client import ClientConnection

from modempi.link.store_port import JobRow, JobStore

log = logging.getLogger("link.upload")

_VER_KEYS = (("sched_ver", "sched"), ("resv_ver", "resv"), ("exam_ver", "exam"), ("ident_ver", "ident"))


def build_job_result(row: JobRow) -> dict:
    vers = json.loads(row.node_vers) if row.node_vers else {}
    state, last_error = row.state, row.last_error
    if state == "cancelled":  # 계약 ⑥: 취소된 작업은 failed/cancelled 로 보고 (S2 §2.4)
        state, last_error = "failed", "cancelled"
    return {
        "t": "job_result",
        "job_id": int(row.job_id),
        "state": state,
        "ack_status": row.ack_status,
        "ack_detail": row.ack_detail,
        "attempts": row.attempts,
        "txn": row.txn,
        "rssi": row.rssi,
        "snr": row.snr,
        **{k: vers.get(v) for k, v in _VER_KEYS},
        "batt_mv": row.batt_mv,
        "layout": row.layout,
        "fw": row.fw,
        "last_error": last_error,
        "finished_at": int(row.finished_at) if row.finished_at is not None else None,
    }


class Uploader:
    def __init__(self, store: JobStore, *, interval: float = 1.0, sleep=asyncio.sleep, batch: int = 100):
        self.store, self.interval, self._sleep, self.batch = store, interval, sleep, batch

    async def run(self, ws: ClientConnection, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self._sleep(self.interval)
            if stop.is_set():
                return
            await self.flush_once(ws)

    async def flush_once(self, ws: ClientConnection) -> int:
        """job_result 먼저, uplink 다음. write 완료 즉시 mark — 실패하면 mark 안 하고 재접속 후 재송."""
        n = 0
        for row in self.store.pending_results(self.batch):
            try:
                msg = build_job_result(row)
            except (ValueError, TypeError):
                log.error("job_id %r 보고 불가 — 치움", row.job_id)
                self.store.mark_uploaded([row.job_id])
                continue
            await ws.send(json.dumps(msg))
            self.store.mark_uploaded([row.job_id])
            n += 1
        for up in self.store.pending_uplinks(self.batch):
            await ws.send(json.dumps({"t": "uplink", **up.body}, ensure_ascii=False))
            self.store.mark_uplinks_uploaded([up.id])
            n += 1
        return n
```

`client.py` 수정 — import 추가 `from modempi.link.uploader import Uploader`; `__init__` 끝에 `self.uploader = Uploader(store, interval=upload_interval, sleep=sleep)`; `_session`의 `await self._recv_loop(ws)`를 아래로 교체:
```python
            up = asyncio.create_task(self.uploader.run(ws, self._stop))
            try:
                await self._recv_loop(ws)
            finally:
                up.cancel()
                await asyncio.gather(up, return_exceptions=True)
```

- [ ] **Step 3: 통과 + 커밋**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check .` → PASS.

```bash
git add modempi/modempi/link/uploader.py modempi/modempi/link/client.py modempi/tests/test_link_uploader.py
git commit -m "feat(modempi): Uploader — job_result/uplink 1 s 폴링 송신, cancelled→failed, 몰아 보내기"
```

---

### Task 4: 재접속 · 백오프 · 4001 · watchdog

**Files:**
- Modify: `modempi/modempi/link/client.py` (`_watchdog`)
- Test: `modempi/tests/test_link_reconnect.py`

**Interfaces:**
- Produces: `LinkClient._watchdog(ws)` — `silence_timeout` 초 이상 `_last_rx` 갱신 없으면 `ws.close()`; `_session`이 업로더와 함께 태스크로 띄움.

- [ ] **Step 1: 실패하는 테스트**

`modempi/tests/test_link_reconnect.py`:
```python
import asyncio

import pytest

from modempi.link.client import LinkClient

from .conftest import FakeHub

pytestmark = pytest.mark.anyio


async def _wait(pred, timeout=3.0):
    async with asyncio.timeout(timeout):
        while not pred():
            await asyncio.sleep(0.02)


async def test_reconnect_after_hub_restart_reports_pending(store, clock):
    hub = FakeHub(token="secret")
    port = await hub.start()
    c = LinkClient(store, url=hub.url, modem_id="m1", token="secret",
                   clock=clock, sleep=clock.sleep, upload_interval=0.05)
    task = asyncio.create_task(c.run())
    await asyncio.wait_for(c.connected.wait(), 3)
    await hub.stop()  # 끊김
    await _wait(lambda: c.state != "CONNECTED")
    # 끊긴 동안 파이프라인이 결과 2개를 만들었다
    for i in ("1", "2"):
        store.put_job(job_id=i, bld="E", room=301, unit=1, type="CMD", payload="{}", priority=3, new_ver=None)
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
    c = LinkClient(store, url="ws://127.0.0.1:1/ws/modem", modem_id="m1", token="x",
                   clock=clock, sleep=clock.sleep)  # 아무도 안 듣는 포트
    task = asyncio.create_task(c.run())
    await _wait(lambda: len(clock.sleeps) >= 7)
    await c.stop()
    await asyncio.wait_for(task, 3)
    base = [1, 2, 4, 8, 16, 30, 30]
    for s, b in zip(clock.sleeps[:7], base):
        assert b * 0.8 <= s <= b * 1.2, (s, b)


async def test_auth_failure_jumps_to_max_backoff(store, fake_hub, clock):
    c = LinkClient(store, url=fake_hub.url, modem_id="m1", token="wrong", clock=clock, sleep=clock.sleep)
    task = asyncio.create_task(c.run())
    await _wait(lambda: len(clock.sleeps) >= 2)
    await c.stop()
    await asyncio.wait_for(task, 3)
    assert all(30 * 0.8 <= s <= 30 * 1.2 for s in clock.sleeps[:2])
    assert c.state == "DISCONNECTED" and store.config is None


async def test_silence_watchdog_reconnects(store, fake_hub, clock):
    c = LinkClient(store, url=fake_hub.url, modem_id="m1", token="secret",
                   clock=clock, sleep=clock.sleep, silence_timeout=60)
    task = asyncio.create_task(c.run())
    await asyncio.wait_for(c.connected.wait(), 3)
    first = c.attempts
    clock.now += 61  # 서버가 61 s 동안 아무 말도 안 했다
    await _wait(lambda: c.attempts > first)  # watchdog 이 닫고 재접속
    await asyncio.wait_for(c.connected.wait(), 3)
    assert len([m for m in fake_hub.received if m["t"] == "hello"]) >= 2
    await c.stop()
    await asyncio.wait_for(task, 3)
```

Run: `uv run pytest tests/test_link_reconnect.py -q` → `test_silence_watchdog_reconnects` FAIL (watchdog 없음). 나머지는 Task 2·3 구현으로 이미 통과할 수 있다 — 통과하면 그대로 둔다(회귀 고정).

- [ ] **Step 2: 구현**

`client.py`에 추가:
```python
    async def _watchdog(self, ws: ClientConnection) -> None:
        """서버가 30 s 마다 ping 을 보낸다. silence_timeout 동안 아무 메시지도 없으면 죽은 연결 (S5 §2.2)."""
        while True:
            await self._sleep(1.0)
            if self._clock() - self._last_rx > self.silence_timeout:
                log.warning("modem %s: %.0f s 무응답 — 재접속", self.modem_id, self.silence_timeout)
                await ws.close(code=1001)
                return
```
`_session`의 태스크 블록을 확장:
```python
            tasks = [
                asyncio.create_task(self.uploader.run(ws, self._stop)),
                asyncio.create_task(self._watchdog(ws)),
            ]
            try:
                await self._recv_loop(ws)
            finally:
                for t in tasks:
                    t.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
```

주의: `test_backoff_sequence_with_jitter`가 `OSError`(connection refused) 경로를 탄다. `websockets.connect`가 던지는 예외가 `OSError`가 아니면(`ConnectionRefusedError`는 OSError 하위이므로 보통 맞음) `run()`의 except 절에 그 타입을 추가한다.

- [ ] **Step 3: 통과 + 커밋**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check .` → PASS. 각 재접속 테스트가 1 s 미만인지 확인(실제 sleep 없음).

```bash
git add modempi/modempi/link/client.py modempi/tests/test_link_reconnect.py
git commit -m "feat(modempi): 링크 재접속 — 백오프·4001 상한 점프·60 s 무응답 watchdog·재접속 시 몰아 보내기"
```

---

### Task 5: `run.py` — env 설정 + 진입점

**Files:**
- Create: `modempi/modempi/link/run.py`
- Test: `modempi/tests/test_link_run.py`

**Interfaces:**
- Produces: `@dataclass LinkSettings(url, modem_id, token, store_path)`, `LinkSettings.from_env(env: Mapping[str, str] = os.environ) -> LinkSettings` (누락 시 `SystemExit` 메시지 `"MODEMPI_* 누락: MODEMPI_TOKEN, MODEMPI_STORE"`), `build_client(settings, store) -> LinkClient`(`agent_ver` = 패키지 버전), `async main(store)` — cw-08 뒤 `main.py`가 store를 만들어 넘긴다.

- [ ] **Step 1: 실패하는 테스트**

`modempi/tests/test_link_run.py`:
```python
import pytest

from modempi.link.client import LinkClient
from modempi.link.run import LinkSettings, build_client

from .fake_store import MemoryStore

ENV = {"MODEMPI_MAIN_URL": "ws://h/ws/modem", "MODEMPI_ID": "mjc-eng",
       "MODEMPI_TOKEN": "tok", "MODEMPI_STORE": "/var/lib/modempi/jobs.db"}


def test_settings_from_env():
    s = LinkSettings.from_env(ENV)
    assert (s.url, s.modem_id, s.token, s.store_path) == (
        "ws://h/ws/modem", "mjc-eng", "tok", "/var/lib/modempi/jobs.db")


def test_missing_env_lists_names():
    with pytest.raises(SystemExit) as e:
        LinkSettings.from_env({"MODEMPI_MAIN_URL": "ws://h"})
    assert "MODEMPI_ID" in str(e.value) and "MODEMPI_TOKEN" in str(e.value) and "MODEMPI_STORE" in str(e.value)


def test_build_client():
    c = build_client(LinkSettings.from_env(ENV), MemoryStore())
    assert isinstance(c, LinkClient) and c.modem_id == "mjc-eng" and c.url == "ws://h/ws/modem"
    assert c.agent_ver  # 패키지 버전 문자열
```

Run: `uv run pytest tests/test_link_run.py -q` → FAIL.

- [ ] **Step 2: 구현**

`modempi/modempi/link/run.py`:
```python
"""env → LinkClient 기동. main.py(공용) 가 store 를 만들어 main(store) 를 태스크로 띄운다 (cw-08 뒤)."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version

from modempi.link.client import LinkClient
from modempi.link.store_port import JobStore

_KEYS = ("MODEMPI_MAIN_URL", "MODEMPI_ID", "MODEMPI_TOKEN", "MODEMPI_STORE")


@dataclass(frozen=True)
class LinkSettings:
    url: str
    modem_id: str
    token: str
    store_path: str

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> LinkSettings:
        missing = [k for k in _KEYS if not env.get(k)]
        if missing:
            raise SystemExit(f"MODEMPI_* 누락: {', '.join(missing)}")
        return cls(env["MODEMPI_MAIN_URL"], env["MODEMPI_ID"], env["MODEMPI_TOKEN"], env["MODEMPI_STORE"])


def _agent_ver() -> str:
    try:
        return version("modempi")
    except PackageNotFoundError:
        return "0.0.0"


def build_client(settings: LinkSettings, store: JobStore) -> LinkClient:
    return LinkClient(
        store, url=settings.url, modem_id=settings.modem_id, token=settings.token, agent_ver=_agent_ver()
    )


async def main(store: JobStore) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    client = build_client(LinkSettings.from_env(), store)
    loop = asyncio.get_running_loop()
    for sig in ("SIGINT", "SIGTERM"):
        try:
            import signal

            loop.add_signal_handler(getattr(signal, sig), lambda: asyncio.ensure_future(client.stop()))
        except (NotImplementedError, AttributeError):  # Windows 개발 환경
            pass
    await client.run()
```

- [ ] **Step 3: 통과 + 커밋**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check .` → PASS.

```bash
git add modempi/modempi/link/run.py modempi/tests/test_link_run.py
git commit -m "feat(modempi): link/run — MODEMPI_* env 설정, 진입점 main(store)"
```

---

### Task 6: 전체 게이트 + 진행도

- [ ] **Step 1: full 게이트**

```bash
cd modempi && uv run pytest -q && uv run ruff check . && uv run ruff format --check .
cd ../server && uv run pytest -q   # fake_hub start(port) 변경이 서버 테스트를 깨지 않는지
```

- [ ] **Step 2: 진행도**

`docs/progress.html` `wj-03`(S5 spec) 체크. `wj-07`은 cw-08 뒤 `main.py` 연결까지 끝나야 체크. 커밋 `docs: 진행도 갱신 (wj) — S5 spec`. PR은 사용자 지시 시.

## 이후

- cw-08(`store.py`) 머지 → `JobStore` Protocol 대조(동기/비동기, `put_job(uploaded=)`, `cancel_job`이 `finished_at` 세팅), `main.py`에 `link.run.main(store)` 태스크 추가(공용 파일, 양쪽 리뷰) → wj-07 체크.
- 4주차 Pi↔Pi(wj-08): 메인Pi 실기 허브 + 모뎀Pi `MODEMPI_*` env → 저장→acked, 끊고 붙이기.

## Self-Review (계획 검토)

- 스펙 커버리지: §2.1 수신 표 → Task 2 `_on_message` · §2.1 송신 표 → Task 2(hello/accepted/pong)·Task 3(job_result/uplink) · §2.2 연결 규칙(백오프·4001·config 10 s·60 s·SIGTERM) → Task 2(`config_timeout`)·Task 4·Task 5(signal) · §2.3 업로드(1 s·100·순서·mark 시점·재접속 몰아 보내기) → Task 3·Task 4 · §3 토큰 마스킹 → Task 2 로그에 token 미출력 · §3 `job_id` 왕복·`int()` 실패 처리 → Task 2·3 · §4.2 Protocol → Task 1 · §4.4 env → Task 5 · §8 테스트 항목 → 각 Task 테스트 이름과 1:1. ✅
- Placeholder 없음. ✅
- 타입 일관성: `LinkClient` 생성자 인자(Task 2) = Task 3·4·5 사용처 동일 · `Uploader(store, interval, sleep, batch)`·`run(ws, stop)` = Task 3 client 호출 · `JobRow` 필드(Task 1) = `build_job_result`(Task 3) · `FakeHub.start(port)` = Task 4 `hub2.start(port)` · conftest `clock`(`FakeClock.__call__`, `.sleep`, `.sleeps`, `.now`) = Task 4. ✅
- 함정 선제 회피: (1) `modempi/tests`가 `tests` 패키지라 `server/tests/fake_hub`와 이름 충돌 → 파일 경로 import. (2) 재접속 테스트에 같은 포트가 필요 → `FakeHub.start(port)` additive. (3) 백오프·무응답 테스트는 `clock`/`sleep` 주입으로 실시간 대기 없음. (4) 업로더는 세션당 태스크라 "연결 없으면 송신 안 함"이 자연히 성립.

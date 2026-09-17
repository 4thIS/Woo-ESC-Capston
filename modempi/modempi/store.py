"""계약 ⑦ JobStore — 모뎀Pi 안에서 링크(wj)와 LoRa 파이프라인(cw)이 만나는 유일한 통로 (로드맵 §4.3).

- 링크 측 공식 시그니처는 `modempi.link.store_port.JobStore` Protocol. 이 클래스는 그것을 그대로 구현하고
  파이프라인 측 함수(`recover`·`pick_next`·`get_job`·`update`·`next_txn`·`get_config`·`on_config_changed`·
  `put_uplink`·`set_meta`·`prune`)를 더한다.
- **동기 `sqlite3`, 연결 1개** — 이벤트 루프에서 직접 부른다(S5 spec §9, S6 spec §2). 모든 쓰기는 호출이
  끝나기 전에 커밋된다(autocommit + 여러 문장은 `_tx()`).
- 스키마 변경은 additive만(기존 컬럼 불변). 바꾸면 `SCHEMA_VERSION` +1, `_SCHEMA`(새 DB용)와
  `_MIGRATIONS[새 버전]`(기존 DB용)을 함께 고친다.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, fields

from modempi.link.store_port import JobRow, UplinkRow

log = logging.getLogger("modempi.store")

SCHEMA_VERSION = 1
# 기존 DB 를 v(n-1) → v(n) 으로 올리는 SQL. 새 DB 는 _SCHEMA 한 번으로 최신이 된다.
_MIGRATIONS: dict[int, str] = {}

# `split` 은 r6(2026-09-17)에서 뺐다 — 유닛 분해는 메인Pi `api._insert` 에서만 한다.
STATES = frozenset({"received", "sending", "acked", "failed", "cancelled"})
_FINISHED = frozenset({"acked", "failed", "cancelled"})

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  job_id      TEXT PRIMARY KEY,
  bld TEXT NOT NULL, room INTEGER NOT NULL, unit INTEGER NOT NULL,
  parent_id   TEXT,
  type        TEXT NOT NULL,
  payload     TEXT NOT NULL,
  priority    INTEGER NOT NULL DEFAULT 5,
  new_ver     INTEGER,
  state       TEXT NOT NULL DEFAULT 'received',
  attempts    INTEGER NOT NULL DEFAULT 0,
  next_try_at REAL,
  txn INTEGER, ack_status INTEGER, ack_detail INTEGER, rssi INTEGER, snr REAL,
  node_vers   TEXT,
  batt_mv INTEGER, layout INTEGER, fw INTEGER, last_error TEXT,
  received_at REAL NOT NULL, finished_at REAL,
  uploaded    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_jobs_pick   ON jobs(state, priority, next_try_at, received_at);
CREATE INDEX IF NOT EXISTS ix_jobs_upload ON jobs(uploaded, finished_at);
CREATE INDEX IF NOT EXISTS ix_jobs_node   ON jobs(bld, room, unit, state);
CREATE TABLE IF NOT EXISTS uplinks (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  body        TEXT NOT NULL,
  created_at  REAL NOT NULL,
  uploaded    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_uplinks_upload ON uplinks(uploaded, id);
CREATE TABLE IF NOT EXISTS config (
  id          INTEGER PRIMARY KEY CHECK (id = 1),
  body        TEXT NOT NULL,
  updated_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS node_txn (
  bld TEXT NOT NULL, room INTEGER NOT NULL, unit INTEGER NOT NULL,
  txn INTEGER NOT NULL,
  PRIMARY KEY (bld, room, unit)
);
CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class Job:
    """`jobs` 한 행 전체. 파이프라인이 `pick_next()`·`get_job()`으로 받는다."""

    job_id: str
    bld: str
    room: int
    unit: int
    parent_id: str | None  # 계약 DDL 에 남아 있으나 r6 부터 쓰지 않음 (항상 None)
    type: str
    payload: str
    priority: int
    new_ver: int | None
    state: str
    attempts: int
    next_try_at: float | None
    txn: int | None
    ack_status: int | None
    ack_detail: int | None
    rssi: int | None
    snr: float | None
    node_vers: str | None
    batt_mv: int | None
    layout: int | None
    fw: int | None
    last_error: str | None
    received_at: float
    finished_at: float | None
    uploaded: int


_JOB_COLS = ", ".join(f.name for f in fields(Job))
_RESULT_COLS = ", ".join(f.name for f in fields(JobRow))
# update() 로 바꿀 수 있는 컬럼. 주소·type·payload·new_ver·received_at 은 수신 시 고정.
_UPDATABLE = frozenset(
    {
        "state",
        "attempts",
        "next_try_at",
        "txn",
        "ack_status",
        "ack_detail",
        "rssi",
        "snr",
        "node_vers",
        "batt_mv",
        "layout",
        "fw",
        "last_error",
        "finished_at",
        "uploaded",
    }
)


class SqliteStore:
    def __init__(
        self,
        path: str,
        *,
        clock: Callable[[], float] = time.time,
        busy_timeout: float = 1.0,
    ) -> None:
        """`busy_timeout`: 다른 프로세스가 쓰기 잠금을 쥐고 있을 때 기다릴 최대 초. 짧게 둔다 —
        기본값(5 s)이면 이벤트 루프(링크 ping 포함)가 그동안 멈춘다. 초과하면 `OperationalError`."""
        self._clock = clock
        self._config_cbs: list[Callable[[dict], None]] = []
        self._conn = sqlite3.connect(path, isolation_level=None, timeout=busy_timeout)
        try:
            self._open_schema(path)
        except BaseException:
            self._conn.close()
            raise

    def _open_schema(self, path: str) -> None:
        (found,) = self._conn.execute("PRAGMA user_version").fetchone()
        if found > SCHEMA_VERSION:
            raise RuntimeError(
                f"{path}: 스키마 v{found} 가 이 코드(v{SCHEMA_VERSION})보다 새롭다 — modempi 를 업데이트할 것"
            )
        # WAL + FULL: 전원이 나가도 커밋된 next_txn·결과가 남는다 (SD 카드, 로드맵 §4.4)
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA synchronous = FULL")
        steps = [(SCHEMA_VERSION, _SCHEMA)] if found == 0 else []
        steps += [(v, _MIGRATIONS[v]) for v in range(max(found, 1) + 1, SCHEMA_VERSION + 1)]
        # 단계마다 한 트랜잭션 — 중간에 죽어도 버전과 스키마가 어긋나지 않는다
        for version, script in steps:
            try:
                self._conn.executescript(
                    f"BEGIN;\n{script}\nPRAGMA user_version = {version};\nCOMMIT;"
                )
            except BaseException:
                self._rollback_if_open()
                raise

    def close(self) -> None:
        self._conn.close()

    def _rollback_if_open(self) -> None:
        if not self._conn.in_transaction:
            return  # SQLite 가 이미 롤백했으면 ROLLBACK 이 또 예외를 내 원래 오류를 가린다
        try:
            self._conn.execute("ROLLBACK")
        except sqlite3.Error:
            log.exception("ROLLBACK 실패")

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        """여러 문장을 한 트랜잭션으로. COMMIT 이 실패해도(디스크 가득·IO 오류) 트랜잭션을 열어 두지 않는다 —
        열어 두면 이후 단일 문장 쓰기가 그 안에 갇혀 성공한 척하다 재시작 때 사라진다."""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            yield self._conn
            self._conn.execute("COMMIT")
        except BaseException:
            self._rollback_if_open()
            raise

    # ---- 링크 측 (store_port.JobStore) ----

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
    ) -> bool:
        """같은 `job_id` 면 무시하고 False. 그 밖의 제약 위반(NOT NULL 등)은 `IntegrityError` —
        `INSERT OR IGNORE` 로 삼키면 링크가 중복으로 알고 `job_accepted` 를 보내 작업이 사라진다."""
        cur = self._conn.execute(
            "INSERT INTO jobs (job_id, bld, room, unit, type, payload, priority, new_ver,"
            " received_at, uploaded) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(job_id) DO NOTHING",
            (job_id, bld, room, unit, type, payload, priority, new_ver, self._clock(), uploaded),
        )
        return cur.rowcount == 1

    def cancel_job(self, job_id: str) -> bool:
        cur = self._conn.execute(
            "UPDATE jobs SET state = 'cancelled', finished_at = ?"
            " WHERE job_id = ? AND state = 'received'",
            (self._clock(), job_id),
        )
        return cur.rowcount == 1

    def pending_results(self, limit: int = 100) -> list[JobRow]:
        rows = self._conn.execute(
            f"SELECT {_RESULT_COLS} FROM jobs WHERE finished_at IS NOT NULL AND uploaded = 0"
            " ORDER BY finished_at, rowid LIMIT ?",
            (limit,),
        )
        return [JobRow(*r) for r in rows]

    def mark_uploaded(self, job_ids: list[str]) -> None:
        with self._tx() as c:
            c.executemany("UPDATE jobs SET uploaded = 1 WHERE job_id = ?", [(i,) for i in job_ids])

    def set_config(self, config: dict) -> None:
        self._conn.execute(
            "INSERT INTO config (id, body, updated_at) VALUES (1, ?, ?)"
            " ON CONFLICT(id) DO UPDATE SET body = excluded.body, updated_at = excluded.updated_at",
            (json.dumps(config, ensure_ascii=False), self._clock()),
        )
        for cb in list(self._config_cbs):
            try:
                cb(config)
            except Exception:
                log.exception("config 콜백 실패 — 무시하고 계속")

    def pending_uplinks(self, limit: int = 100) -> list[UplinkRow]:
        rows = self._conn.execute(
            "SELECT id, body FROM uplinks WHERE uploaded = 0 ORDER BY id LIMIT ?", (limit,)
        )
        return [UplinkRow(i, json.loads(b)) for i, b in rows]

    def mark_uplinks_uploaded(self, ids: list[int]) -> None:
        with self._tx() as c:
            c.executemany("UPDATE uplinks SET uploaded = 1 WHERE id = ?", [(i,) for i in ids])

    def get_meta(self, key: str) -> str | None:
        row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    # ---- 파이프라인 측 ----

    def recover(self) -> int:
        """파이프라인 기동 시 1회. 바꾼 행 수.

        - `sending` 으로 남은 행 → `received` (송신 도중 죽었음. 안 되돌리면 그 노드가 영영 안 집힌다).
          `attempts`·`txn` 은 그대로 — 워커가 **같은 TXN 으로** 재송해야 노드가 이미 적용한 프레임을
          DUP 으로 받는다. 새 TXN 이면 노드는 같은 버전을 GAP 으로 본다(v2 §3.4·§3.5).
        - `received` 의 재시도 대기(`next_try_at`)를 비운다. RTC 없는 Pi 가 과거 시각으로 깨어나면
          대기가 늘어나기 때문이다.

        여는 것만으로 하지 않는 이유: 디버그 스크립트가 같은 파일을 열 때 워커의 `sending` 행을 건드리면 안 된다.
        """
        with self._tx() as c:
            n = c.execute("UPDATE jobs SET state = 'received' WHERE state = 'sending'").rowcount
            n += c.execute(
                "UPDATE jobs SET next_try_at = NULL"
                " WHERE state = 'received' AND next_try_at IS NOT NULL"
            ).rowcount
        return n

    def get_job(self, job_id: str) -> Job | None:
        row = self._conn.execute(
            f"SELECT {_JOB_COLS} FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        return Job(*row) if row else None

    def pick_next(self) -> Job | None:
        """다음에 보낼 행. 상태는 바꾸지 않는다 — 호출자가
        `update(id, expect_state="received", state="sending")` 으로 집는다(그 사이 링크의 cancel 과 경합 방지).

        **노드 (bld, room, unit) 안에서는 엄격한 FIFO** (v2 §3.5 "프레임 순서는 워커가 노드별 FIFO 로 보장").
        각 노드의 머리 행만 후보다. 머리 = `sending` 이 있으면 그것(→ 그 노드는 후보 없음), 없으면 `received`
        중 순번이 가장 앞선 행이며, 그 행이 재시도 대기 중이면 노드 전체가 기다린다.
        순번은 **메인 `job_id`(outbox id = 생성 순 = 버전 순)**, 숫자가 아닌 id(`time-…`)는 0 으로 보고
        도착 순(rowid)으로 가른다. priority 는 노드끼리 머리 행을 고를 때만 쓴다 — 같은 노드 안에서
        priority 로 추월하면(예: FILE v5 보다 SLOT_SET v6 먼저) 노드가 GAP 을 내고 이어 온 옛 FILE 이
        최신 편집을 덮는다.
        """
        row = self._conn.execute(
            f"SELECT {_JOB_COLS} FROM jobs AS j"
            " WHERE j.state = 'received' AND (j.next_try_at IS NULL OR j.next_try_at <= :now)"
            " AND NOT EXISTS (SELECT 1 FROM jobs AS k"
            "   WHERE k.bld = j.bld AND k.room = j.room AND k.unit = j.unit"
            "   AND (k.state = 'sending' OR (k.state = 'received'"
            "     AND (CAST(k.job_id AS INTEGER), k.rowid) < (CAST(j.job_id AS INTEGER), j.rowid))))"
            " ORDER BY j.priority, j.received_at, j.rowid LIMIT 1",
            {"now": self._clock()},
        ).fetchone()
        return Job(*row) if row else None

    def update(self, job_id: str, /, *, expect_state: str | None = None, **fields: object) -> bool:
        """결과·재시도 필드 갱신. 행이 없거나 `expect_state` 와 현재 상태가 다르면 아무것도 안 하고 False.

        - `state` 가 acked/failed/cancelled 인데 `finished_at` 이 없거나 None 이면 지금 시각으로 채운다
          (안 채우면 `pending_results` 에 영영 안 잡혀 결과가 조용히 사라진다).
        - `node_vers` 는 dict 도 받는다 → JSON 문자열로 저장.
        - 주소·type·payload·new_ver·received_at 은 바꿀 수 없다(ValueError).
        - 메인은 결과 필드를 그대로 복사한다 — 재시도 끝에 `failed` 로 닫을 땐 앞 시도의 `ack_status` 등을
          함께 None 으로 넘길 것(S6).
        """
        if not fields:
            raise ValueError("update: 바꿀 필드 없음")
        bad = set(fields) - _UPDATABLE
        if bad:
            raise ValueError(f"update: 바꿀 수 없는 컬럼 {sorted(bad)}")
        if "state" in fields and fields["state"] not in STATES:
            raise ValueError(f"update: 알 수 없는 state {fields['state']!r}")
        if fields.get("state") in _FINISHED and fields.get("finished_at") is None:
            fields["finished_at"] = self._clock()
        if isinstance(fields.get("node_vers"), dict):
            fields["node_vers"] = json.dumps(fields["node_vers"])
        sets = ", ".join(f"{k} = ?" for k in fields)
        sql, args = f"UPDATE jobs SET {sets} WHERE job_id = ?", [*fields.values(), job_id]
        if expect_state is not None:
            sql, args = sql + " AND state = ?", [*args, expect_state]
        return self._conn.execute(sql, args).rowcount == 1

    def next_txn(self, bld: str, room: int, unit: int) -> int:
        """노드별 TXN 1..255 롤링(0 건너뜀). 호출이 끝나면 커밋돼 있다 — 재부팅 후에도 같은 TXN 을 다시 안 쓴다.

        **프레임을 처음 보낼 때만** 부른다. no_ack·BUSY·재기동 후 같은 프레임 재송은 `jobs.txn` 을 다시 써야
        노드가 DUP 으로 받는다(S6)."""
        with self._tx() as c:
            c.execute(
                "INSERT INTO node_txn (bld, room, unit, txn) VALUES (?, ?, ?, 1)"
                " ON CONFLICT(bld, room, unit) DO UPDATE SET txn = txn % 255 + 1",
                (bld, room, unit),
            )
            (txn,) = c.execute(
                "SELECT txn FROM node_txn WHERE bld = ? AND room = ? AND unit = ?",
                (bld, room, unit),
            ).fetchone()
        return txn

    def get_config(self) -> dict | None:
        row = self._conn.execute("SELECT body FROM config WHERE id = 1").fetchone()
        return json.loads(row[0]) if row else None

    def on_config_changed(self, cb: Callable[[dict], None]) -> None:
        """`set_config` 가 저장을 끝낸 뒤 같은 호출 안에서 `cb(config)` 를 부른다. 콜백 예외는 로그만 남긴다
        — 파이프라인 버그가 링크의 수신 루프를 깨면 안 된다."""
        self._config_cbs.append(cb)

    def put_uplink(self, body: dict) -> int:
        """`body` 는 JSON 으로 저장된다 — bytes 는 안 됨(MAC 은 소문자 hex 문자열, 로드맵 §4.2 인코딩 규칙)."""
        cur = self._conn.execute(
            "INSERT INTO uplinks (body, created_at) VALUES (?, ?)",
            (json.dumps(body, ensure_ascii=False), self._clock()),
        )
        return cur.lastrowid

    def prune(self, *, older_than: float) -> int:
        """메인Pi 에 보고까지 끝난 지 `older_than` 초가 지난 행을 지운다. 지운 행 수(jobs + uplinks).

        모뎀Pi 는 시간표 원본을 갖지 않는다(로드맵 §1) — FILE 레코드도 보고 뒤엔 버린다. 안 끝났거나
        아직 못 올린 행은 남긴다. 파이프라인이 하루 1회 부른다.
        """
        cutoff = self._clock() - older_than
        with self._tx() as c:
            n = c.execute(
                "DELETE FROM jobs WHERE uploaded = 1 AND finished_at IS NOT NULL AND finished_at < ?",
                (cutoff,),
            ).rowcount
            n += c.execute(
                "DELETE FROM uplinks WHERE uploaded = 1 AND created_at < ?", (cutoff,)
            ).rowcount
        return n

    def set_meta(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

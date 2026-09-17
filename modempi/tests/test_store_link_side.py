"""계약 ⑦ SqliteStore — 링크(wj)가 쓰는 함수들 (store_port.JobStore Protocol, 로드맵 §4.3).

tests/fake_store.py(MemoryStore)가 흉내 내던 의미를 실물이 그대로 지키는지 본다.
"""

import inspect

import pytest

from modempi.link.store_port import JobRow, JobStore, UplinkRow
from modempi.store import SqliteStore

from .conftest import FakeClock


@pytest.fixture
def clk():
    return FakeClock()


@pytest.fixture
def db(clk):
    s = SqliteStore(":memory:", clock=clk)
    yield s
    s.close()


def put(
    s,
    job_id,
    *,
    bld="E",
    room=301,
    unit=1,
    type="SLOT_SET",
    payload="{}",
    priority=3,
    new_ver=1,
    **kw,
):
    return s.put_job(
        job_id=job_id,
        bld=bld,
        room=room,
        unit=unit,
        type=type,
        payload=payload,
        priority=priority,
        new_ver=new_ver,
        **kw,
    )


# ---- Protocol 일치 ----


def test_every_protocol_method_exists_with_same_parameters():
    for name, proto_fn in inspect.getmembers(JobStore, inspect.isfunction):
        if name.startswith("_"):
            continue
        impl = getattr(SqliteStore, name, None)
        assert impl is not None, f"SqliteStore.{name} 없음"
        want = inspect.signature(proto_fn).parameters
        got = inspect.signature(impl).parameters
        assert list(got) == list(want), f"{name}: {list(got)} != {list(want)}"
        for p in want:
            assert got[p].kind == want[p].kind, f"{name}.{p} kind"
            assert got[p].default == want[p].default, f"{name}.{p} default"


# ---- put_job ----


def test_put_job_inserts_received_row(db):
    assert put(db, "7", payload='{"day":1}', new_ver=4) is True
    j = db.get_job("7")
    assert (j.bld, j.room, j.unit, j.type, j.payload, j.priority, j.new_ver) == (
        "E",
        301,
        1,
        "SLOT_SET",
        '{"day":1}',
        3,
        4,
    )
    assert (j.state, j.attempts, j.uploaded, j.parent_id, j.finished_at) == (
        "received",
        0,
        0,
        None,
        None,
    )


def test_put_job_duplicate_is_ignored_and_returns_false(db):
    put(db, "7", payload='{"day":1}')
    assert put(db, "7", payload='{"day":9}', new_ver=2) is False
    assert db.get_job("7").payload == '{"day":1}'


def test_put_job_malformed_row_raises_instead_of_looking_like_duplicate(db):
    """INSERT OR IGNORE 는 NOT NULL 위반도 삼켜 False(=중복)를 돌려준다 → 링크가 job_accepted 를 보내고
    메인은 dispatched 로 둔 채 작업이 사라진다. 중복만 False, 나머지 위반은 예외."""
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        put(db, "7", bld=None)
    assert db.get_job("7") is None


def test_put_job_records_received_at_from_clock(db, clk):
    put(db, "1")
    assert db.get_job("1").received_at == clk.now


def test_put_job_accepts_null_new_ver_and_uploaded_flag(db):
    put(db, "time-1", bld="", room=0, unit=0, type="TIME", priority=0, new_ver=None, uploaded=1)
    j = db.get_job("time-1")
    assert j.new_ver is None and j.uploaded == 1


# ---- cancel_job ----


def test_cancel_only_received_sets_finished_at(db, clk):
    put(db, "1")
    assert db.cancel_job("1") is True
    j = db.get_job("1")
    assert j.state == "cancelled" and j.finished_at == clk.now
    assert db.cancel_job("1") is False  # 이미 cancelled
    assert db.cancel_job("nope") is False


def test_cancel_refuses_sending_row(db):
    put(db, "1")
    db.update("1", state="sending")
    assert db.cancel_job("1") is False
    assert db.get_job("1").state == "sending"


# ---- pending_results / mark_uploaded ----


def test_pending_results_returns_finished_unuploaded_in_finish_order(db, clk):
    for i in ("1", "2", "3"):
        put(db, i)
    put(db, "time-1", type="TIME", priority=0, new_ver=None, uploaded=1)
    db.update("2", state="failed", last_error="no_ack")
    clk.now += 1
    db.update("1", state="acked", ack_status=0, rssi=-90, snr=7.5, attempts=2, txn=9)
    db.update("time-1", state="acked")
    rows = db.pending_results()
    assert [r.job_id for r in rows] == ["2", "1"]  # 3 은 안 끝남, time-1 은 uploaded=1
    assert all(isinstance(r, JobRow) for r in rows)
    r = rows[1]
    assert (r.state, r.ack_status, r.rssi, r.snr, r.attempts, r.txn) == ("acked", 0, -90, 7.5, 2, 9)
    assert rows[0].last_error == "no_ack"


def test_pending_results_includes_cancelled(db):
    put(db, "1")
    db.cancel_job("1")
    assert [(r.job_id, r.state) for r in db.pending_results()] == [("1", "cancelled")]


def test_pending_results_limit(db):
    for i in range(5):
        put(db, str(i))
        db.update(str(i), state="acked")
    assert len(db.pending_results(limit=2)) == 2
    assert db.pending_results(limit=0) == []


def test_mark_uploaded(db):
    for i in ("1", "2"):
        put(db, i)
        db.update(i, state="acked")
    db.mark_uploaded(["1", "nope"])
    assert [r.job_id for r in db.pending_results()] == ["2"]
    db.mark_uploaded([])
    assert db.get_job("1").uploaded == 1


# ---- config ----


def test_set_config_roundtrip_and_replaces(db):
    assert db.get_config() is None
    db.set_config({"net_id": 75, "nodes": [{"bld": "E", "room": 301, "unit": 1}]})
    db.set_config({"net_id": 76, "nodes": []})
    assert db.get_config() == {"net_id": 76, "nodes": []}


# ---- uplinks ----


def test_uplinks_roundtrip_in_insert_order(db):
    a = db.put_uplink({"kind": "HELLO", "mac": "aabbccddeeff", "bld": 0})
    b = db.put_uplink({"kind": "STATUS", "bld": "E", "note": "강의실"})
    rows = db.pending_uplinks()
    assert [r.id for r in rows] == [a, b] and all(isinstance(r, UplinkRow) for r in rows)
    assert rows[1].body == {"kind": "STATUS", "bld": "E", "note": "강의실"}
    db.mark_uplinks_uploaded([a])
    assert [r.id for r in db.pending_uplinks()] == [b]
    assert db.pending_uplinks(limit=0) == []


# ---- meta ----


def test_meta_get_missing_is_none_and_set_overwrites(db):
    assert db.get_meta("modem_fw") is None
    db.set_meta("modem_fw", "0.1.0")
    db.set_meta("modem_fw", "0.2.0")
    assert db.get_meta("modem_fw") == "0.2.0"

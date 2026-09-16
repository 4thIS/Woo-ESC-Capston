from modempi.link.store_port import JobRow, JobStore, UplinkRow

from .fake_store import MemoryStore


def test_memory_store_satisfies_protocol():
    s: JobStore = MemoryStore()  # 타입상 만족 — runtime 은 아래 동작으로 확인
    assert isinstance(s, MemoryStore)


def test_put_job_is_idempotent_and_returns_false_on_dup():
    s = MemoryStore()
    assert (
        s.put_job(
            job_id="7",
            bld="E",
            room=301,
            unit=1,
            type="SLOT_SET",
            payload='{"day":1}',
            priority=3,
            new_ver=1,
        )
        is True
    )
    assert (
        s.put_job(
            job_id="7",
            bld="E",
            room=301,
            unit=1,
            type="SLOT_SET",
            payload='{"day":9}',
            priority=3,
            new_ver=2,
        )
        is False
    )
    assert s.jobs["7"]["payload"] == '{"day":1}' and s.jobs["7"]["state"] == "received"


def test_cancel_only_received_and_sets_finished_at():
    s = MemoryStore()
    s.put_job(
        job_id="1", bld="E", room=301, unit=1, type="CMD", payload="{}", priority=3, new_ver=None
    )
    assert s.cancel_job("1") is True and s.jobs["1"]["state"] == "cancelled"
    assert s.jobs["1"]["finished_at"] is not None
    assert s.cancel_job("1") is False  # 이미 cancelled
    assert s.cancel_job("nope") is False


def test_pending_results_and_mark_uploaded():
    s = MemoryStore()
    for i in ("1", "2", "3"):
        s.put_job(
            job_id=i, bld="E", room=301, unit=1, type="CMD", payload="{}", priority=3, new_ver=None
        )
    s.put_job(
        job_id="time-1",
        bld="",
        room=0,
        unit=0,
        type="TIME",
        payload="{}",
        priority=0,
        new_ver=None,
        uploaded=1,
    )
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

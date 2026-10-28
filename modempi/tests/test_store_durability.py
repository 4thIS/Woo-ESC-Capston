"""계약 ⑦ SqliteStore — 파일 DB 영속·재기동 복구·스키마 버전·보관 정리 (로드맵 §4.4 오프라인 동작)."""

import sqlite3

import pytest

from modempi.store import SCHEMA_VERSION, SqliteStore

from .conftest import FakeClock


@pytest.fixture
def clk():
    return FakeClock()


@pytest.fixture
def path(tmp_path):
    return str(tmp_path / "jobs.db")


def put(s, job_id, *, unit=1, type="SLOT_SET", payload="{}", **kw):
    return s.put_job(
        job_id=job_id,
        bld="E",
        room=301,
        unit=unit,
        type=type,
        payload=payload,
        priority=5,
        new_ver=1,
        **kw,
    )


def test_everything_survives_reopen(path, clk):
    s = SqliteStore(path, clock=clk)
    put(s, "1")
    s.set_config({"net_id": 75})
    s.set_meta("modem_fw", "0.1.0")
    s.put_uplink({"kind": "HELLO"})
    assert s.next_txn("E", 301, 1) == 1
    s.close()

    s = SqliteStore(path, clock=clk)
    assert s.get_job("1").state == "received"
    assert s.get_config() == {"net_id": 75}
    assert s.get_meta("modem_fw") == "0.1.0"
    assert [u.body for u in s.pending_uplinks()] == [{"kind": "HELLO"}]
    assert s.next_txn("E", 301, 1) == 2  # 재부팅 후 같은 TXN 재사용 없음
    s.close()


def test_recover_returns_interrupted_rows_and_clears_retry_wait(path, clk):
    """송신 중 프로세스가 죽으면 sending 이 남아 그 노드가 영영 막힌다 → 파이프라인이 기동 시 recover().
    재시도 대기(next_try_at)도 비운다 — RTC 없는 Pi 가 fake-hwclock 로 과거 시각에 깨면 대기가 최대 1 h 늘어난다."""
    s = SqliteStore(path, clock=clk)
    put(s, "1")
    put(s, "2", unit=2)
    put(s, "3", unit=3)
    s.update("1", state="sending", attempts=1, txn=42)
    s.update("2", state="acked")
    s.update("3", attempts=2, next_try_at=clk.now + 3600)
    s.close()

    s = SqliteStore(path, clock=clk)
    assert s.get_job("1").state == "sending"  # 여는 것만으로는 안 바뀐다
    assert s.recover() == 2
    j = s.get_job("1")
    assert (j.state, j.attempts, j.txn) == ("received", 1, 42)  # txn 유지 — 재송은 같은 TXN(DUP)
    assert s.get_job("2").state == "acked"
    assert s.get_job("3").next_try_at is None
    assert s.pick_next().job_id == "1"
    s.close()


def test_second_instance_does_not_disturb_in_flight_row(path, clk):
    """디버그 스크립트가 같은 파일을 열어도 워커의 sending 행을 되돌리지 않는다."""
    s = SqliteStore(path, clock=clk)
    put(s, "1")
    s.update("1", state="sending")
    other = SqliteStore(path, clock=clk)
    other.close()
    assert s.cancel_job("1") is False
    assert s.get_job("1").state == "sending"
    s.close()


def test_failed_transaction_body_leaves_no_open_transaction(path, clk):
    s = SqliteStore(path, clock=clk)
    put(s, "1")
    with pytest.raises(sqlite3.Error):
        s.mark_uploaded(["1", {"not": "bindable"}])
    assert not s._conn.in_transaction
    put(s, "2")  # 이후 단일 문장 쓰기가 열린 트랜잭션에 갇히지 않고 커밋된다
    with sqlite3.connect(path) as c:
        assert c.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 2
    s.close()


def test_external_writer_lock_fails_fast_instead_of_freezing_loop(path, clk):
    import time

    s = SqliteStore(path, clock=clk, busy_timeout=0.05)
    other = sqlite3.connect(path, isolation_level=None)
    other.execute("BEGIN IMMEDIATE")
    t0 = time.perf_counter()
    with pytest.raises(sqlite3.OperationalError):
        put(s, "1")
    assert time.perf_counter() - t0 < 1.0
    other.execute("ROLLBACK")
    other.close()
    s.close()


def test_older_schema_is_migrated_step_by_step(path, monkeypatch):
    import modempi.store as store_mod

    SqliteStore(path).close()  # v1 DB
    monkeypatch.setattr(store_mod, "SCHEMA_VERSION", 2)
    monkeypatch.setattr(store_mod, "_MIGRATIONS", {2: "ALTER TABLE jobs ADD COLUMN extra TEXT;"})
    SqliteStore(path).close()
    with sqlite3.connect(path) as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == 2
        cols = [r[1] for r in c.execute("PRAGMA table_info(jobs)")]
    assert "extra" in cols
    SqliteStore(path).close()  # 다시 열어도 마이그레이션을 재실행하지 않는다(ALTER 중복 오류 없음)


def test_schema_version_is_recorded(path):
    SqliteStore(path).close()
    with sqlite3.connect(path) as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_newer_schema_is_refused(path):
    SqliteStore(path).close()
    with sqlite3.connect(path) as c:
        c.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    with pytest.raises(RuntimeError):
        SqliteStore(path)


def test_file_db_uses_wal(path):
    s = SqliteStore(path)
    with sqlite3.connect(path) as c:
        assert c.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    s.close()


# ---- prune ----


def test_prune_deletes_only_old_uploaded_finished_rows(path, clk):
    s = SqliteStore(path, clock=clk)
    put(s, "old-acked", type="FILE", payload='{"records": ["큰 레코드"]}')
    put(s, "old-not-uploaded", unit=2)
    put(s, "old-received", unit=3)
    s.update("old-acked", state="acked")
    s.update("old-not-uploaded", state="failed")
    s.mark_uploaded(["old-acked"])
    a = s.put_uplink({"kind": "HELLO"})
    b = s.put_uplink({"kind": "STATUS"})
    s.mark_uplinks_uploaded([a])

    clk.now += 8 * 86400
    put(s, "new-acked", unit=4)
    s.update("new-acked", state="acked")
    s.mark_uploaded(["new-acked"])

    assert s.prune(older_than=7 * 86400) == 2  # old-acked 1행 + 업로드된 업링크 1행
    assert s.get_job("old-acked") is None
    assert s.get_job("old-not-uploaded") is not None  # 아직 메인에 못 보냄
    assert s.get_job("old-received") is not None  # 안 끝남
    assert s.get_job("new-acked") is not None  # 보관 기간 안
    assert [u.id for u in s.pending_uplinks()] == [b]
    s.close()

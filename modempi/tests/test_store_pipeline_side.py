"""계약 ⑦ SqliteStore — 파이프라인(cw)이 쓰는 함수들 (로드맵 §4.3, S6 spec §2·§4.3)."""

import json

import pytest

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
    priority=5,
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


# ---- pick_next (v2 §8.4 순서) ----


def test_pick_next_empty_is_none(db):
    assert db.pick_next() is None


def test_pick_next_orders_by_priority_then_received_at(db, clk):
    put(db, "a", unit=1, priority=5)
    clk.now += 1
    put(db, "b", unit=2, priority=3)
    clk.now += 1
    put(db, "c", unit=3, priority=3)
    assert db.pick_next().job_id == "b"
    db.update("b", state="acked")
    assert db.pick_next().job_id == "c"
    db.update("c", state="acked")
    assert db.pick_next().job_id == "a"


def test_pick_next_does_not_change_state(db):
    put(db, "a")
    assert db.pick_next().job_id == "a"
    assert db.get_job("a").state == "received"


def test_pick_next_waits_for_next_try_at(db, clk):
    put(db, "a", priority=1)
    put(db, "b", unit=2, priority=9)
    db.update("a", next_try_at=clk.now + 20)
    assert db.pick_next().job_id == "b"  # a 는 아직 대기
    db.update("b", state="acked")
    assert db.pick_next() is None
    clk.now += 20
    assert db.pick_next().job_id == "a"  # 경계 포함 (<=)


def test_pick_next_skips_node_with_sending_row(db, clk):
    put(db, "a1", unit=1, priority=1)
    put(db, "a2", unit=1, priority=1)
    clk.now += 1
    put(db, "b1", unit=2, priority=9)
    db.update("a1", state="sending")
    assert db.pick_next().job_id == "b1"  # a2 는 같은 노드에 sending 이 있어 건너뜀
    db.update("b1", state="sending")
    assert db.pick_next() is None
    db.update("a1", state="acked")
    assert db.pick_next().job_id == "a2"


def test_retry_waiting_row_keeps_its_place_for_its_node(db, clk):
    """v2 §3.5 "프레임 순서는 워커가 (room, unit) FIFO 로 보장". v1 이 no_ack 로 재시도 대기 중일 때
    같은 노드의 v2 를 먼저 보내면 노드는 GAP → 메인이 FILE 재동기를 큐잉한다. 대기 행이 순번을 지킨다."""
    put(db, "10", unit=1, new_ver=1)
    clk.now += 1
    put(db, "11", unit=1, new_ver=2)
    put(db, "12", unit=2)
    db.update("10", state="received", attempts=1, next_try_at=clk.now + 5)
    assert db.pick_next().job_id == "12"  # 다른 노드는 막히지 않는다
    db.update("12", state="acked")
    assert db.pick_next() is None  # 11 은 10 뒤에서 기다린다
    clk.now += 5
    assert db.pick_next().job_id == "10"
    db.update("10", state="acked")
    assert db.pick_next().job_id == "11"


def test_node_is_fifo_by_main_job_id_not_priority_or_arrival(db, clk):
    """메인 job_id(outbox id)는 생성 순 = 버전 순. 같은 노드 안에서는 priority 도 도착 순서도 무시한다.

    FILE v5(id 100, priority 5) 가 SLOT_SET v6(id 101, priority 3) 보다 먼저 만들어졌는데
    SLOT_SET 이 먼저 나가면 노드 4→6 GAP, 이어 온 FILE v5 가 최신 편집을 덮어 잘못된 화면이 뜬다.
    허브가 (priority, id) 순으로 몰아 보내 도착 순서가 뒤집혀도 id 순을 지킨다."""
    put(db, "101", unit=1, type="SLOT_SET", priority=3, new_ver=6)
    clk.now += 1
    put(db, "100", unit=1, type="FILE", priority=5, new_ver=5)
    assert db.pick_next().job_id == "100"
    db.update("100", state="acked")
    assert db.pick_next().job_id == "101"


def test_node_fifo_holds_when_head_waits_for_retry(db, clk):
    put(db, "100", unit=1, priority=5)
    put(db, "101", unit=1, priority=1)
    db.update("100", next_try_at=clk.now + 60)
    assert db.pick_next() is None  # 우선순위가 높아도 같은 노드의 앞 작업을 추월하지 않는다


def test_priority_still_orders_heads_of_different_nodes(db, clk):
    put(db, "100", unit=1, priority=5)
    clk.now += 1
    put(db, "101", unit=2, priority=1)
    assert db.pick_next().job_id == "101"


def test_non_numeric_ids_on_same_node_fall_back_to_arrival_order(db, clk):
    put(db, "time-200", bld="", room=0, unit=0, type="TIME", priority=0, new_ver=None)
    clk.now += 1
    put(db, "time-100", bld="", room=0, unit=0, type="TIME", priority=0, new_ver=None)
    assert db.pick_next().job_id == "time-200"


def test_failed_row_no_longer_blocks_its_node(db, clk):
    put(db, "10", unit=1)
    clk.now += 1
    put(db, "11", unit=1)
    db.update("10", next_try_at=clk.now + 60)
    assert db.pick_next() is None
    db.update("10", state="failed", last_error="no_ack")
    assert db.pick_next().job_id == "11"


def test_pick_next_stays_fast_with_large_backlog(db):
    """CSV 임포트는 호실마다 FILE 을 큐잉한다(~300호 × 2유닛). pick_next 는 루프에서 0.5 s 마다 돈다."""
    import time as _t

    for i in range(1500):
        put(db, str(1000 + i), room=100 + i % 750, unit=1 + i % 2)
    best = min(_timed(db.pick_next, _t) for _ in range(3))
    assert best < 0.025, f"pick_next {best * 1000:.1f} ms"


def _timed(fn, t):
    t0 = t.perf_counter()
    fn()
    return t.perf_counter() - t0


def test_sending_on_other_room_or_bld_does_not_block(db):
    put(db, "x", bld="E", room=301, unit=1)
    put(db, "y", bld="E", room=302, unit=1)
    put(db, "z", bld="F", room=301, unit=1)
    db.update("x", state="sending")
    assert db.pick_next().job_id == "y"
    db.update("y", state="sending")
    assert db.pick_next().job_id == "z"


@pytest.mark.parametrize("state", ["sending", "acked", "failed", "cancelled"])
def test_pick_next_only_takes_received(db, state):
    put(db, "a")
    db.update("a", state=state)
    assert db.pick_next() is None


def test_pick_next_returns_full_row(db):
    put(db, "a", payload='{"day":2}', priority=2, new_ver=7)
    db.update("a", attempts=1, next_try_at=0.0)
    j = db.pick_next()
    assert (j.type, j.payload, j.priority, j.new_ver, j.attempts, j.parent_id) == (
        "SLOT_SET",
        '{"day":2}',
        2,
        7,
        1,
        None,
    )


# ---- update ----


def test_update_terminal_state_fills_finished_at(db, clk):
    put(db, "a")
    clk.now += 3
    assert db.update("a", state="failed", last_error="no_ack", attempts=3) is True
    j = db.get_job("a")
    assert (j.state, j.last_error, j.attempts, j.finished_at) == ("failed", "no_ack", 3, clk.now)


def test_update_cancelled_also_fills_finished_at(db, clk):
    put(db, "a")
    db.update("a", state="cancelled")
    assert db.get_job("a").finished_at == clk.now
    assert [r.job_id for r in db.pending_results()] == ["a"]


def test_update_explicit_none_finished_at_is_still_filled(db, clk):
    put(db, "a")
    db.update("a", state="acked", finished_at=None)
    assert db.get_job("a").finished_at == clk.now


def test_split_state_no_longer_exists(db):
    """메인Pi 가 unit=0 을 유닛별 outbox 로 이미 분해한다(api._insert). 모뎀Pi 분해 경로는 계약 ⑦ r6 에서 삭제."""
    put(db, "a")
    with pytest.raises(ValueError):
        db.update("a", state="split")
    assert not hasattr(db, "add_subjobs")


def test_update_explicit_finished_at_is_kept(db):
    put(db, "a")
    db.update("a", state="acked", finished_at=123.0)
    assert db.get_job("a").finished_at == 123.0


def test_update_requeue_does_not_finish(db, clk):
    put(db, "a")
    db.update("a", state="sending")
    db.update("a", state="received", attempts=1, next_try_at=clk.now + 5, last_error="no_ack")
    j = db.get_job("a")
    assert (j.state, j.attempts, j.finished_at) == ("received", 1, None)


def test_update_node_vers_dict_is_stored_as_json(db):
    put(db, "a")
    db.update("a", state="acked", node_vers={"sched": 3, "resv": 1, "exam": 0, "ident": 2})
    assert json.loads(db.get_job("a").node_vers) == {"sched": 3, "resv": 1, "exam": 0, "ident": 2}
    assert json.loads(db.pending_results()[0].node_vers)["sched"] == 3


def test_update_missing_job_returns_false(db):
    assert db.update("nope", state="acked") is False


def test_update_rejects_unknown_or_fixed_column(db):
    put(db, "a")
    for bad in ({"payload": "{}"}, {"bld": "F"}, {"job_id": "b"}, {"nonsense": 1}):
        with pytest.raises(ValueError):
            db.update("a", **bad)
    assert db.get_job("a").payload == "{}"


def test_update_rejects_unknown_state(db):
    put(db, "a")
    with pytest.raises(ValueError):
        db.update("a", state="done")


def test_update_with_no_fields_is_value_error(db):
    put(db, "a")
    with pytest.raises(ValueError):
        db.update("a")


def test_update_expect_state_guards_race_with_cancel(db):
    """pick_next 와 update(sending) 사이에 링크가 cancel 하면 sending 으로 덮어쓰지 않는다."""
    put(db, "a")
    assert db.pick_next().job_id == "a"
    db.cancel_job("a")
    assert db.update("a", expect_state="received", state="sending") is False
    assert db.get_job("a").state == "cancelled"
    put(db, "b", unit=2)
    assert db.update("b", expect_state="received", state="sending") is True


# ---- next_txn ----


def test_next_txn_starts_at_1_and_increments_per_node(db):
    assert [db.next_txn("E", 301, 1) for _ in range(3)] == [1, 2, 3]
    assert db.next_txn("E", 301, 2) == 1
    assert db.next_txn("F", 301, 1) == 1
    assert db.next_txn("E", 301, 1) == 4


def test_next_txn_rolls_255_to_1_skipping_0(db):
    seen = [db.next_txn("E", 301, 1) for _ in range(256)]
    assert seen[254] == 255 and seen[255] == 1
    assert 0 not in seen


# ---- config 이벤트 ----


def test_on_config_changed_called_after_store(db):
    got = []
    db.on_config_changed(lambda cfg: got.append((cfg, db.get_config())))
    db.set_config({"net_id": 75})
    assert got == [({"net_id": 75}, {"net_id": 75})]


def test_config_callback_error_does_not_break_link_or_other_callbacks(db):
    got = []

    def boom(cfg):
        raise RuntimeError("pipeline bug")

    db.on_config_changed(boom)
    db.on_config_changed(got.append)
    db.set_config({"net_id": 1})  # 예외가 링크로 올라가지 않는다
    assert got == [{"net_id": 1}]
    assert db.get_config() == {"net_id": 1}


# ---- uplink ids ----


def test_put_uplink_ids_increase(db):
    a = db.put_uplink({"kind": "HELLO"})
    b = db.put_uplink({"kind": "STATUS"})
    assert b > a


# ---- newer_pending (쌓인 TIME 정리, #35 리뷰 4) ----


def test_newer_pending_sees_only_later_received_rows_of_same_node_and_type(db, clk):
    put(db, "time-1", bld="", room=0, unit=0, type="TIME", priority=0, new_ver=None)
    clk.now += 1
    put(db, "time-2", bld="", room=0, unit=0, type="TIME", priority=0, new_ver=None)
    put(db, "time-3-E301-1", bld="E", room=301, unit=1, type="TIME", priority=0, new_ver=None)
    assert db.newer_pending(db.get_job("time-1")) is True
    assert db.newer_pending(db.get_job("time-2")) is False  # 다른 노드의 TIME 은 무관
    db.update("time-2", state="acked")
    assert db.newer_pending(db.get_job("time-1")) is False  # 끝난 행은 세지 않는다

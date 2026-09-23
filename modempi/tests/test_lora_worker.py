import asyncio
import contextlib
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

SLOT = {
    "day": 1,
    "s_h": 9,
    "s_m": 0,
    "e_h": 9,
    "e_m": 50,
    "type": 1,
    "subject": "자료구조",
    "professor": "김교수",
}


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
    db.put_job(
        job_id=job_id,
        bld="E",
        room=301,
        unit=unit,
        type=type,
        payload=json.dumps(payload if payload is not None else SLOT),
        priority=priority,
        new_ver=new_ver,
        **kw,
    )


def slot_records(n: int) -> list[dict]:
    """FILE 청크(200 B)를 여러 개 만들 만큼의 슬롯 레코드. 24개 ≈ 624 B → DATA 4개."""
    return [
        dict(SLOT, day=1 + i % 7, s_h=8 + i // 7, e_h=8 + i // 7, subject=f"과목{i}")
        for i in range(n)
    ]


def sent(modem) -> list[dict]:
    """모뎀이 실제로 받은 tx 프레임들 — 헤더의 txn·type (FILE_DATA 는 seq 까지)."""
    out = []
    for who, msg in modem.log:
        if who != "host" or msg.get("op") != "tx":
            continue
        h, pb = C.decode_frame(bytes.fromhex(msg["frame"]))
        info = {"txn": h.txn, "type": h.type}
        if h.type == P.Type.FILE_DATA:
            info["seq"] = pb[0]
        out.append(info)
    return out


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


async def test_retry_reuses_same_txn_so_node_answers_dup(rig, clk):
    """ACK 유실 후 재송이 새 TXN 이면 노드는 (v−v) mod 255 = 0 → GAP. 같은 TXN 이어야 DUP."""
    db, modem, _, w = rig
    node = modem.nodes[(ord("E"), 301, 1)]
    modem.script(["no_ack"])
    put(db, new_ver=3)
    await w.once()  # 노드는 받아서 적용했지만 ACK 가 사라졌다 — 그 상태를 직접 만든다
    first_txn = db.get_job("10").txn
    node.last_txn, node.sched_ver = first_txn, 3
    clk.now += 5.0  # 재시도 대기
    await w.once()  # 재송
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
    db, _, _, w = rig
    put(db, new_ver=9)  # 노드 sched_ver=2 → 버전 불연속
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
    assert modem.stats["tx"] == 2  # 같은 프레임 즉시 1회 재송


async def test_cancelled_between_pick_and_claim_is_not_sent(rig):
    """`pick_next` 는 상태를 바꾸지 않는다 — 집기(`expect_state`)가 False 면 보내지 않고 넘어간다."""
    db, modem, _, w = rig
    put(db)
    real_pick = db.pick_next

    def pick_then_cancel():
        job = real_pick()
        if job is not None:
            db.cancel_job(job.job_id)  # 그 사이 링크가 취소했다
        return job

    db.pick_next = pick_then_cancel
    assert await w.once() is True
    assert db.get_job("10").state == "cancelled"
    assert modem.stats["tx"] == 0


async def test_unit0_job_fails_with_unit0(rig):
    db, _, _, w = rig
    put(db, unit=0)
    await w.once()
    assert (db.get_job("10").state, db.get_job("10").last_error) == ("failed", "unit0")


async def test_time_row_is_sent_without_ack_and_stale_one_is_superseded(rig, clk):
    db, _, _, w = rig
    db.put_job(
        job_id="time-old",
        bld="",
        room=0,
        unit=0,
        type="TIME",
        payload=json.dumps({"epoch": int(clk.now) - 3600, "flags": 0}),
        priority=0,
        new_ver=None,
        uploaded=1,
    )
    db.put_job(
        job_id="time-new",
        bld="",
        room=0,
        unit=0,
        type="TIME",
        payload=json.dumps({"epoch": int(clk.now), "flags": 0}),
        priority=0,
        new_ver=None,
        uploaded=1,
    )
    await w.once()
    old = db.get_job("time-old")
    assert (old.state, old.last_error) == ("acked", "superseded")
    await w.once()
    assert db.get_job("time-new").state == "acked"


async def test_file_session_sends_begin_data_end_each_with_new_txn(rig):
    db, modem, _, w = rig
    node = modem.nodes[(ord("E"), 301, 1)]
    recs = slot_records(24)
    put(db, type="FILE", new_ver=3, payload={"kind": int(P.FileKind.SCHEDULE), "records": recs})
    await w.once()
    j = db.get_job("10")
    assert (j.state, j.ack_status) == ("acked", int(P.AckStatus.OK))
    assert node.sched_ver == 3 and len(node.files[int(P.FileKind.SCHEDULE)]) == len(recs)
    txns = [f["txn"] for f in sent(modem)]
    assert len(txns) == modem.stats["tx"] and len(set(txns)) == len(txns)  # 프레임마다 새 TXN


async def test_file_missing_resends_from_that_seq(rig):
    db, modem, _, w = rig
    node = modem.nodes[(ord("E"), 301, 1)]
    recs = slot_records(24)
    put(db, type="FILE", new_ver=3, payload={"kind": int(P.FileKind.SCHEDULE), "records": recs})
    modem.drop_next_file_data(1)
    await w.once()
    assert db.get_job("10").state == "acked"
    assert node.sched_ver == 3 and len(node.files[int(P.FileKind.SCHEDULE)]) == len(recs)
    seqs = [f["seq"] for f in sent(modem) if f["type"] == P.Type.FILE_DATA]
    assert seqs == [0, 1, 2, 3, 1, 2, 3]  # FILE_MISSING(1) 뒤 그 seq 부터 재송


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


async def test_run_recovers_sending_row_and_resends_with_same_txn(rig):
    """송신 도중 죽은 행: `run()` 이 `recover()` 로 되돌리고 **같은 TXN** 으로 재송 → 노드는 DUP."""
    db, modem, _, w = rig
    node = modem.nodes[(ord("E"), 301, 1)]
    put(db, new_ver=3)
    txn = db.next_txn("E", 301, 1)
    db.update("10", expect_state="received", state="sending", txn=txn)
    node.last_txn, node.sched_ver = txn, 3  # 노드는 적용했는데 모뎀Pi 가 그 사이 죽었다
    stop = asyncio.Event()
    task = asyncio.create_task(w.run(stop))
    for _ in range(50):
        await asyncio.sleep(0.01)
        if db.get_job("10").state == "acked":
            break
    stop.set()
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    j = db.get_job("10")
    assert j.txn == txn
    assert (j.state, j.ack_status) == ("acked", int(P.AckStatus.DUP))


async def test_time_uses_txn_0_and_does_not_consume_the_node_counter(rig, clk):
    """타겟 TIME 이 노드 TXN 을 먹으면 그 노드의 재송이 DUP 이 아니게 되어 GAP → FILE 재동기가 걸린다.
    TIME 은 버전도 없고 멱등이라 txn=0 으로 보내고 노드는 DUP 판정에서 제외한다(v2 §3.5 · S6 §9 결정)."""
    db, _, _, w = rig
    db.put_job(
        job_id=f"time-{int(clk.now)}-E301-1",
        bld="E",
        room=301,
        unit=1,
        type="TIME",
        payload=json.dumps({"epoch": int(clk.now), "flags": 0}),
        priority=0,
        new_ver=None,
        uploaded=1,
    )
    assert await w.once() is True
    j = db.get_job(f"time-{int(clk.now)}-E301-1")
    assert (j.state, j.txn) == ("acked", 0)
    assert db.next_txn("E", 301, 1) == 1  # 카운터가 그대로 — TIME 이 먹지 않았다


async def test_targeted_time_between_send_and_retry_keeps_the_retry_txn(rig, clk):
    db, modem, _, w = rig
    modem.script(["no_ack"])
    put(db)
    await w.once()
    first_txn = db.get_job("10").txn
    db.put_job(
        job_id=f"time-{int(clk.now)}-E301-1",
        bld="E",
        room=301,
        unit=1,
        type="TIME",
        payload=json.dumps({"epoch": int(clk.now), "flags": 0}),
        priority=0,
        new_ver=None,
        uploaded=1,
    )
    await w.once()  # 타겟 TIME 이 끼어든다
    clk.now += 5.0
    await w.once()  # 원래 작업 재송
    assert db.get_job("10").txn == first_txn


async def test_file_session_gives_up_after_repeated_busy(rig, clk):
    """BUSY 는 세션을 유지한 채 5 s 뒤 같은 프레임 재송이지만, 무한히 반복하면 워커가 영영 안 돌아온다."""
    db, modem, _, w = rig
    modem.script(["ack:BUSY"] * 12)
    put(
        db,
        type="FILE",
        new_ver=3,
        payload={"kind": int(P.FileKind.SCHEDULE), "records": slot_records(24)},
    )
    await asyncio.wait_for(w.once(), 3)
    j = db.get_job("10")
    assert j.state == "received" and j.attempts == 1  # 세션 실패 → 일반 재시도 정책으로


async def test_time_is_held_back_while_clock_is_untrusted(rig, clk):
    """메인의 time_now 로 들어온 TIME 도 워커를 거친다. 시계를 못 믿으면 옛 시각을 방송하지 않고 미룬다."""
    db, modem, client, _ = rig
    w = Worker(db, client, clock=clk, sleep=clk.sleep, clock_ok=lambda now: False)
    jid = f"time-{int(clk.now)}"
    db.put_job(
        job_id=jid,
        bld="",
        room=0,
        unit=0,
        type="TIME",
        payload=json.dumps({"epoch": int(clk.now), "flags": 0}),
        priority=0,
        new_ver=None,
        uploaded=1,
    )
    assert await w.once() is True
    j = db.get_job(jid)
    assert (j.state, j.next_try_at, j.attempts) == ("received", clk.now + 60.0, 0)
    assert modem.stats["tx"] == 0

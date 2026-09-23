import asyncio
import json
import logging

import pytest
from lora_proto import codec as C
from lora_proto import proto as P

from modempi.lora.modem_client import RxEvent
from modempi.lora.uplink import UplinkReader
from modempi.store import SqliteStore

from .conftest import E, FakeClock, frame

pytestmark = pytest.mark.anyio

MAC = "a0b1c2d3e4f5"


@pytest.fixture
def db():
    s = SqliteStore(":memory:")
    yield s
    s.close()


def status_frame(flags=0, *, bld=E, rssi_last=-90, snr_last_x4=20):
    ack = C.Ack(P.AckStatus.OK, 0, 3900, 2, 1, 0, 1, 20, int(P.Layout.CLASS))
    return frame(
        P.Type.STATUS,
        C.Status(ack, rssi_last, snr_last_x4, flags, 42),
        bld=bld,
        room=301,
        unit=1,
        txn=0,
        flags=0,
    )


def hello_frame():
    return frame(
        P.Type.HELLO,
        C.Hello(bytes.fromhex(MAC), 20, 4000),
        bld=P.BLD_UNPROVISIONED,
        room=0,
        unit=0,
        txn=0,
        flags=0,
    )


def test_status_becomes_uplink_row(db):
    r = UplinkReader(db, client=None)
    assert r.handle(RxEvent(status_frame(), -95, 4.0)) == "STATUS"
    [row] = db.pending_uplinks()
    assert row.body["kind"] == "STATUS" and row.body["bld"] == "E" and row.body["room"] == 301
    assert row.body["sched_ver"] == 2 and row.body["rssi"] == -95 and row.body["uptime_h"] == 42


def test_status_body_matches_contract_6_exactly(db):
    """로드맵 §4.2 인코딩 규칙 — Ack 필드명 그대로 평탄화 + rssi_last·snr_last_x4·flags·uptime_h,
    rssi/snr 는 모뎀이 잰 링크 값. 메인 `api.on_uplink` 가 이 키를 읽는다."""
    UplinkReader(db, client=None).handle(
        RxEvent(status_frame(int(P.StatusFlag.LOW_BATT), snr_last_x4=-8), -95, 4.5)
    )
    [row] = db.pending_uplinks()
    assert row.body == {
        "kind": "STATUS",
        "bld": "E",
        "room": 301,
        "unit": 1,
        "mac": None,
        "status": int(P.AckStatus.OK),
        "detail": 0,
        "batt_mv": 3900,
        "sched_ver": 2,
        "resv_ver": 1,
        "exam_ver": 0,
        "ident_ver": 1,
        "fw": 20,
        "layout": int(P.Layout.CLASS),
        "rssi_last": -90,
        "snr_last_x4": -8,
        "flags": int(P.StatusFlag.LOW_BATT),
        "uptime_h": 42,
        "rssi": -95,
        "snr": 4.5,
    }


def test_hello_mac_is_hex_string(db):
    r = UplinkReader(db, client=None)
    assert r.handle(RxEvent(hello_frame(), -100, 3.0)) == "HELLO"
    [row] = db.pending_uplinks()
    assert row.body["mac"] == MAC and row.body["bld"] == 0


def test_hello_body_matches_contract_6_exactly(db):
    UplinkReader(db, client=None).handle(RxEvent(hello_frame(), -100, 3.0))
    [row] = db.pending_uplinks()
    assert row.body == {
        "kind": "HELLO",
        "bld": 0,
        "room": 0,
        "unit": 0,
        "mac": MAC,
        "fw": 20,
        "batt_mv": 4000,
        "rssi": -100,
        "snr": 3.0,
    }


def test_clock_stale_queues_targeted_time(db):
    clk = FakeClock()
    r = UplinkReader(db, client=None, clock=clk)
    r.handle(RxEvent(status_frame(int(P.StatusFlag.CLOCK_STALE)), -95, 4.0))
    job = db.pick_next()
    assert (job.type, job.bld, job.room, job.unit, job.uploaded) == ("TIME", "E", 301, 1, 1)
    assert (job.priority, job.new_ver) == (0, None)
    assert json.loads(job.payload) == {"epoch": int(clk.now), "flags": 0}
    assert len(db.pending_uplinks()) == 1  # STATUS 자체도 올라간다


def test_clock_stale_twice_in_same_second_queues_one_time(db):
    clk = FakeClock(start=1_800_000_000.25)
    r = UplinkReader(db, client=None, clock=clk)
    stale = status_frame(int(P.StatusFlag.CLOCK_STALE))
    r.handle(RxEvent(stale, -95, 4.0))
    clk.now += 0.5  # 같은 초
    r.handle(RxEvent(stale, -96, 4.0))
    times = db._conn.execute("SELECT job_id FROM jobs WHERE type = 'TIME'").fetchall()
    assert [t[0] for t in times] == ["time-1800000000-E301-1"]
    assert len(db.pending_uplinks()) == 2  # STATUS 두 건은 모두 올린다


def test_status_without_clock_stale_queues_nothing(db):
    UplinkReader(db, client=None).handle(RxEvent(status_frame(), -95, 4.0))
    assert db.pick_next() is None


def test_garbage_frame_is_dropped(db):
    assert UplinkReader(db, client=None).handle(RxEvent(b"\x00\x01\x02", -95, 4.0)) is None
    assert db.pending_uplinks() == []


@pytest.mark.parametrize(
    "mangle",
    [
        pytest.param(lambda f: f[:-1] + bytes([f[-1] ^ 0xFF]), id="bad_crc"),
        pytest.param(lambda f: f[:1] + bytes([f[1] ^ 0xFF]) + f[2:], id="wrong_net_id"),
        pytest.param(lambda f: f[:5], id="too_short"),
    ],
)
def test_bad_frames_are_logged_and_dropped(db, caplog, mangle):
    bad = mangle(status_frame(int(P.StatusFlag.CLOCK_STALE)))
    with caplog.at_level(logging.WARNING, logger="lora.uplink"):
        assert UplinkReader(db, client=None).handle(RxEvent(bad, -95, 4.0)) is None
    assert db.pending_uplinks() == [] and db.pick_next() is None
    assert any(rec.levelno == logging.WARNING for rec in caplog.records)


def test_payload_that_does_not_decode_is_dropped(db):
    """헤더·CRC 는 맞지만 STATUS 페이로드 길이가 틀린 프레임."""
    h = C.Header(type=P.Type.STATUS, bld=E, room=301, unit=1, txn=0, flags=0)
    bad = C.encode_frame(h, b"\x00\x01\x02")
    assert UplinkReader(db, client=None).handle(RxEvent(bad, -95, 4.0)) is None
    assert db.pending_uplinks() == []


def test_late_ack_is_only_logged(db, caplog):
    ack = C.Ack(P.AckStatus.OK, 0, 3900, 2, 1, 0, 1, 20, int(P.Layout.CLASS))
    f = frame(P.Type.ACK, ack, txn=9, flags=0)
    with caplog.at_level(logging.INFO, logger="lora.uplink"):
        assert UplinkReader(db, client=None).handle(RxEvent(f, -95, 4.0)) is None
    assert db.pending_uplinks() == [] and db.pick_next() is None
    assert any("ACK" in rec.getMessage() for rec in caplog.records)


@pytest.mark.parametrize("bld", [P.BLD_UNPROVISIONED, P.BLD_ALL, ord("1")])
def test_status_with_non_letter_bld_is_dropped(db, bld):
    """메인은 bld 를 `[A-Za-z]` 한 글자로 받는다 — 그 밖의 헤더 bld 는 올리지 않는다."""
    f = status_frame(int(P.StatusFlag.CLOCK_STALE), bld=bld)
    assert UplinkReader(db, client=None).handle(RxEvent(f, -95, 4.0)) is None
    assert db.pending_uplinks() == [] and db.pick_next() is None


class _RxOnly:
    def __init__(self):
        self.rx: asyncio.Queue[RxEvent] = asyncio.Queue()


async def test_run_survives_exception_and_keeps_consuming(db, monkeypatch):
    client = _RxOnly()
    r = UplinkReader(db, client=client)
    real_put = db.put_uplink
    calls = {"n": 0}

    def flaky_put(body):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("디스크 가득")
        return real_put(body)

    monkeypatch.setattr(db, "put_uplink", flaky_put)
    stop = asyncio.Event()
    task = asyncio.create_task(r.run(stop))
    await client.rx.put(RxEvent(status_frame(), -95, 4.0))  # 저장 실패 — 버리고 계속
    await client.rx.put(RxEvent(b"\x00", -95, 4.0))  # 쓰레기 — 버리고 계속
    await client.rx.put(RxEvent(hello_frame(), -100, 3.0))
    for _ in range(100):
        if db.pending_uplinks():
            break
        await asyncio.sleep(0.01)
    stop.set()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    [row] = db.pending_uplinks()
    assert row.body["kind"] == "HELLO"

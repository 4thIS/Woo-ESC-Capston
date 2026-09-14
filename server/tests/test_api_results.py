import datetime as dt
import hashlib

from lora_proto import proto as P
from sqlalchemy import select

from app.lora_service import api
from app.lora_service.models import Modem, Outbox, PendingDevice, RoomVersion, TerminalStatus


def _ack(**over):
    base = {
        "state": "acked",
        "ack_status": 0,
        "ack_detail": 0,
        "attempts": 1,
        "txn": 5,
        "rssi": -90,
        "snr": 6.5,
        "sched_ver": 1,
        "resv_ver": 0,
        "exam_ver": 0,
        "ident_ver": 1,
        "batt_mv": 3900,
        "layout": 1,
        "fw": 20,
        "last_error": None,
        "finished_at": 1_800_000_000,
    }
    base.update(over)
    return base


def _dispatch(db, ids):
    with db() as s, s.begin():
        for i in ids:
            s.get(Outbox, i).state = "dispatched"


def test_job_result_acked_updates_row_and_terminal_status(db):
    ids = api.enqueue_slot_set("E", 302, 1, (9, 0), (10, 0), 1, "a", "b")
    _dispatch(db, ids)
    api.on_job_result("m1", {"job_id": ids[0], **_ack()})
    with db() as s:
        r = s.get(Outbox, ids[0])
        assert r.state == "acked" and r.ack_status == 0 and r.rssi == -90 and r.finished_at
        ts = s.get(TerminalStatus, ("E", 302, 1))
        assert ts.sched_ver == 1 and ts.batt_mv == 3900 and ts.sync_state == "synced"
        assert ts.last_ack_at is not None and ts.modem_id == "m1"


def test_job_result_gap_queues_one_file_only(db):
    ids = api.enqueue_slot_set("E", 302, 1, (9, 0), (10, 0), 1, "a", "b")
    _dispatch(db, ids)
    api.on_job_result("m1", {"job_id": ids[0], **_ack(ack_status=int(P.AckStatus.GAP))})
    api.on_job_result("m1", {"job_id": ids[0], **_ack(ack_status=int(P.AckStatus.GAP))})  # 재전송
    with db() as s:
        files = s.scalars(select(Outbox).where(Outbox.type == "FILE")).all()
        assert len(files) == 1 and files[0].unit == 1 and files[0].state == "queued"
        assert s.get(TerminalStatus, ("E", 302, 1)).sync_state == "resync"


def test_job_result_version_mismatch_queues_file(db):
    ids = api.enqueue_slot_set("E", 302, 1, (9, 0), (10, 0), 1, "a", "b")  # schedule ver=1
    _dispatch(db, ids)
    api.on_job_result("m1", {"job_id": ids[0], **_ack(sched_ver=7)})
    with db() as s:
        assert (
            s.scalars(select(Outbox).where(Outbox.type == "FILE"))
            .one()
            .payload.startswith('{"kind": 1')
        )


def test_job_result_failed_and_finished_rows_ignored(db):
    ids = api.enqueue_slot_set("E", 302, 1, (9, 0), (10, 0), 1, "a", "b")
    _dispatch(db, ids)
    api.on_job_result("m1", {"job_id": ids[0], **_ack(state="failed", last_error="no_ack")})
    api.on_job_result("m1", {"job_id": ids[0], **_ack()})  # 이미 끝남 → 무시
    with db() as s:
        r = s.get(Outbox, ids[0])
        assert r.state == "failed" and r.last_error == "no_ack"
        assert s.get(TerminalStatus, ("E", 302, 1)) is None


def test_set_room_acked_deletes_pending_device(db):
    api.on_uplink(
        "m1",
        {
            "kind": "HELLO",
            "bld": 0,
            "room": 0,
            "unit": 0,
            "mac": "aabbccddeeff",
            "fw": 20,
            "batt_mv": 4000,
            "rssi": -100,
            "snr": 3.0,
        },
    )
    with db() as s:
        assert s.get(PendingDevice, "aabbccddeeff").modem_id == "m1"
    oid = api.provision("aabbccddeeff", "E", 302, 1)
    _dispatch(db, [oid])
    api.on_job_result("m1", {"job_id": oid, **_ack(ident_ver=1)})
    with db() as s:
        assert s.get(PendingDevice, "aabbccddeeff") is None


def test_uplink_status_updates_terminal_and_flags(db):
    api.on_uplink(
        "m1",
        {
            "kind": "STATUS",
            "bld": "E",
            "room": 302,
            "unit": 1,
            "mac": None,
            "status": 0,
            "detail": 0,
            "batt_mv": 3400,
            "sched_ver": 0,
            "resv_ver": 0,
            "exam_ver": 0,
            "ident_ver": 1,
            "fw": 20,
            "layout": 4,
            "rssi_last": -95,
            "snr_last_x4": 24,
            "flags": int(P.StatusFlag.LOW_BATT),
            "uptime_h": 100,
            "rssi": -98,
            "snr": 4.0,
        },
    )
    with db() as s:
        ts = s.get(TerminalStatus, ("E", 302, 1))
        assert ts.low_batt is True and ts.clock_stale is False and ts.uptime_h == 100
        assert (
            ts.last_status_at is not None and ts.sync_state == "synced"
        )  # 버전 행 없음 = 비교 생략


def test_modem_token_roundtrip(db):
    tok = api.register_modem("m1")
    assert api.verify_token("m1", tok) and not api.verify_token("m1", "x")
    assert not api.verify_token("nope", tok)
    tok2 = api.rotate_token("m1")
    assert tok2 != tok and api.verify_token("m1", tok2) and not api.verify_token("m1", tok)
    with db() as s:
        assert s.get(Modem, "m1").token_hash == hashlib.sha256(tok2.encode()).hexdigest()
    api.touch_modem("m1", connected=True, agent_ver="0.1", modem_fw="gw-2.0.0")
    m = api.get_modems()[0]
    assert m.connected and m.agent_ver == "0.1" and m.last_seen_at is not None


def test_sweep_offline_fails_dispatched_after_24h(db):
    api.register_modem("m1")
    ids = api.enqueue_slot_set("E", 302, 1, (9, 0), (10, 0), 1, "a", "b")
    _dispatch(db, ids)
    api.touch_modem("m1", connected=False)
    now = dt.datetime(2026, 9, 14, 12, 0)  # noqa: DTZ001 — 앱 전역이 naive UTC (app.db.utcnow)
    with db() as s, s.begin():
        s.get(Modem, "m1").last_seen_at = now - dt.timedelta(hours=23)
    assert api.sweep_offline(now) == 0
    with db() as s, s.begin():
        s.get(Modem, "m1").last_seen_at = now - dt.timedelta(hours=25)
    assert api.sweep_offline(now) == 1
    with db() as s:
        r = s.get(Outbox, ids[0])
        assert r.state == "failed" and r.last_error == "modem_offline"
        assert s.get(RoomVersion, ("E", 302, "schedule")).ver == 1  # 버전은 건드리지 않음

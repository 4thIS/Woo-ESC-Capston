import time

import pytest
from starlette.websockets import WebSocketDisconnect

from app.lora_service import api
from app.lora_service.models import Outbox, PendingDevice, TerminalStatus


@pytest.fixture
def modem(live):
    return api.register_modem("m1")


def _wait_disconnected(timeout=1.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if api.get_modems()[0].connected is False:
            return True
        time.sleep(0.02)
    return False


def _hello(ws, token, pending=0):
    ws.send_json(
        {
            "t": "hello",
            "modem_id": "m1",
            "token": token,
            "agent_ver": "0.1",
            "modem_fw": "gw-2.0.0",
            "pending_results": pending,
        }
    )


def _barrier(ws):
    ws.send_json({"t": "ping"})
    assert ws.receive_json()["t"] == "pong"


def test_hello_logs_agent_fw_pending_results(client, live, modem, caplog):
    """PR #5 M-b."""
    with caplog.at_level("INFO", logger="hub"), client.websocket_connect("/ws/modem") as ws:
        _hello(ws, modem, pending=3)
        ws.receive_json()  # config
        _barrier(ws)
    msg = next(r.getMessage() for r in caplog.records if "hello agent=" in r.getMessage())
    assert "m1" in msg and "0.1" in msg and "gw-2.0.0" in msg and "3" in msg


def test_non_dict_hello_closes_without_crashing(client, modem):
    with client.websocket_connect("/ws/modem") as ws:
        ws.send_json([1, 2])
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_bad_token_closes(client, modem):
    with client.websocket_connect("/ws/modem") as ws:
        _hello(ws, "wrong")
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_hello_sends_config_then_queued_jobs(client, live, modem):
    ids = api.enqueue_slot_set("E", 301, 1, (9, 0), (10, 0), 1, "a", "b")  # 접속 전 → queued
    with client.websocket_connect("/ws/modem") as ws:
        _hello(ws, modem)
        cfg = ws.receive_json()
        assert cfg["t"] == "config" and cfg["net_id"] == 0x4B
        assert cfg["radio"] == {
            "sf": 9,
            "bw": 125.0,
            "cr": 5,
            "tx_dbm": 14,
            "preamble_wake_ms": 3000,
        }
        assert sorted(cfg["nodes"], key=lambda n: (n["room"], n["unit"])) == [
            {"bld": "E", "room": 301, "unit": 1},
            {"bld": "E", "room": 301, "unit": 2},
            {"bld": "E", "room": 302, "unit": 1},
        ]
        assert cfg["status_hour_utc"] == 18 and "qr_base_url" not in cfg  # QR 폐기 (#16)
        jobs = [ws.receive_json(), ws.receive_json()]
        assert [j["t"] for j in jobs] == ["job", "job"]
        assert [j["job_id"] for j in jobs] == ids
        assert jobs[0]["type"] == "SLOT_SET" and jobs[0]["payload"]["subject"] == "a"
        assert jobs[0]["new_ver"] == 1 and jobs[0]["priority"] == 3
        for j in jobs:
            ws.send_json({"t": "job_accepted", "job_id": j["job_id"]})
        _barrier(ws)
        with live() as s:
            assert {s.get(Outbox, i).state for i in ids} == {"dispatched"}
            assert s.get(Outbox, ids[0]).dispatched_at is not None
    assert _wait_disconnected()  # 끊김 반영


def test_job_id_as_string_is_coerced(client, live, modem):
    ids = api.enqueue_slot_set("E", 302, 1, (9, 0), (10, 0), 1, "a", "b")
    with client.websocket_connect("/ws/modem") as ws:
        _hello(ws, modem)
        ws.receive_json()  # config
        ws.receive_json()  # job
        ws.send_json({"t": "job_accepted", "job_id": str(ids[0])})
        _barrier(ws)
        with live() as s:
            assert s.get(Outbox, ids[0]).state == "dispatched"
        ws.send_json(
            {
                "t": "job_result",
                "job_id": str(ids[0]),
                "state": "acked",
                "ack_status": 0,
                "ack_detail": 0,
                "attempts": 1,
                "txn": 1,
                "rssi": -80,
                "snr": 7.0,
                "sched_ver": 1,
                "resv_ver": 0,
                "exam_ver": 0,
                "ident_ver": 1,
                "batt_mv": 4000,
                "layout": 1,
                "fw": 20,
                "last_error": None,
                "finished_at": 1_800_000_000,
            }
        )
        _barrier(ws)
        with live() as s:
            assert s.get(Outbox, ids[0]).state == "acked"


def test_flush_does_not_resend_already_sent_job(client, live, modem):
    ids = api.enqueue_slot_set("E", 302, 1, (9, 0), (10, 0), 1, "a", "b")
    with client.websocket_connect("/ws/modem") as ws:
        _hello(ws, modem)
        ws.receive_json()  # config
        assert ws.receive_json()["job_id"] == ids[0]
        api._hub.notify("m1")  # 재알림 — 아직 job_accepted 도 안 왔다
        _barrier(ws)  # 바로 pong 이 온다 = job 재송신 없음
    assert _wait_disconnected()
    with client.websocket_connect("/ws/modem") as ws:
        _hello(ws, modem, pending=1)
        ws.receive_json()  # config
        assert ws.receive_json()["job_id"] == ids[0]  # 새 연결 = 새 집합, 다시 온다
        _barrier(ws)


def test_job_accepted_discards_sent_marker(client, live, modem):
    """PR #5 M-c — _sent 가 커넥션 수명 내내 자라지 않도록 job_accepted 에서 지운다."""
    ids = api.enqueue_slot_set("E", 302, 1, (9, 0), (10, 0), 1, "a", "b")
    with client.websocket_connect("/ws/modem") as ws:
        _hello(ws, modem)
        ws.receive_json()  # config
        assert ws.receive_json()["job_id"] == ids[0]
        assert ids[0] in client.app.state.hub._sent["m1"]
        ws.send_json({"t": "job_accepted", "job_id": ids[0]})
        _barrier(ws)
        assert ids[0] not in client.app.state.hub._sent["m1"]


def test_enqueue_while_connected_pushes_immediately(client, live, modem):
    with client.websocket_connect("/ws/modem") as ws:
        _hello(ws, modem)
        ws.receive_json()  # config
        ids = api.enqueue_slot_set("E", 302, 1, (9, 0), (10, 0), 1, "a", "b")
        job = ws.receive_json()
        assert job["t"] == "job" and job["job_id"] == ids[0]


def test_reconnect_does_not_resend_dispatched(client, live, modem):
    ids = api.enqueue_slot_set("E", 302, 1, (9, 0), (10, 0), 1, "a", "b")
    with client.websocket_connect("/ws/modem") as ws:
        _hello(ws, modem)
        ws.receive_json()
        assert ws.receive_json()["job_id"] == ids[0]
        ws.send_json({"t": "job_accepted", "job_id": ids[0]})
        _barrier(ws)
    new = api.enqueue_slot_set("E", 302, 2, (9, 0), (10, 0), 1, "a", "b")
    with client.websocket_connect("/ws/modem") as ws:
        _hello(ws, modem, pending=1)
        ws.receive_json()  # config
        assert ws.receive_json()["job_id"] == new[0]  # dispatched 였던 ids[0] 은 안 옴
        _barrier(ws)  # 그 뒤 pong 이 바로 온다 = 다른 job 없음


def test_job_result_and_uplink_reach_api(client, live, modem):
    ids = api.enqueue_slot_set("E", 302, 1, (9, 0), (10, 0), 1, "a", "b")
    with client.websocket_connect("/ws/modem") as ws:
        _hello(ws, modem)
        ws.receive_json()
        ws.receive_json()
        ws.send_json({"t": "job_accepted", "job_id": ids[0]})
        ws.send_json(
            {
                "t": "job_result",
                "job_id": ids[0],
                "state": "acked",
                "ack_status": 0,
                "ack_detail": 0,
                "attempts": 1,
                "txn": 1,
                "rssi": -80,
                "snr": 7.0,
                "sched_ver": 1,
                "resv_ver": 0,
                "exam_ver": 0,
                "ident_ver": 1,
                "batt_mv": 4000,
                "layout": 1,
                "fw": 20,
                "last_error": None,
                "finished_at": 1_800_000_000,
            }
        )
        ws.send_json(
            {
                "t": "uplink",
                "kind": "HELLO",
                "bld": 0,
                "room": 0,
                "unit": 0,
                "mac": "aabbccddeeff",
                "fw": 20,
                "batt_mv": 4000,
                "rssi": -100,
                "snr": 3.0,
            }
        )
        ws.send_json({"t": "garbage"})  # 모르는 t → 무시, 연결 유지
        _barrier(ws)
        with live() as s:
            assert s.get(Outbox, ids[0]).state == "acked"
            assert s.get(TerminalStatus, ("E", 302, 1)).sync_state == "synced"
            assert s.get(PendingDevice, "aabbccddeeff") is not None


def test_cancel_and_time_now_are_sent(client, live, modem):
    ids = api.enqueue_slot_set("E", 302, 1, (9, 0), (10, 0), 1, "a", "b")
    with client.websocket_connect("/ws/modem") as ws:
        _hello(ws, modem)
        ws.receive_json()
        ws.receive_json()
        ws.send_json({"t": "job_accepted", "job_id": ids[0]})
        _barrier(ws)
        assert api.cancel(ids[0]) is True
        assert ws.receive_json() == {"t": "cancel", "job_id": ids[0]}
        assert api.request_time_broadcast() == 1
        assert ws.receive_json() == {"t": "time_now", "request_status": False}


def test_job_accepted_after_cancel_replies_cancel(client, live, modem):
    ids = api.enqueue_slot_set("E", 302, 1, (9, 0), (10, 0), 1, "a", "b")
    with client.websocket_connect("/ws/modem") as ws:
        _hello(ws, modem)
        ws.receive_json()  # config
        ws.receive_json()  # job
        assert api.cancel(ids[0]) is True  # queued → cancelled (아직 job_accepted 안 옴)
        ws.send_json({"t": "job_accepted", "job_id": ids[0]})
        assert ws.receive_json() == {"t": "cancel", "job_id": ids[0]}


def test_second_connection_replaces_first(client, modem):
    with client.websocket_connect("/ws/modem") as a:
        _hello(a, modem)
        a.receive_json()
        with client.websocket_connect("/ws/modem") as b:
            _hello(b, modem)
            b.receive_json()
            with pytest.raises(WebSocketDisconnect):
                a.receive_json()
            _barrier(b)


def test_malformed_known_message_keeps_connection(client, live, modem):
    with client.websocket_connect("/ws/modem") as ws:
        _hello(ws, modem)
        ws.receive_json()  # config
        ws.send_json({"t": "job_result"})  # job_id 없음
        ws.send_json({"t": "uplink", "kind": "HELLO"})  # mac 없음
        ws.send_json([1, 2, 3])  # dict 아님
        _barrier(ws)  # 여전히 pong 이 온다


def test_replacement_survives_stale_old_socket(client, live, modem):
    with client.websocket_connect("/ws/modem") as a:
        _hello(a, modem)
        a.receive_json()
        with client.websocket_connect("/ws/modem") as b:
            _hello(b, modem)
            b.receive_json()
            _barrier(b)
        assert _wait_disconnected()
    # a 가 닫힌 뒤 세 번째 접속도 정상
    with client.websocket_connect("/ws/modem") as c:
        _hello(c, modem)
        assert c.receive_json()["t"] == "config"
        _barrier(c)


def test_flush_sends_in_outbox_id_order_not_priority(client, live, modem):
    """#28: 노드 FIFO(계약 ⑦ r6). id 가 작으면 priority 숫자가 커도(FILE=5) 먼저 나간다 —
    SLOT_SET v6 이 FILE v5 를 추월하면 노드가 GAP 을 내고 옛 FILE 이 최신 편집을 덮는다."""
    from lora_proto import codec as C

    api.set_record_provider(
        lambda bld, room, kind: (
            [C.SlotSet(0, 1, 9, 0, 10, 0, 1, "a", "b")] if kind == "schedule" else []
        )
    )
    file_id = api.enqueue_file_replace("E", 302, "schedule")[0]  # priority 5
    slot_id = api.enqueue_slot_set("E", 302, 1, (9, 0), (10, 0), 1, "a", "b")[0]  # priority 3
    assert file_id < slot_id
    with client.websocket_connect("/ws/modem") as ws:
        _hello(ws, modem)
        ws.receive_json()  # config
        jobs = [ws.receive_json(), ws.receive_json()]
        assert [(j["job_id"], j["priority"]) for j in jobs] == [(file_id, 5), (slot_id, 3)]
        _barrier(ws)


def test_hub_db_write_waiting_on_lock_does_not_freeze_the_loop(client, live, modem, app):
    """#43 — 다른 연결이 쓰기 잠금을 쥔 동안 허브가 수신 기록(lora_log)을 써야 하면, 그 대기는 스레드에서.
    루프 위에서 기다리면 루프 전체가 busy_timeout(5 s)만큼 멈춰 다른 요청도 같이 멈춘다(실측 16~20 s 저장)."""
    import sqlite3

    with client.websocket_connect("/ws/modem") as ws:
        _hello(ws, modem)
        ws.receive_json()  # config
        # 허브는 보낸 뒤에 기록을 스레드에서 쓴다 — config 를 받은 순간 그 기록이 아직 진행 중일 수 있어 기다린다
        holder = sqlite3.connect(app.state.engine.url.database, timeout=5)
        holder.execute("BEGIN IMMEDIATE")  # 쓰기 잠금을 쥔다 — 저장 요청이 커밋 전에 쥔 것과 같다
        holder.execute("UPDATE modems SET agent_ver = agent_ver")
        try:
            ws.send_json({"t": "ping"})  # 허브는 rx 기록을 쓰려다 잠금에 막힌다
            time.sleep(0.2)
            t0 = time.monotonic()
            assert client.get("/api/health").status_code == 200
            # 루프가 멈추면 busy_timeout(5 s)만큼 걸린다 — 병렬 실행 부하에서도 흔들리지 않게 여유를 둔다(#84 리뷰)
            assert time.monotonic() - t0 < 2.5
        finally:
            holder.rollback()  # 잠금을 풀면 허브의 기록이 이어서 들어간다
            holder.close()
        assert ws.receive_json()["t"] == "pong"  # 메시지는 유실되지 않고 순서대로 처리된다


def _hold(monkeypatch, obj, name, when=lambda *a, **k: True):
    """obj.name 을 붙잡는다 — 조건이 맞는 첫 호출이 들어오면 entered, release 될 때까지 기다린 뒤 원래대로.
    허브의 DB 작업(스레드)이 잠금을 기다리는 동안을 흉내낸다"""
    import threading

    entered, release = threading.Event(), threading.Event()
    real = getattr(obj, name)
    armed = [True]

    def held(*a, **k):
        if armed[0] and when(*a, **k):
            armed[0] = False
            entered.set()
            assert release.wait(5)
        return real(*a, **k)

    monkeypatch.setattr(obj, name, held)
    return entered, release


def test_job_waits_for_config_while_hello_handling_is_blocked(client, live, modem, monkeypatch):
    """#84 리뷰 🔴 — 연결을 등록한 뒤 config 를 보내기 전까지 DB 대기(touch_modem 등)가 있다. 그 사이 notify 가
    job 을 먼저 보내면 모뎀Pi 는 'config 대신 job' 으로 세션을 끊는다(client.py:135). 첫 메시지는 config"""
    ids = api.enqueue_slot_set("E", 302, 1, (9, 0), (10, 0), 1, "a", "b")
    entered, release = _hold(monkeypatch, api, "touch_modem", lambda *a, **k: k.get("connected"))
    with client.websocket_connect("/ws/modem") as ws:
        _hello(ws, modem)
        assert entered.wait(5)  # 허브가 config 전 DB 대기에 걸렸다
        api._hub.notify("m1")  # 저장 요청이 그 사이 알린다
        time.sleep(0.2)
        release.set()
        assert ws.receive_json()["t"] == "config"
        assert ws.receive_json()["job_id"] == ids[0]
        _barrier(ws)  # job 은 한 번만


def test_old_flush_does_not_send_on_replacing_connection(client, live, modem, monkeypatch):
    """#84 리뷰 — flush 가 await(조회) 뒤에 연결·sent 를 다시 잡으면, 재접속한 새 연결로 config 보다 먼저 job 을
    보낼 수 있었다. flush 는 시작한 연결에 묶인다"""
    ids = api.enqueue_slot_set("E", 302, 1, (9, 0), (10, 0), 1, "a", "b")
    with client.websocket_connect("/ws/modem") as a:
        _hello(a, modem)
        assert a.receive_json()["t"] == "config"
        assert a.receive_json()["job_id"] == ids[0]
        q_in, q_go = _hold(monkeypatch, api._hub, "_queued")
        api._hub.notify("m1")  # a 의 flush — 조회에서 멈춘다
        assert q_in.wait(5)
        t_in, t_go = _hold(monkeypatch, api, "touch_modem", lambda *a, **k: k.get("connected"))
        with client.websocket_connect("/ws/modem") as b:
            _hello(b, modem, pending=1)
            assert t_in.wait(5)  # b 는 config 전 DB 대기
            q_go.set()  # 옛 flush 가 풀린다 — b 로 보내면 안 된다
            time.sleep(0.2)
            t_go.set()
            assert b.receive_json()["t"] == "config"
            assert b.receive_json()["job_id"] == ids[0]  # b 자신의 flush 가 한 번
            _barrier(b)

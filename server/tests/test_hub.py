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
        assert cfg["status_hour_utc"] == 18 and "qr_base_url" in cfg
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

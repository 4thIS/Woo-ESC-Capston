from app.lora_service import api


def _room(client):
    sch = client.post("/api/schools", json={"name": "명지", "net_id": 75}).json()
    b = client.post(
        "/api/buildings",
        json={"school_id": sch["id"], "name": "공학관", "bld": "E", "modem_id": "m1"},
    ).json()
    return client.post("/api/rooms", json={"building_id": b["id"], "room": 302, "units": 1}).json()


def test_modem_register_list_rotate(client):
    res = client.post("/api/lora/modems", json={"modem_id": "m1"})
    assert res.status_code == 200 and api.verify_token("m1", res.json()["token"])
    assert client.post("/api/lora/modems", json={"modem_id": "m1"}).status_code == 400
    lst = client.get("/api/lora/modems").json()
    assert (
        lst[0]["modem_id"] == "m1" and lst[0]["connected"] is False and "token_hash" not in lst[0]
    )
    tok2 = client.post("/api/lora/modems/m1/token").json()["token"]
    assert api.verify_token("m1", tok2)
    assert client.post("/api/lora/modems/zz/token").status_code == 404


def test_outbox_cancel_status_pending_provision_time(client):
    client.post("/api/lora/modems", json={"modem_id": "m1"})
    r = _room(client)
    ids = client.put(
        f"/api/rooms/{r['id']}/slots",
        json={
            "day": 1,
            "s_h": 9,
            "s_m": 0,
            "e_h": 10,
            "e_m": 0,
            "type": 1,
            "subject": "a",
            "professor": "b",
        },
    ).json()["outbox_ids"]
    ob = client.get("/api/lora/outbox?state=queued&bld=E&room=302").json()
    assert [x["id"] for x in ob] == ids and ob[0]["payload"]["subject"] == "a"
    assert client.post(f"/api/lora/outbox/{ids[0]}/cancel").json() == {"ok": True}
    assert client.get("/api/lora/outbox?state=cancelled").json()[0]["id"] == ids[0]
    assert client.post("/api/lora/outbox/99999/cancel").status_code == 404
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
    assert client.get("/api/lora/pending").json()[0]["mac"] == "aabbccddeeff"
    prov = client.post(
        "/api/lora/pending/aabbccddeeff/provision", json={"bld": "E", "room": 302, "unit": 1}
    )
    assert prov.status_code == 200 and prov.json()["outbox_ids"]
    assert client.get("/api/lora/outbox?state=queued").json()[-1]["type"] == "SET_ROOM"
    assert client.get("/api/lora/status").json() == []
    assert client.post("/api/lora/time").json() == {"modems": 0}


def test_validation_error_is_400_but_plain_valueerror_is_500(app):
    """#8: 검증 실패(api.ValidationError)만 400. 내부 버그성 ValueError 는 500 으로 드러난다."""
    from fastapi.testclient import TestClient

    @app.get("/_boom")
    def boom():
        raise ValueError("internal bug")

    @app.get("/_bad")
    def bad():
        raise api.ValidationError("bad input")

    with TestClient(app, raise_server_exceptions=False) as c:
        assert c.get("/_boom").status_code == 500
        r = c.get("/_bad")
        assert r.status_code == 400 and r.json()["detail"] == "bad input"


def test_frame_error_and_unit_check_are_validation_errors(client, db):
    import pytest

    with pytest.raises(api.ValidationError):
        api.provision("aabbccddeeff", "E", 301, 3)  # unit 범위
    with pytest.raises(api.ValidationError):
        api.enqueue_slot_set("E", 301, 1, (9, 0), (10, 0), 1, "x" * 100, "p")  # FrameError 래핑
    assert client.post("/api/lora/modems", json={"modem_id": "m1"}).status_code == 200
    assert client.post("/api/lora/modems", json={"modem_id": "m1"}).status_code == 400  # 중복


def test_cmd_args_hex_rejected_by_schema(client):
    client.post("/api/lora/modems", json={"modem_id": "m1"})
    r = _room(client)
    assert (
        client.post(f"/api/rooms/{r['id']}/cmd", json={"cmd": 4, "args_hex": "zz"}).status_code
        == 422
    )
    assert (
        client.post(f"/api/rooms/{r['id']}/cmd", json={"cmd": 4, "args_hex": "0aFF"}).status_code
        == 200
    )

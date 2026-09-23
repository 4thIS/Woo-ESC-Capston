import pytest

from app.domain.models import Building, Room, School
from app.lora_service.models import Modem


def _bld(app, school_id, bld):
    with app.state.Session() as s, s.begin():
        b = Building(school_id=school_id, name=f"{bld}동", bld=bld)
        s.add(b)
        s.flush()
        r = Room(building_id=b.id, room=101, units=1)
        s.add(r)
        s.flush()
        return b.id, r.id


def test_domain_endpoints_require_admin(client_raw, school):
    for path in ("/api/schools", "/api/buildings", "/api/rooms", "/api/rooms/1/slots"):
        assert client_raw.get(path).status_code == 401, path
    assert (
        client_raw.post(
            "/api/import/slots", content=b"x", headers={"content-type": "text/csv"}
        ).status_code
        == 401
    )


def test_school_endpoints_scoped_and_no_create_delete(client, app, school):
    assert [x["id"] for x in client.get("/api/schools").json()] == [1]
    assert client.post("/api/schools", json={"name": "x", "net_id": 9}).status_code == 405
    assert client.delete("/api/schools/1").status_code == 405
    assert client.patch("/api/schools/2", json={"name": "y"}).status_code == 404
    r = client.patch(
        "/api/schools/1", json={"name": "명지대", "email_domain": "gmail.com", "net_id": 9}
    )
    assert r.status_code == 200 and r.json()["name"] == "명지대"
    with app.state.Session() as s:  # name 만 바뀐다 — email_domain·net_id 는 CLI 전용 (S4a §3.3)
        sch = s.get(School, 1)
        assert sch.email_domain == "mju.ac.kr" and sch.net_id == 75


def test_buildings_rooms_scoped(client, app, school, other_admin_hdr):
    b1, r1 = _bld(app, 1, "E")
    b2, r2 = _bld(app, 2, "F")
    assert [x["id"] for x in client.get("/api/buildings").json()] == [b1]
    assert [x["id"] for x in client.get("/api/rooms").json()] == [r1]
    assert client.get(f"/api/rooms/{r2}/slots").status_code == 404
    assert (
        client.patch(
            f"/api/buildings/{b2}", json={"school_id": 2, "name": "x", "bld": "F"}
        ).status_code
        == 404
    )
    assert client.delete(f"/api/rooms/{r2}").status_code == 404
    assert (
        client.post("/api/buildings", json={"school_id": 2, "name": "x", "bld": "G"}).status_code
        == 404
    )
    assert client.post("/api/rooms", json={"building_id": b2, "room": 5}).status_code == 404
    slot = {
        "day": 1,
        "s_h": 9,
        "s_m": 0,
        "e_h": 10,
        "e_m": 0,
        "type": 1,
        "subject": "a",
        "professor": "",
    }
    assert client.put(f"/api/rooms/{r2}/slots", json=slot).status_code == 404
    assert client.post(f"/api/rooms/{r2}/sync", json={}).status_code == 404
    # 타교 관리자는 자기 것만
    assert [x["id"] for x in client.get("/api/rooms", headers=other_admin_hdr).json()] == [r2]
    r = client.post("/api/rooms", json={"building_id": b1, "room": 102, "reservable": True})
    assert r.status_code == 200 and r.json()["reservable"] is True
    # PATCH 는 보낸 필드만 — reservable 이 초기화되지 않는다
    r = client.patch(f"/api/rooms/{r.json()['id']}", json={"units": 2})
    assert r.status_code == 200 and r.json()["reservable"] is True and r.json()["units"] == 2


@pytest.mark.parametrize(
    "kind,body",
    [
        ("school", {"name": None}),
        ("building", {"bld": None}),
        ("building", {"name": None}),
        ("room", {"room": None}),
        ("room", {"units": None}),
        ("room", {"reservable": None}),
    ],
)
def test_patch_explicit_null_is_422(client, app, school, kind, body):
    """리뷰 finding 1: 보낸 필드의 명시적 null 은 409(제약 위반)가 아니라 422 — 생략은 부분 업데이트로 허용."""
    b, r = _bld(app, 1, "E")
    url = {
        "school": "/api/schools/1",
        "building": f"/api/buildings/{b}",
        "room": f"/api/rooms/{r}",
    }[kind]
    assert client.patch(url, json=body).status_code == 422


def test_patch_building_modem_id_null_unassigns(client, app, school):
    """BuildingPatch.modem_id 만은 null 이 모뎀 배정 해제라는 의미를 가지므로 422 가 되면 안 된다."""
    with app.state.Session() as s, s.begin():
        s.add(Modem(modem_id="mine", token_hash="x", school_id=1))
    b, _r = _bld(app, 1, "E")
    assert client.patch(f"/api/buildings/{b}", json={"modem_id": "mine"}).status_code == 200
    r = client.patch(f"/api/buildings/{b}", json={"modem_id": None})
    assert r.status_code == 200 and r.json()["modem_id"] is None


def test_building_modem_and_bld_guards(client, app, school):
    with app.state.Session() as s, s.begin():
        s.add_all(
            [
                Modem(modem_id="mine", token_hash="x", school_id=1),
                Modem(modem_id="theirs", token_hash="x", school_id=2),
            ]
        )
    _bld(app, 2, "F")
    assert (
        client.post(
            "/api/buildings", json={"school_id": 1, "name": "x", "bld": "G", "modem_id": "theirs"}
        ).status_code
        == 404
    )
    assert (
        client.post("/api/buildings", json={"school_id": 1, "name": "x", "bld": "F"}).status_code
        == 409
    )  # 타교가 쓰는 bld
    r = client.post(
        "/api/buildings", json={"school_id": 1, "name": "x", "bld": "G", "modem_id": "mine"}
    )
    assert r.status_code == 200
    bid = r.json()["id"]
    assert client.patch(f"/api/buildings/{bid}", json={"modem_id": "theirs"}).status_code == 404
    assert client.patch(f"/api/buildings/{bid}", json={"bld": "F"}).status_code == 409
    r = client.patch(f"/api/buildings/{bid}", json={"name": "새이름"})
    assert r.status_code == 200 and r.json()["modem_id"] == "mine" and r.json()["bld"] == "G"


def test_csv_import_rejects_other_school_rows(client, app, school):
    _bld(app, 2, "F")
    text = "school,building,room,day,start,end,type,subject,professor\n타교,F,101,월,09:00,10:00,1,a,\n"
    r = client.post(
        "/api/import/slots", content=text.encode(), headers={"content-type": "text/csv"}
    )
    assert r.status_code == 400 and r.json()["errors"][0]["error"] == "school: 다른 학교"
    # 타교 이름을 내 학교 이름과 같게 바꿔도 조회가 School.id 로 한정돼 있어 못 쓴다 (리뷰 🔴4d)
    with app.state.Session() as s, s.begin():
        s.get(School, 2).name = "명지"
    text = "school,building,room,day,start,end,type,subject,professor\n명지,F,101,월,09:00,10:00,1,a,\n"
    r = client.post(
        "/api/import/slots", content=text.encode(), headers={"content-type": "text/csv"}
    )
    assert r.status_code == 400 and r.json()["errors"][0]["error"] == "building: 'F' 없음 (명지)"

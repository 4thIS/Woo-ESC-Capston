from app.domain import router as R
from app.domain.models import Building, Room

RESV = {
    "date": "2026-09-24",
    "s_h": 9,
    "s_m": 0,
    "e_h": 10,
    "e_m": 0,
    "type": 6,
    "subject": "r",
    "professor": "",
}
EXAM = {"date_start": "2026-10-19", "date_end": "2026-10-23"}


def _building(app, school_id, bld, rooms=((101, 1), (102, 1))):
    with app.state.Session() as s, s.begin():
        b = Building(school_id=school_id, name=f"{bld}동", bld=bld)
        s.add(b)
        s.flush()
        ids = {}
        for room, units in rooms:
            r = Room(building_id=b.id, room=room, units=units)
            s.add(r)
            s.flush()
            ids[room] = r.id
        bid = b.id
    return bid, ids


def test_server_assigns_smallest_free_id(client, app, school):
    _, ids = _building(app, 1, "E")
    rid = ids[101]
    r = client.post(f"/api/rooms/{rid}/reservations", json=RESV)
    assert r.status_code == 200 and r.json()["id"] == 1 and "outbox_ids" in r.json()
    assert client.post(f"/api/rooms/{rid}/reservations", json=RESV).json()["id"] == 2
    assert client.post(f"/api/rooms/{ids[102]}/reservations", json=RESV).json()["id"] == 3  # 전역
    assert client.delete(f"/api/rooms/{rid}/reservations/1").status_code == 200
    assert (
        client.post(f"/api/rooms/{rid}/reservations", json=RESV).json()["id"] == 1
    )  # 빈 최소값 재사용
    # id 지정 upsert 는 기존대로
    r = client.post(f"/api/rooms/{rid}/reservations", json={**RESV, "id": 2, "subject": "edited"})
    assert r.json()["id"] == 2
    assert [
        x["subject"] for x in client.get(f"/api/rooms/{rid}/reservations").json() if x["id"] == 2
    ] == ["edited"]


def test_explicit_id_must_be_same_room(client, app, school, other_admin_hdr):
    """id 지정 수정은 같은 방의 기존 행만 — 다른 방·다른 학교 행을 빼앗지 못한다 (S4a §3.3 🔴4a)."""
    _, ids = _building(app, 1, "E")
    _, other = _building(app, 2, "F", rooms=((201, 1),))
    assert client.post(f"/api/rooms/{ids[101]}/reservations", json=RESV).json()["id"] == 1
    r = client.post(f"/api/rooms/{ids[102]}/reservations", json={**RESV, "id": 1})
    assert r.status_code == 409 and "다른 방" in r.json()["detail"]
    r = client.post(
        f"/api/rooms/{other[201]}/reservations", json={**RESV, "id": 1}, headers=other_admin_hdr
    )
    assert r.status_code == 409  # 타교 관리자도 남의 행을 못 가져간다
    assert client.post(f"/api/rooms/{ids[101]}/exams", json=EXAM).json()["id"] == 1
    assert client.post(f"/api/rooms/{ids[102]}/exams", json={**EXAM, "id": 1}).status_code == 409


def test_exam_ids_same_rule(client, app, school):
    _, ids = _building(app, 1, "E")
    assert client.post(f"/api/rooms/{ids[101]}/exams", json=EXAM).json()["id"] == 1
    assert client.post(f"/api/rooms/{ids[102]}/exams", json=EXAM).json()["id"] == 2
    assert client.post(f"/api/rooms/{ids[101]}/exams", json={**EXAM, "id": 9}).json()["id"] == 9


def test_id_exhausted_409(client, app, school, monkeypatch):
    monkeypatch.setattr(R, "ID_MAX", 2)
    _, ids = _building(app, 1, "E")
    rid = ids[101]
    assert client.post(f"/api/rooms/{rid}/reservations", json=RESV).json()["id"] == 1
    assert client.post(f"/api/rooms/{rid}/reservations", json=RESV).json()["id"] == 2
    r = client.post(f"/api/rooms/{rid}/reservations", json=RESV)
    assert r.status_code == 409 and "소진" in r.json()["detail"]
    assert (
        client.post(
            f"/api/rooms/{rid}/exams", json={"date_start": "2026-10-19", "date_end": "2026-10-23"}
        ).json()["id"]
        == 1
    )


def test_explicit_id_still_validated(client, app, school):
    _, ids = _building(app, 1, "E")
    assert (
        client.post(f"/api/rooms/{ids[101]}/reservations", json={**RESV, "id": 0}).status_code
        == 422
    )
    assert (
        client.post(f"/api/rooms/{ids[101]}/reservations", json={**RESV, "id": 65536}).status_code
        == 422
    )


def test_concurrent_auto_ids_serialized_by_lock(client, app, school, monkeypatch):
    """채번~커밋을 _ID_LOCK 이 직렬화 — 없으면 동시 요청이 같은 최소값을 골라 PK 충돌(500) (#48 🟡1)."""
    import time
    from concurrent.futures import ThreadPoolExecutor

    _, ids = _building(app, 1, "E")
    rid = ids[101]
    orig = R._free_id

    def slow_free_id(s, model):
        i = orig(s, model)
        time.sleep(0.05)  # 채번과 커밋 사이를 벌려 경합을 확정적으로 만든다
        return i

    monkeypatch.setattr(R, "_free_id", slow_free_id)
    with ThreadPoolExecutor(12) as ex:
        res = list(
            ex.map(lambda _: client.post(f"/api/rooms/{rid}/reservations", json=RESV), range(12))
        )
    assert [r.status_code for r in res] == [200] * 12
    assert sorted(r.json()["id"] for r in res) == list(range(1, 13))


def test_delete_exam_waits_for_concurrent_update(client, app, school, monkeypatch):
    """delete_exam 도 _ID_LOCK 안 — 같은 id 수정이 행을 읽은 뒤 삭제가 끼어들면 UPDATE 0행(StaleDataError) 500 (#48 🟡2)."""
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor

    _, ids = _building(app, 1, "E")
    rid = ids[101]
    eid = client.post(f"/api/rooms/{rid}/exams", json=EXAM).json()["id"]
    loaded = threading.Event()
    orig = R._existing_same_room

    def slow_existing(s, model, obj_id, room_id):
        obj = orig(s, model, obj_id, room_id)
        loaded.set()
        time.sleep(0.2)  # 수정이 행을 읽고 쓰기 전 — 삭제가 여기 끼어들 수 있으면 경합
        return obj

    monkeypatch.setattr(R, "_existing_same_room", slow_existing)
    body = {**EXAM, "id": eid, "date_end": "2026-10-24"}
    with ThreadPoolExecutor(1) as ex:
        put = ex.submit(client.post, f"/api/rooms/{rid}/exams", json=body)
        assert loaded.wait(5)
        dele = client.delete(f"/api/rooms/{rid}/exams/{eid}")
        assert put.result().status_code == 200
    assert dele.status_code == 200
    assert client.get(f"/api/rooms/{rid}/exams").json() == []  # 수정 뒤 삭제 — 순서대로 직렬화

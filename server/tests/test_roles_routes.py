"""#160 관리자 권한 3단계 — 모든 /api 라우트의 권한 · 건물 범위 (docs/specs/2026-11-17-roles-3tier-design.md §5).

건물 관리자 ba@ 는 E 동만 맡는다. 같은 학교의 W 동은 남의 건물이다.
- 범위 라우트(MANAGER): W 리소스는 404, 목록은 W 행이 없다. E 는 쓸 수 있다
- 최고 관리자 라우트(SUPER): 건물 관리자 403
- 학생: 관리자 라우트 전부 403
새 라우트를 ROUTES 에 분류하지 않고 더하면 test_every_api_route_is_classified 가 실패한다."""

from __future__ import annotations

import datetime as dt
import json

import pytest
from fastapi.testclient import TestClient

from app.auth import password
from app.auth.models import User, UserBuilding
from app.db import utcnow
from app.domain import clock
from app.domain.models import Building, ExamPeriod, Reservation, Room, Slot
from app.lora_service.models import Modem, Outbox, PendingDevice, TerminalStatus
from tests.conftest import _hdr

PUBLIC, STUDENT, ANY, MANAGER, SUPER = "public", "student", "any", "manager", "super"

# 앱의 /api 라우트 전부. (메서드, 경로) → 분류
ROUTES: dict[tuple[str, str], str] = {
    # 공개 · 로그인한 누구나
    ("GET", "/api/health"): PUBLIC,
    ("POST", "/api/auth/signup"): PUBLIC,
    ("POST", "/api/auth/verify/open"): PUBLIC,
    ("POST", "/api/auth/verify"): PUBLIC,
    ("POST", "/api/auth/login"): PUBLIC,
    ("POST", "/api/auth/forgot"): PUBLIC,
    ("POST", "/api/auth/reset"): PUBLIC,
    ("GET", "/api/auth/me"): ANY,
    # 학생
    ("GET", "/api/student/rooms"): STUDENT,
    ("GET", "/api/student/rooms/free"): STUDENT,
    ("GET", "/api/student/rooms/{id}/week"): STUDENT,
    ("POST", "/api/student/rooms/{id}/reservations"): STUDENT,
    ("GET", "/api/student/me/reservations"): STUDENT,
    ("POST", "/api/student/me/reservations/{id}/cancel"): STUDENT,
    ("POST", "/api/student/me/reservations/{id}/checkin"): STUDENT,
    ("POST", "/api/student/me/reservations/{id}/checkout"): STUDENT,
    # 건물 범위 — 건물 관리자도
    ("GET", "/api/schools"): MANAGER,
    ("GET", "/api/buildings"): MANAGER,
    ("GET", "/api/buildings/{id}/slots"): MANAGER,
    ("GET", "/api/buildings/{id}/reservations"): MANAGER,
    ("GET", "/api/buildings/{id}/exams"): MANAGER,
    ("GET", "/api/buildings/{id}/outbox"): MANAGER,
    ("GET", "/api/rooms"): MANAGER,
    ("POST", "/api/rooms"): MANAGER,
    ("PATCH", "/api/rooms/{id}"): MANAGER,
    ("DELETE", "/api/rooms/{id}"): MANAGER,
    ("GET", "/api/rooms/{id}/slots"): MANAGER,
    ("PUT", "/api/rooms/{id}/slots"): MANAGER,
    ("DELETE", "/api/rooms/{id}/slots/{day}/{s_h}/{s_m}"): MANAGER,
    ("DELETE", "/api/rooms/{id}/slots"): MANAGER,
    ("GET", "/api/rooms/{id}/reservations"): MANAGER,
    ("POST", "/api/rooms/{id}/reservations"): MANAGER,
    ("DELETE", "/api/rooms/{id}/reservations/{resv_id}"): MANAGER,
    ("GET", "/api/rooms/{id}/exams"): MANAGER,
    ("POST", "/api/rooms/{id}/exams"): MANAGER,
    ("DELETE", "/api/rooms/{id}/exams/{exam_id}"): MANAGER,
    ("POST", "/api/rooms/{id}/sync"): MANAGER,
    ("POST", "/api/rooms/{id}/cmd"): MANAGER,
    ("POST", "/api/import/slots"): MANAGER,
    ("GET", "/api/admin/nodes"): MANAGER,
    ("GET", "/api/admin/outbox/failed"): MANAGER,
    ("GET", "/api/admin/summary"): MANAGER,
    ("GET", "/api/admin/reservations"): MANAGER,
    ("POST", "/api/admin/reservations/{id}/approve"): MANAGER,
    ("POST", "/api/admin/reservations/{id}/reject"): MANAGER,
    ("POST", "/api/admin/reservations/{id}/cancel"): MANAGER,
    ("GET", "/api/admin/analytics/allocation"): MANAGER,
    ("GET", "/api/admin/analytics/free-slots"): MANAGER,
    ("GET", "/api/admin/analytics/reservations"): MANAGER,
    ("GET", "/api/admin/analytics/latency"): MANAGER,
    ("GET", "/api/admin/analytics/latency/samples"): MANAGER,
    ("GET", "/api/lora/modems"): MANAGER,
    ("GET", "/api/lora/outbox"): MANAGER,
    ("POST", "/api/lora/outbox/{id}/cancel"): MANAGER,
    ("GET", "/api/lora/status"): MANAGER,
    ("GET", "/api/lora/pending"): MANAGER,
    ("POST", "/api/lora/pending/{mac}/provision"): MANAGER,
    # 최고 관리자만
    ("PATCH", "/api/schools/{id}"): SUPER,
    ("POST", "/api/buildings"): SUPER,
    ("PATCH", "/api/buildings/{id}"): SUPER,
    ("DELETE", "/api/buildings/{id}"): SUPER,
    ("POST", "/api/lora/modems"): SUPER,
    ("POST", "/api/lora/modems/{modem_id}/token"): SUPER,
    ("POST", "/api/lora/time"): SUPER,
    ("GET", "/api/admin/users"): SUPER,
    ("POST", "/api/admin/users/{email}/approve"): SUPER,
    ("POST", "/api/admin/users/{email}/reject"): SUPER,
    ("POST", "/api/admin/users/{email}/disable"): SUPER,
    ("POST", "/api/admin/users/{email}/enable"): SUPER,
    ("PUT", "/api/admin/users/{email}/role"): SUPER,
    ("POST", "/api/admin/jobs/daily"): SUPER,
    ("GET", "/api/admin/jobs"): SUPER,
}

FUTURE = clock.local_today() + dt.timedelta(days=3)


@pytest.fixture
def world(app, school, students):
    """학교 1: E 동(모뎀 m1, 301호) · W 동(모뎀 mw, 201호). 건물 관리자 ba@ 는 E 만."""
    ids = {}
    with app.state.Session() as s, s.begin():
        s.add_all(
            [
                Modem(modem_id="m1", token_hash="x", school_id=1),
                Modem(modem_id="mw", token_hash="x", school_id=1),
            ]
        )
        s.flush()
        e = Building(school_id=1, name="공학관", bld="E", modem_id="m1")
        w = Building(school_id=1, name="인문관", bld="W", modem_id="mw")
        s.add_all([e, w])
        s.flush()
        re_, rw = (
            Room(building_id=e.id, room=301, units=1, reservable=True),
            Room(building_id=w.id, room=201, units=1, reservable=True),
        )
        s.add_all([re_, rw])
        s.flush()
        for r in (re_, rw):
            s.add(
                Slot(
                    room_id=r.id,
                    day=1,
                    s_h=9,
                    s_m=0,
                    e_h=10,
                    e_m=0,
                    type=1,
                    subject="수업",
                    professor="",
                    source=2,
                )
            )
        s.add_all(
            [
                Reservation(
                    id=11,
                    room_id=re_.id,
                    date=FUTURE,
                    s_h=13,
                    s_m=0,
                    e_h=14,
                    e_m=0,
                    type=6,
                    subject="E신청",
                    professor="",
                    status="requested",
                    requested_by="s1@mju.ac.kr",
                    requested_at=utcnow(),
                ),
                Reservation(
                    id=12,
                    room_id=rw.id,
                    date=FUTURE,
                    s_h=13,
                    s_m=0,
                    e_h=14,
                    e_m=0,
                    type=6,
                    subject="W신청",
                    professor="",
                    status="requested",
                    requested_by="s2@mju.ac.kr",
                    requested_at=utcnow(),
                ),
                ExamPeriod(id=21, room_id=rw.id, date_start=FUTURE, date_end=FUTURE),
                TerminalStatus(bld="E", room=301, unit=1, modem_id="m1", last_seen_at=utcnow()),
                TerminalStatus(bld="W", room=201, unit=1, modem_id="mw", last_seen_at=utcnow()),
                PendingDevice(
                    mac="AAAAAAAAAAA1", modem_id="m1", first_seen_at=utcnow(), last_seen_at=utcnow()
                ),
                PendingDevice(
                    mac="BBBBBBBBBBB2", modem_id="mw", first_seen_at=utcnow(), last_seen_at=utcnow()
                ),
            ]
        )
        now = utcnow()
        for bld, room, mid, state in [
            ("E", 301, "m1", "failed"),
            ("W", 201, "mw", "failed"),
            ("W", 201, "mw", "queued"),
        ]:
            o = Outbox(
                modem_id=mid,
                bld=bld,
                room=room,
                unit=1,
                type="SLOT_SET",
                payload=json.dumps({}),
                state=state,
                created_at=now - dt.timedelta(minutes=5),
                finished_at=now if state == "failed" else None,
                last_error="timeout" if state == "failed" else None,
            )
            s.add(o)
            s.flush()
            ids[f"outbox_{bld}_{state}"] = o.id
        s.add(
            User(
                email="ba@mju.ac.kr",
                school_id=1,
                role="building_admin",
                status="active",
                name="건물관리",
                pw_hash=password.hash("adminpass1"),
            )
        )
        s.flush()
        s.add(UserBuilding(email="ba@mju.ac.kr", building_id=e.id))
        ids |= {"E": e.id, "W": w.id, "rE": re_.id, "rW": rw.id}
    return ids


@pytest.fixture
def ba(app, world, live):
    with TestClient(app, headers=_hdr(app, "ba@mju.ac.kr")) as c:
        yield c


def _api_routes(app) -> set[tuple[str, str]]:
    """앱이 실제로 여는 /api 라우트 — OpenAPI 스키마에서 (include_router 가 라우터를 묶음째 두는 버전에서도 빠짐없이)."""
    return {
        (m.upper(), path)
        for path, ops in app.openapi()["paths"].items()
        if path.startswith("/api")
        for m in ops
    }


def test_every_api_route_is_classified(app):
    routes = _api_routes(app)
    assert routes - ROUTES.keys() == set(), (
        "분류되지 않은 라우트 — ROUTES 에 MANAGER/SUPER 등으로 넣고 시험을 더한다"
    )
    assert ROUTES.keys() - routes == set(), "ROUTES 에 있는데 앱에 없는 라우트"


def _fill(path: str, w: dict) -> str:
    return (
        path.replace("{id}", str(w["rE"]))
        .replace("{modem_id}", "m1")
        .replace("{email}", "s1@mju.ac.kr")
        .replace("{mac}", "AAAAAAAAAAA1")
        .replace("{resv_id}", "11")
        .replace("{exam_id}", "21")
        .replace("{day}", "1")
        .replace("{s_h}", "9")
        .replace("{s_m}", "0")
    )


def test_super_routes_forbid_building_admin(ba, world):
    for (method, path), kind in ROUTES.items():
        if kind == SUPER:
            r = ba.request(method, _fill(path, world), json={})
            assert r.status_code == 403, (method, path, r.status_code)


def test_admin_routes_forbid_student(app, world, student_hdr):
    with TestClient(app, headers=student_hdr) as c:
        for (method, path), kind in ROUTES.items():
            if kind in (MANAGER, SUPER):
                r = c.request(method, _fill(path, world), json={})
                assert r.status_code == 403, (method, path, r.status_code)


# ---- 건물 범위: W(남의 건물)는 404, 목록엔 없다, E 는 된다 ----

SLOT = {
    "day": 2,
    "s_h": 9,
    "s_m": 0,
    "e_h": 10,
    "e_m": 0,
    "type": 1,
    "subject": "x",
    "professor": "",
    "source": 2,
}
RESV = {
    "date": FUTURE.isoformat(),
    "s_h": 15,
    "s_m": 0,
    "e_h": 16,
    "e_m": 0,
    "type": 5,
    "subject": "x",
    "professor": "",
}
EXAM = {"date_start": FUTURE.isoformat(), "date_end": FUTURE.isoformat()}


def test_room_scoped_routes_other_building_404(ba, world):
    rw = world["rW"]
    cases = [
        ("GET", f"/api/buildings/{world['W']}/slots", None),
        ("GET", f"/api/buildings/{world['W']}/reservations", None),
        ("GET", f"/api/buildings/{world['W']}/exams", None),
        ("GET", f"/api/buildings/{world['W']}/outbox", None),
        ("POST", "/api/rooms", {"building_id": world["W"], "room": 202}),
        ("PATCH", f"/api/rooms/{rw}", {"reservable": False}),
        ("DELETE", f"/api/rooms/{rw}", None),
        ("GET", f"/api/rooms/{rw}/slots", None),
        ("PUT", f"/api/rooms/{rw}/slots", SLOT),
        ("DELETE", f"/api/rooms/{rw}/slots/1/9/0", None),
        ("DELETE", f"/api/rooms/{rw}/slots?day=1", None),
        ("GET", f"/api/rooms/{rw}/reservations", None),
        ("POST", f"/api/rooms/{rw}/reservations", RESV),
        ("DELETE", f"/api/rooms/{rw}/reservations/12", None),
        ("GET", f"/api/rooms/{rw}/exams", None),
        ("POST", f"/api/rooms/{rw}/exams", EXAM),
        ("DELETE", f"/api/rooms/{rw}/exams/21", None),
        ("POST", f"/api/rooms/{rw}/sync", {"kinds": ["schedule"]}),
        ("POST", f"/api/rooms/{rw}/cmd", {"cmd": 1, "args_hex": ""}),
        ("GET", f"/api/admin/nodes?building_id={world['W']}", None),
        ("POST", "/api/admin/reservations/12/approve", None),
        ("POST", "/api/admin/reservations/12/reject", {"reason": "x"}),
        ("POST", "/api/admin/reservations/12/cancel", None),
        ("POST", f"/api/lora/outbox/{world['outbox_W_queued']}/cancel", None),
        (
            "POST",
            "/api/lora/pending/BBBBBBBBBBB2/provision",
            {"bld": "E", "room": 301, "unit": 1},
        ),  # 남의 모뎀이 본 노드
        (
            "POST",
            "/api/lora/pending/AAAAAAAAAAA1/provision",
            {"bld": "W", "room": 201, "unit": 1},
        ),  # 남의 강의실로
    ]
    for method, path, body in cases:
        r = ba.request(method, path, json=body)
        assert r.status_code == 404, (method, path, r.status_code, r.text)
    with ba.app.state.Session() as s:  # 아무것도 바뀌지 않았다
        assert s.get(Room, rw).reservable is True
        assert s.get(Reservation, 12).status == "requested"
        assert s.get(ExamPeriod, 21) is not None
        assert s.get(Outbox, world["outbox_W_queued"]).state == "queued"


def test_list_routes_show_only_own_building(ba, world):
    assert [b["bld"] for b in ba.get("/api/buildings").json()] == ["E"]
    assert [r["id"] for r in ba.get("/api/rooms").json()] == [world["rE"]]
    assert [x["id"] for x in ba.get("/api/schools").json()] == [1]  # 학교는 읽기만
    assert {n["bld"] for n in ba.get("/api/admin/nodes").json()} == {"E"}
    assert {f["bld"] for f in ba.get("/api/admin/outbox/failed").json()} == {"E"}
    sm = ba.get("/api/admin/summary").json()
    assert sm["totals"] == {"buildings": 1, "rooms": 1, "nodes": 1, "modems": 1}
    assert sm["warnings"]["pending_approval"]["count"] == 0  # 가입 승인은 최고 관리자의 일
    assert [x["id"] for x in sm["warnings"]["pending_reservations"]["items"]] == [11]
    assert [x["id"] for x in ba.get("/api/admin/reservations").json()] == [11]
    assert ba.get(f"/api/admin/reservations?building_id={world['W']}").json() == []
    alloc = ba.get("/api/admin/analytics/allocation").json()
    assert {a["key"] for a in alloc} == {world["rE"]}  # group=room — key 가 room_id
    assert {x["room_id"] for x in ba.get("/api/admin/analytics/free-slots").json()} == {world["rE"]}
    assert ba.get(f"/api/admin/analytics/free-slots?building_id={world['W']}").json() == []
    assert ba.get("/api/admin/analytics/reservations").status_code == 200
    assert ba.get("/api/admin/analytics/latency").status_code == 200
    assert ba.get("/api/admin/analytics/latency/samples").json() == []
    assert [m["modem_id"] for m in ba.get("/api/lora/modems").json()] == ["m1"]
    assert {o["bld"] for o in ba.get("/api/lora/outbox").json()} == {"E"}
    assert {t["bld"] for t in ba.get("/api/lora/status").json()} == {"E"}
    assert [p["mac"] for p in ba.get("/api/lora/pending").json()] == ["AAAAAAAAAAA1"]


def test_own_building_works(ba, world):
    re_ = world["rE"]
    assert ba.get(f"/api/buildings/{world['E']}/slots").status_code == 200
    assert ba.put(f"/api/rooms/{re_}/slots", json=SLOT).status_code == 200
    assert ba.post(f"/api/rooms/{re_}/exams", json=EXAM).status_code == 200
    assert ba.patch(f"/api/rooms/{re_}", json={"units": 1}).status_code == 200
    r = ba.post("/api/admin/reservations/11/approve")
    assert r.status_code == 200 and r.json()["status"] == "approved"
    with ba.app.state.Session() as s:
        assert s.get(Reservation, 11).decided_by == "ba@mju.ac.kr"
    assert ba.post("/api/rooms", json={"building_id": world["E"], "room": 302}).status_code == 200


def test_csv_import_hides_other_building(ba, world):
    head = "school,building,room,day,start,end,type,subject,professor\n"
    bad = ba.post(
        "/api/import/slots?dry_run=true",
        content=(head + "명지,W,201,화,09:00,10:00,수업,x,\n").encode(),
        headers={"content-type": "text/csv"},
    )
    assert bad.status_code == 400 and "building: 'W' 없음" in bad.text
    ok = ba.post(
        "/api/import/slots?dry_run=true",
        content=(head + "명지,E,301,화,09:00,10:00,수업,x,\n").encode(),
        headers={"content-type": "text/csv"},
    )
    assert ok.status_code == 200, ok.text


def test_building_admin_with_no_buildings_sees_nothing(app, world, live):
    """맡은 건물이 모두 지워져도 권한이 넓어지지 않는다 — 빈 범위는 빈 목록."""
    with app.state.Session() as s, s.begin():
        s.query(UserBuilding).delete()
    with TestClient(app, headers=_hdr(app, "ba@mju.ac.kr")) as c:
        assert c.get("/api/buildings").json() == []
        assert c.get("/api/rooms").json() == []
        assert c.get("/api/lora/modems").json() == []
        assert c.get(f"/api/rooms/{world['rE']}/slots").status_code == 404


def test_super_admin_still_sees_whole_school(client, world):
    assert {b["bld"] for b in client.get("/api/buildings").json()} == {"E", "W"}
    assert {m["modem_id"] for m in client.get("/api/lora/modems").json()} == {"m1", "mw"}

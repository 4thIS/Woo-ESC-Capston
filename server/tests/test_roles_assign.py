"""#160 역할 지정 — PUT /api/admin/users/{email}/role (최고 관리자 전용, 스펙 §3.4)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.auth.models import RoleChange, User, UserBuilding
from app.domain.models import Building
from tests.conftest import _hdr


@pytest.fixture
def blds(app, school, students):
    with app.state.Session() as s, s.begin():
        e = Building(school_id=1, name="공학관", bld="E")
        w = Building(school_id=1, name="인문관", bld="W")
        x = Building(school_id=2, name="타교관", bld="X")
        s.add_all([e, w, x])
        s.flush()
        return {"E": e.id, "W": w.id, "X": x.id}


def _u(app, email):
    with app.state.Session() as s:
        u = s.get(User, email)
        ids = sorted(
            s.scalars(
                UserBuilding.__table__.select()
                .with_only_columns(UserBuilding.building_id)
                .where(UserBuilding.email == email)
            )
        )
        logs = s.query(RoleChange).filter_by(email=email).order_by(RoleChange.id).all()
        return (
            u,
            ids,
            [(r.from_role, r.to_role, json.loads(r.building_ids), r.changed_by) for r in logs],
        )


def test_assign_change_and_revert(client, app, blds):
    old = _hdr(app, "s1@mju.ac.kr")
    r = client.put(
        "/api/admin/users/s1@mju.ac.kr/role",
        json={"role": "building_admin", "building_ids": [blds["E"]]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "building_admin" and r.json()["building_ids"] == [blds["E"]]
    u, ids, logs = _u(app, "s1@mju.ac.kr")
    assert u.role == "building_admin" and u.token_version == 1 and ids == [blds["E"]]
    assert logs == [("student", "building_admin", [blds["E"]], "admin@mju.ac.kr")]
    with TestClient(app, headers=old) as c:  # 바꾸는 순간 기존 로그인이 끊긴다
        assert c.get("/api/auth/me").status_code == 401

    # 같은 값 — 아무것도 바꾸지 않는다(멱등)
    assert (
        client.put(
            "/api/admin/users/s1@mju.ac.kr/role",
            json={"role": "building_admin", "building_ids": [blds["E"]]},
        ).status_code
        == 200
    )
    u, _, logs = _u(app, "s1@mju.ac.kr")
    assert u.token_version == 1 and len(logs) == 1

    # 건물만 바꿔도 끊는다
    both = sorted([blds["E"], blds["W"]])
    r = client.put(
        "/api/admin/users/s1@mju.ac.kr/role",
        json={"role": "building_admin", "building_ids": [blds["W"], blds["E"], blds["W"]]},
    )
    assert r.json()["building_ids"] == both
    u, ids, logs = _u(app, "s1@mju.ac.kr")
    assert u.token_version == 2 and ids == both and logs[-1][2] == both

    # 해제 — 일반 계정, 건물 비움
    r = client.put(
        "/api/admin/users/s1@mju.ac.kr/role", json={"role": "student", "building_ids": [blds["E"]]}
    )
    assert r.status_code == 200 and r.json()["role"] == "student" and r.json()["building_ids"] == []
    u, ids, logs = _u(app, "s1@mju.ac.kr")
    assert u.token_version == 3 and ids == [] and logs[-1][:3] == ("building_admin", "student", [])


def test_list_users_shows_building_ids(client, app, blds):
    client.put(
        "/api/admin/users/s1@mju.ac.kr/role",
        json={"role": "building_admin", "building_ids": [blds["W"]]},
    )
    rows = {u["email"]: u for u in client.get("/api/admin/users").json()}
    assert rows["s1@mju.ac.kr"]["building_ids"] == [blds["W"]]
    assert rows["s2@mju.ac.kr"]["building_ids"] == []


def test_cannot_make_super_admin_on_web(client, blds):
    r = client.put("/api/admin/users/s1@mju.ac.kr/role", json={"role": "admin", "building_ids": []})
    assert r.status_code == 422


def test_rejects_bad_targets(client, app, blds):
    put = lambda email, body: client.put(f"/api/admin/users/{email}/role", json=body)
    ba = {"role": "building_admin", "building_ids": [blds["E"]]}
    assert put("admin@mju.ac.kr", ba).status_code == 400  # 최고 관리자는 CLI 로
    assert put("s3@other.ac.kr", ba).status_code == 404  # 다른 학교 — 존재를 숨긴다
    assert put("nobody@mju.ac.kr", ba).status_code == 404
    assert (
        put("s1@mju.ac.kr", {"role": "building_admin", "building_ids": [blds["X"]]}).status_code
        == 404
    )
    assert put("s1@mju.ac.kr", {"role": "building_admin", "building_ids": []}).status_code == 422
    with app.state.Session() as s, s.begin():
        s.get(User, "s2@mju.ac.kr").status = "disabled"
    assert put("s2@mju.ac.kr", ba).status_code == 409
    u, ids, logs = _u(app, "s1@mju.ac.kr")
    assert u.role == "student" and ids == [] and logs == []


def test_building_admin_cannot_assign(app, blds):
    with app.state.Session() as s, s.begin():
        s.get(User, "s1@mju.ac.kr").role = "building_admin"
        s.add(UserBuilding(email="s1@mju.ac.kr", building_id=blds["E"]))
    with TestClient(app, headers=_hdr(app, "s1@mju.ac.kr")) as c:
        r = c.put(
            "/api/admin/users/s2@mju.ac.kr/role",
            json={"role": "building_admin", "building_ids": [blds["E"]]},
        )
        assert r.status_code == 403


def test_building_admin_login_returns_role(client_raw, app, blds):
    with app.state.Session() as s, s.begin():
        s.get(User, "s1@mju.ac.kr").role = "building_admin"
    # students 픽스처 비밀번호
    r = client_raw.post("/api/auth/login", json={"email": "s1@mju.ac.kr", "password": "password1"})
    assert r.status_code == 200 and r.json()["role"] == "building_admin"

import os
import subprocess
import sys

import pytest

from app.auth import mailer, password, tokens
from app.auth.models import User
from app.settings import Settings


@pytest.fixture
def seed(app, school):
    """conftest school(학교 둘·관리자 둘) 위에 학생 3명."""
    with app.state.Session() as s, s.begin():
        s.add_all(
            [
                User(
                    email="p1@mju.ac.kr",
                    school_id=1,
                    role="student",
                    status="pending_approval",
                    name="p1",
                    student_no="101",
                    pw_hash=password.hash("password1"),
                ),
                User(
                    email="a1@mju.ac.kr",
                    school_id=1,
                    role="student",
                    status="active",
                    name="a1",
                    student_no="102",
                    pw_hash=password.hash("password1"),
                ),
                User(
                    email="o@other.ac.kr",
                    school_id=2,
                    role="student",
                    status="pending_approval",
                    name="o",
                    student_no="109",
                    pw_hash=password.hash("password1"),
                ),
            ]
        )


def _hdr(app, email):
    with app.state.Session() as s:
        return {"Authorization": f"Bearer {tokens.jwt_encode(Settings(), s.get(User, email))}"}


@pytest.fixture
def hdr(admin_hdr, seed):
    return admin_hdr


@pytest.fixture
def mails(monkeypatch, app):
    sent = []

    def cap(st, to, subj, body, kind):
        with app.state.Session() as s:  # 커밋 뒤 발송인지
            sent.append((to, subj, body, s.get(User, to).status))

    monkeypatch.setattr(mailer, "send", cap)
    return sent


def test_list_is_school_scoped_and_filterable(client, hdr):
    r = client.get("/api/admin/users", headers=hdr)
    assert r.status_code == 200
    assert {u["email"] for u in r.json()} == {"admin@mju.ac.kr", "p1@mju.ac.kr", "a1@mju.ac.kr"}
    assert "pw_hash" not in r.text
    r = client.get("/api/admin/users?status=pending_approval", headers=hdr)
    assert [u["email"] for u in r.json()] == ["p1@mju.ac.kr"]


def test_approve_reject_disable_enable_transitions(client, app, hdr, mails):
    r = client.post("/api/admin/users/p1@mju.ac.kr/approve", headers=hdr)
    assert r.status_code == 200 and r.json()["status"] == "active" and r.json()["approved_at"]
    assert (
        mails[-1][0] == "p1@mju.ac.kr" and "승인" in mails[-1][1] and mails[-1][3] == "active"
    )  # 커밋 뒤
    assert client.post("/api/admin/users/p1@mju.ac.kr/approve", headers=hdr).status_code == 409
    with app.state.Session() as s:
        assert s.get(User, "p1@mju.ac.kr").approved_by == "admin@mju.ac.kr"
    stu = _hdr(app, "a1@mju.ac.kr")
    assert (
        client.post("/api/admin/users/a1@mju.ac.kr/disable", headers=hdr).json()["status"]
        == "disabled"
    )
    assert (
        client.post("/api/admin/users/a1@mju.ac.kr/enable", headers=hdr).json()["status"]
        == "active"
    )
    assert (
        client.get("/api/auth/me", headers=stu).status_code == 401
    )  # disable·enable 이 tv 를 올렸다
    assert client.post("/api/admin/users/a1@mju.ac.kr/enable", headers=hdr).status_code == 409
    with app.state.Session() as s, s.begin():
        s.get(User, "a1@mju.ac.kr").status = "pending_approval"
    r = client.post(
        "/api/admin/users/a1@mju.ac.kr/reject", json={"reason": "학번 불일치"}, headers=hdr
    )
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert "학번 불일치" in mails[-1][2] and mails[-1][3] == "rejected"
    assert client.post("/api/admin/users/admin@mju.ac.kr/disable", headers=hdr).status_code == 400


def test_other_school_user_is_404_and_student_token_is_403(client, app, hdr):
    assert client.post("/api/admin/users/o@other.ac.kr/approve", headers=hdr).status_code == 404
    stu = _hdr(app, "a1@mju.ac.kr")
    assert client.get("/api/admin/users", headers=stu).status_code == 403


def _cli(db, *args, stdin=None):
    return subprocess.run(
        [sys.executable, "-m", "app.cli", *args],
        capture_output=True,
        text=True,
        input=stdin,
        env={**os.environ, "SERVER_DB": str(db)},
        check=False,
    )


def test_cli_create_update_school_and_admin_then_login(tmp_path):
    db = tmp_path / "cli.db"
    r = _cli(db, "create-school", "--name", "명지", "--net-id", "77", "--email-domain", "mjc.ac.kr")
    assert r.returncode == 0, r.stderr
    r = _cli(db, "update-school", "--id", "1", "--email-domain", " MJC2.ac.kr ")  # 정규화
    assert r.returncode == 0, r.stderr
    r = _cli(
        db,
        "create-admin",
        "--school-id",
        "1",
        "--email",
        "Admin@MJC.ac.kr",
        "--name",
        "관리",
        stdin="short\n",
    )
    assert r.returncode != 0 and "8자" in r.stderr
    r = _cli(
        db,
        "create-admin",
        "--school-id",
        "1",
        "--email",
        "Admin@MJC.ac.kr",
        "--name",
        "관리",
        stdin="adminpass1\n",
    )
    assert r.returncode == 0, r.stderr
    r = _cli(
        db,
        "create-admin",
        "--school-id",
        "1",
        "--email",
        "admin@mjc.ac.kr",
        "--name",
        "관리",
        stdin="adminpass1\n",
    )
    assert r.returncode != 0 and "이미" in r.stderr
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app(str(db))) as c:
        r = c.post("/api/auth/login", json={"email": "admin@mjc.ac.kr", "password": "adminpass1"})
        assert r.status_code == 200 and r.json()["role"] == "admin"
        old = r.json()["token"]
    r = _cli(db, "set-user", "--email", "admin@mjc.ac.kr", "--password", stdin="newpass12\n")
    assert r.returncode == 0, r.stderr
    r = _cli(db, "set-user", "--email", "admin@mjc.ac.kr", "--status", "disabled")
    assert r.returncode == 0, r.stderr
    with TestClient(create_app(str(db))) as c:
        assert (
            c.get("/api/auth/me", headers={"Authorization": f"Bearer {old}"}).status_code == 401
        )  # tv 증가
        assert (
            c.post(
                "/api/auth/login", json={"email": "admin@mjc.ac.kr", "password": "newpass12"}
            ).status_code
            == 401
        )
    assert _cli(db, "assign-modem", "--modem-id", "nope", "--school-id", "1").returncode != 0


def test_cli_set_user_password_kills_mail_tokens(tmp_path):
    """CLI 로 비밀번호를 바꾸면 이전 reset 링크도 죽는다 (PR #42 🟡)."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    db = tmp_path / "cli.db"
    assert _cli(db, "create-school", "--name", "명지", "--net-id", "77").returncode == 0
    r = _cli(
        db,
        "create-admin",
        *("--school-id", "1", "--email", "admin@mjc.ac.kr", "--name", "관리"),
        stdin="adminpass1\n",
    )
    assert r.returncode == 0, r.stderr
    app = create_app(str(db))
    with app.state.Session() as s, s.begin():
        tok = tokens.issue(s, "admin@mjc.ac.kr", "reset")
    r = _cli(db, "set-user", "--email", "admin@mjc.ac.kr", "--password", stdin="newpass12\n")
    assert r.returncode == 0, r.stderr
    with TestClient(app) as c:
        r = c.post("/api/auth/reset", json={"token": tok, "password": "hijacked1"})
        assert r.status_code == 400


def test_reject_reason_only_on_rejected_rows(client, app, hdr, mails):
    r = client.post(
        "/api/admin/users/p1@mju.ac.kr/reject", json={"reason": "학번 불일치"}, headers=hdr
    )
    assert r.json()["reject_reason"] == "학번 불일치"
    rows = {u["email"]: u for u in client.get("/api/admin/users", headers=hdr).json()}
    assert rows["p1@mju.ac.kr"]["reject_reason"] == "학번 불일치"
    assert rows["a1@mju.ac.kr"]["reject_reason"] is None
    assert "o@other.ac.kr" not in rows  # 타 학교 행은 사유째 안 보인다
    me = client.get("/api/auth/me", headers=_hdr(app, "a1@mju.ac.kr")).json()
    assert me["reject_reason"] is None  # 학생 본인 응답 — active 만 /me 를 통과한다

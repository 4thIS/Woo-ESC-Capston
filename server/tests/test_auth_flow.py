import datetime as dt
import re

import pytest

from app.auth import mailer, password, ratelimit, tokens
from app.auth.models import EmailToken, User
from app.domain.models import School


@pytest.fixture
def schools(app):
    with app.state.Session() as s, s.begin():
        s.add(School(id=1, name="명지", net_id=75, email_domain="mju.ac.kr"))
        s.add(School(id=2, name="타교", net_id=76, email_domain="other.ac.kr"))


@pytest.fixture
def mails(monkeypatch, app):
    """발송 시점에 DB 가 이미 커밋돼 있는지도 같이 본다 (S4a §3.4 메일·커밋 순서)."""
    sent: list[tuple[str, str, str, bool]] = []

    def cap(st, to, subj, body, kind):
        with app.state.Session() as s:  # 새 세션 — 커밋된 것만 보인다
            m = re.search(r"token=([A-Za-z0-9_-]+)", body)
            committed = m is None or s.get(EmailToken, tokens._h(m.group(1))) is not None
        sent.append((to, subj, body, committed))

    monkeypatch.setattr(mailer, "send", cap)
    return sent


def _token(mails, kind):
    return re.search(rf"/{kind}#token=([A-Za-z0-9_-]+)", mails[-1][2]).group(1)


def _user(app, email):
    with app.state.Session() as s:
        return s.get(User, email)


PROFILE = {"name": "학생", "student_no": "20260001", "password": "password1"}


def test_two_step_signup_then_login(client_raw, app, schools, mails):
    c = client_raw
    r = c.post("/api/auth/signup", json={"email": "Stu@MJU.ac.kr"})
    assert r.status_code == 202 and r.json() == {"status": "sent"}
    assert mails[-1][0] == "stu@mju.ac.kr" and mails[-1][3] is True  # 소문자 정규화, 커밋 뒤 발송
    assert _user(app, "stu@mju.ac.kr") is None  # 신청 단계엔 users 행 없음
    r = c.post("/api/auth/verify", json={"token": _token(mails, "verify"), **PROFILE})
    assert r.status_code == 200 and r.json() == {"status": "pending_approval"}
    u = _user(app, "stu@mju.ac.kr")
    assert (
        u.school_id == 1
        and u.status == "pending_approval"
        and u.name == "학생"
        and password.verify("password1", u.pw_hash)
    )
    r = c.post("/api/auth/login", json={"email": "stu@mju.ac.kr", "password": "password1"})
    assert r.status_code == 403 and "승인" in r.json()["detail"]
    with app.state.Session() as s, s.begin():
        s.get(User, "stu@mju.ac.kr").status = "active"  # 승인은 T6
    r = c.post("/api/auth/login", json={"email": "stu@mju.ac.kr", "password": "password1"})
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "student" and body["school_id"] == 1 and body["name"] == "학생"
    me = c.get("/api/auth/me", headers={"Authorization": f"Bearer {body['token']}"})
    assert (
        me.status_code == 200 and me.json()["email"] == "stu@mju.ac.kr" and "pw_hash" not in me.text
    )
    assert c.get("/api/auth/me").status_code == 401
    assert c.get("/api/auth/me", headers={"Authorization": "Bearer nope"}).status_code == 401


@pytest.mark.parametrize(
    "email",
    [
        "attacker@gmail.com,x@mju.ac.kr",
        "a@b@mju.ac.kr",
        "a b@mju.ac.kr",
        "<a@mju.ac.kr>",
        "a@mju.ac.kr ,",
        "@mju.ac.kr",
        "a@",
    ],
)
def test_signup_rejects_malformed_email(client_raw, schools, mails, email):
    assert client_raw.post("/api/auth/signup", json={"email": email}).status_code == 422
    assert mails == []


def test_signup_domain_existing_and_interval(client_raw, app, schools, mails, monkeypatch):
    c = client_raw
    r = c.post("/api/auth/signup", json={"email": "x@gmail.com"})
    assert r.status_code == 400 and "학교 웹메일" in r.json()["detail"]
    t0 = dt.datetime(2026, 9, 23, 9, 0, 0)  # noqa: DTZ001 — 앱 전역이 naive UTC (app.db.utcnow)
    monkeypatch.setattr(tokens, "utcnow", lambda: t0)
    assert c.post("/api/auth/signup", json={"email": "a@mju.ac.kr"}).status_code == 202
    assert c.post("/api/auth/signup", json={"email": "a@mju.ac.kr"}).status_code == 202
    assert len(mails) == 1  # 60 s 이내 재신청 → 보내지 않음
    monkeypatch.setattr(tokens, "utcnow", lambda: t0 + dt.timedelta(seconds=61))
    assert c.post("/api/auth/signup", json={"email": "a@mju.ac.kr"}).status_code == 202
    assert len(mails) == 2
    with app.state.Session() as s, s.begin():  # 이미 가입된 email → 202, 메일 없음
        s.add(
            User(
                email="b@mju.ac.kr",
                school_id=1,
                role="student",
                status="active",
                name="b",
                student_no="9",
                pw_hash=password.hash("password1"),
            )
        )
    assert c.post("/api/auth/signup", json={"email": "b@mju.ac.kr"}).status_code == 202
    assert len(mails) == 2


def test_preemption_is_impossible(client_raw, app, schools, mails):
    """공격자가 피해자 웹메일로 먼저 신청해도 비밀번호는 링크를 연 사람이 정한다 (리뷰 🔴2)."""
    c = client_raw
    c.post("/api/auth/signup", json={"email": "victim@mju.ac.kr"})  # 공격자
    assert _user(app, "victim@mju.ac.kr") is None
    ratelimit.reset()
    tok = _token(mails, "verify")  # 메일은 피해자 메일함으로만 간다
    assert (
        c.post(
            "/api/auth/verify",
            json={"token": tok, "name": "피해자", "student_no": "1", "password": "victimpass"},
        ).status_code
        == 200
    )
    assert password.verify("victimpass", _user(app, "victim@mju.ac.kr").pw_hash)


def test_verify_open_checks_without_consuming(client_raw, schools, mails, monkeypatch):
    """링크 페이지가 먼저 부른다 — 이메일을 보여주고, 입력 시간을 30분으로 늘린다 (r2 🟡 5분에 입력까지 포함되던 것)."""
    c = client_raw
    t0 = dt.datetime(2026, 9, 23, 9, 0, 0)  # noqa: DTZ001 — 앱 전역이 naive UTC (app.db.utcnow)
    monkeypatch.setattr(tokens, "utcnow", lambda: t0)
    c.post("/api/auth/signup", json={"email": "a@mju.ac.kr"})
    tok = _token(mails, "verify")
    monkeypatch.setattr(tokens, "utcnow", lambda: t0 + dt.timedelta(minutes=4))
    r = c.post("/api/auth/verify/open", json={"token": tok})
    assert r.status_code == 200 and r.json() == {"email": "a@mju.ac.kr"}
    monkeypatch.setattr(tokens, "utcnow", lambda: t0 + dt.timedelta(minutes=25))  # 입력에 20분
    assert c.post("/api/auth/verify", json={"token": tok, **PROFILE}).status_code == 200
    assert c.post("/api/auth/verify/open", json={"token": tok}).status_code == 400  # 소비됨
    assert c.post("/api/auth/verify/open", json={"token": "nope"}).status_code == 400


def test_rejected_can_sign_up_again_and_does_not_hold_student_no(client_raw, app, schools, mails):
    """거절 행은 학번을 잡지 않고(부분 인덱스), 본인은 다시 신청할 수 있다 (r2 🟡 — 오타로 거절돼도 막히지 않게)."""
    c = client_raw
    with app.state.Session() as s, s.begin():
        s.add(
            User(
                email="r@mju.ac.kr",
                school_id=1,
                role="student",
                status="rejected",
                name="내부자",
                student_no="20260001",
                pw_hash=password.hash("password1"),
                reject_reason="남의 학번",
            )
        )
    c.post("/api/auth/signup", json={"email": "victim@mju.ac.kr"})
    r = c.post("/api/auth/verify", json={"token": _token(mails, "verify"), **PROFILE})  # 같은 학번
    assert r.status_code == 200
    c.post("/api/auth/signup", json={"email": "r@mju.ac.kr"})
    assert mails[-1][0] == "r@mju.ac.kr"  # 거절된 사람도 메일을 받는다
    r = c.post(
        "/api/auth/verify",
        json={"token": _token(mails, "verify"), **PROFILE, "student_no": "20260002"},
    )
    assert r.status_code == 200
    u = _user(app, "r@mju.ac.kr")
    assert u.status == "pending_approval" and u.student_no == "20260002" and u.reject_reason is None


def test_verify_student_no_probe_is_rate_limited(client_raw, app, schools, mails):
    """409 는 롤백돼 토큰이 살아 있다(오타를 고쳐 다시 제출 가능) — 대신 학번 조회 남용은 분당 5회로 (r2 ⚪)."""
    c = client_raw
    with app.state.Session() as s, s.begin():
        s.add(
            User(
                email="b@mju.ac.kr",
                school_id=1,
                role="student",
                status="active",
                name="b",
                student_no="20260001",
                pw_hash=password.hash("password1"),
            )
        )
    c.post("/api/auth/signup", json={"email": "a@mju.ac.kr"})
    tok = _token(mails, "verify")
    codes = [
        c.post("/api/auth/verify", json={"token": tok, **PROFILE}).status_code for _ in range(6)
    ]
    assert codes == [409] * 5 + [429]
    ratelimit.reset()
    assert (
        c.post(
            "/api/auth/verify", json={"token": tok, **PROFILE, "student_no": "20260009"}
        ).status_code
        == 200
    )


def test_resend_spam_cannot_kill_open_link_or_flood(client_raw, app, schools, mails, monkeypatch):
    """주소 하나로 61 초마다 signup — 피해자가 연 링크는 살아 있고, 그 주소로는 시간당 3통만 나간다 (자체 점검 🔴)."""
    c = client_raw
    t0 = dt.datetime(2026, 9, 23, 9, 0, 0)  # noqa: DTZ001 — 앱 전역이 naive UTC (app.db.utcnow)
    monkeypatch.setattr(tokens, "utcnow", lambda: t0)
    c.post("/api/auth/signup", json={"email": "v@mju.ac.kr"})
    tok = _token(mails, "verify")
    c.post("/api/auth/verify/open", json={"token": tok})
    for k in range(1, 6):  # 공격자가 재신청을 반복
        monkeypatch.setattr(tokens, "utcnow", lambda k=k: t0 + dt.timedelta(seconds=61 * k))
        ratelimit._hits.pop(
            "signup:v@mju.ac.kr", None
        )  # email 분당 한도는 따로 검증됨 — 여기선 주소당 시간 상한만
        c.post("/api/auth/signup", json={"email": "v@mju.ac.kr"})
    assert len(mails) == 3  # 주소당 시간 3통
    assert (
        c.post("/api/auth/verify", json={"token": tok, **PROFILE}).status_code == 200
    )  # 처음 연 링크가 산다


def test_student_no_is_normalized(client_raw, app, schools, mails):
    c = client_raw
    c.post("/api/auth/signup", json={"email": "a@mju.ac.kr"})
    assert (
        c.post(
            "/api/auth/verify",
            json={"token": _token(mails, "verify"), **PROFILE, "student_no": "２０２６０００１"},
        ).status_code
        == 422
    )
    r = c.post(
        "/api/auth/verify",
        json={
            "token": _token(mails, "verify"),
            **PROFILE,
            "student_no": " 20260001 ",
            "name": "  ",
        },
    )
    assert r.status_code == 422  # 이름 공백뿐
    assert (
        c.post(
            "/api/auth/verify",
            json={"token": _token(mails, "verify"), **PROFILE, "student_no": " 20260001 "},
        ).status_code
        == 200
    )
    assert _user(app, "a@mju.ac.kr").student_no == "20260001"


def test_signup_per_domain_cap_is_visible(client_raw, schools, mails, monkeypatch):
    """가짜 주소(junkN@학교) 대량 신청 — 학교 도메인당 상한, 넘으면 429 로 보인다(조용히 버리지 않음) (r2 🟡)."""
    from app.auth import router as auth_router

    monkeypatch.setattr(auth_router, "SIGNUP_PER_DOMAIN_HOUR", 2)
    c = client_raw
    assert [
        c.post("/api/auth/signup", json={"email": f"junk{i}@mju.ac.kr"}).status_code
        for i in range(3)
    ] == [202, 202, 429]
    assert (
        c.post("/api/auth/signup", json={"email": "x@other.ac.kr"}).status_code == 202
    )  # 다른 학교는 별도
    assert len(mails) == 3


def test_verify_validation_expiry_and_duplicates(client_raw, app, schools, mails, monkeypatch):
    c = client_raw
    t0 = dt.datetime(2026, 9, 23, 9, 0, 0)  # noqa: DTZ001 — 앱 전역이 naive UTC (app.db.utcnow)
    monkeypatch.setattr(tokens, "utcnow", lambda: t0)
    c.post("/api/auth/signup", json={"email": "a@mju.ac.kr"})
    tok = _token(mails, "verify")
    assert (
        c.post("/api/auth/verify", json={"token": tok, **PROFILE, "password": "short"}).status_code
        == 422
    )
    monkeypatch.setattr(tokens, "utcnow", lambda: t0 + dt.timedelta(minutes=6))
    assert c.post("/api/auth/verify", json={"token": tok, **PROFILE}).status_code == 400  # 만료
    c.post("/api/auth/signup", json={"email": "a@mju.ac.kr"})
    tok2 = _token(mails, "verify")
    assert c.post("/api/auth/verify", json={"token": tok2, **PROFILE}).status_code == 200
    assert c.post("/api/auth/verify", json={"token": tok2, **PROFILE}).status_code == 400  # 재사용
    # 같은 학교 학번 중복 → 409
    c.post("/api/auth/signup", json={"email": "z@mju.ac.kr"})
    r = c.post("/api/auth/verify", json={"token": _token(mails, "verify"), **PROFILE})
    assert r.status_code == 409 and "학번" in r.json()["detail"]


def test_login_status_matrix_and_token_death(client_raw, app, schools):
    c = client_raw
    with app.state.Session() as s, s.begin():
        s.add(
            User(
                email="u@mju.ac.kr",
                school_id=1,
                role="student",
                status="active",
                name="u",
                student_no="1",
                pw_hash=password.hash("password1"),
            )
        )

    def login(pw="password1"):
        ratelimit.reset()  # 이 테스트는 상태 전이를 본다 — 429 는 test_rate_limit_login 에서
        return c.post("/api/auth/login", json={"email": "u@mju.ac.kr", "password": pw})

    assert login("wrong").status_code == 401
    assert (
        c.post(
            "/api/auth/login", json={"email": "ghost@mju.ac.kr", "password": "password1"}
        ).status_code
        == 401
    )
    tok = login().json()["token"]
    hdr = {"Authorization": f"Bearer {tok}"}
    for st, code in (("pending_approval", 403), ("disabled", 401), ("rejected", 401)):
        with app.state.Session() as s, s.begin():
            s.get(User, "u@mju.ac.kr").status = st
        assert login().status_code == code, st
    assert c.get("/api/auth/me", headers=hdr).status_code == 401  # disabled·rejected 즉시 401
    with app.state.Session() as s, s.begin():
        u = s.get(User, "u@mju.ac.kr")
        u.status, u.token_version = "active", u.token_version + 1
    assert c.get("/api/auth/me", headers=hdr).status_code == 401  # tv 불일치 → 옛 토큰 무효


def test_forgot_reset_kills_old_tokens(client_raw, app, schools, mails):
    c = client_raw
    with app.state.Session() as s, s.begin():
        s.add(
            User(
                email="u@mju.ac.kr",
                school_id=1,
                role="student",
                status="active",
                name="u",
                student_no="1",
                pw_hash=password.hash("password1"),
            )
        )
    old = c.post("/api/auth/login", json={"email": "u@mju.ac.kr", "password": "password1"}).json()[
        "token"
    ]
    assert c.post("/api/auth/forgot", json={"email": "ghost@mju.ac.kr"}).status_code == 202
    assert mails == []
    assert c.post("/api/auth/forgot", json={"email": "u@mju.ac.kr"}).status_code == 202
    assert mails[-1][3] is True
    tok = _token(mails, "reset")
    assert (
        c.post("/api/auth/reset", json={"token": tok, "password": "newpassword"}).status_code == 200
    )
    assert (
        c.post("/api/auth/reset", json={"token": tok, "password": "again1234"}).status_code == 400
    )
    assert c.get("/api/auth/me", headers={"Authorization": f"Bearer {old}"}).status_code == 401
    assert (
        c.post(
            "/api/auth/login", json={"email": "u@mju.ac.kr", "password": "password1"}
        ).status_code
        == 401
    )
    assert (
        c.post(
            "/api/auth/login", json={"email": "u@mju.ac.kr", "password": "newpassword"}
        ).status_code
        == 200
    )


def test_rate_limit_login(client_raw, schools):
    body = {"email": "u@mju.ac.kr", "password": "x"}
    for _ in range(5):
        assert client_raw.post("/api/auth/login", json=body).status_code == 401
    assert client_raw.post("/api/auth/login", json=body).status_code == 429

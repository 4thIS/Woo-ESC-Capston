import datetime as dt

import jwt
import pytest

from app.auth import password, tokens
from app.auth.models import User
from app.domain.models import School
from app.settings import Settings


def test_password_hash_roundtrip_and_format(monkeypatch):
    # conftest 가 속도용으로 낮춘 N 을 운영 값으로 되돌려 형식 확인
    monkeypatch.setattr(password, "N", 2**14)
    h = password.hash("correct horse")
    parts = h.split("$")
    assert parts[:4] == ["scrypt", "16384", "8", "1"] and len(parts) == 6
    assert password.verify("correct horse", h) and not password.verify("wrong", h)
    assert password.hash("correct horse") != h  # salt 다름


def test_password_verify_rejects_garbage_and_dummy_runs():
    assert not password.verify("x", "not-a-hash")
    assert not password.verify("x", "scrypt$1$1$1$zz$zz")
    password.dummy_verify("anything")  # 예외 없이 끝난다


@pytest.fixture
def s(app):
    with app.state.Session() as s, s.begin():
        s.add(School(id=1, name="명지", net_id=75, email_domain="mju.ac.kr"))
        s.flush()  # relationship() 이 없어 INSERT 순서가 보장되지 않는다 — 부모 먼저 (r2 🔴3)
        s.add(
            User(
                email="a@mju.ac.kr",
                school_id=1,
                role="student",
                status="active",
                name="가",
                student_no="1",
                pw_hash=password.hash("pw"),
            )
        )
        yield s


def test_issue_without_user_row(s):
    """verify 토큰은 users 행이 없어도 발급된다 (S4a §2.2 — FK 아님)."""
    plain = tokens.issue(s, "new@mju.ac.kr", "verify")
    assert tokens.consume(s, plain, "verify") == "new@mju.ac.kr"


def test_issue_and_consume_once(s):
    plain = tokens.issue(s, "a@mju.ac.kr", "verify")
    assert len(plain) >= 40
    assert tokens.consume(s, plain, "verify") == "a@mju.ac.kr"
    assert tokens.consume(s, plain, "verify") is None  # 1회용
    assert tokens.consume(s, "nope", "verify") is None
    assert tokens.consume(s, plain, "reset") is None  # purpose 불일치


def test_peek_reads_without_consuming_and_consume_is_single_use(s, monkeypatch):
    plain = tokens.issue(s, "a@mju.ac.kr", "reset")
    assert tokens.peek(s, plain, "reset") == tokens.peek(s, plain, "reset") == "a@mju.ac.kr"
    assert tokens.peek(s, plain, "verify") is None
    assert tokens.consume(s, plain, "reset") == "a@mju.ac.kr"
    assert tokens.consume(s, plain, "reset") is None and tokens.peek(s, plain, "reset") is None
    late = tokens.issue(s, "a@mju.ac.kr", "reset")
    t = tokens.utcnow() + dt.timedelta(minutes=6)
    monkeypatch.setattr(tokens, "utcnow", lambda: t)
    assert tokens.peek(s, late, "reset") is None and tokens.consume(s, late, "reset") is None


def test_reissue_does_not_kill_open_link(s):
    """재발급이 이전 토큰을 죽이면, 남이 61 초마다 signup 을 보내 피해자가 열어 둔 링크를 계속 무효화할 수 있다 (r3 자체 점검 🔴).
    이전 토큰은 5분 뒤 자연 만료, 성공한 verify/reset 이 invalidate_all 로 정리한다."""
    old = tokens.issue(s, "a@mju.ac.kr", "verify")
    new = tokens.issue(s, "a@mju.ac.kr", "verify")
    assert tokens.consume(s, old, "verify") == "a@mju.ac.kr"
    tokens.invalidate_all(s, "a@mju.ac.kr")  # verify 성공 뒤 라우터가 부른다
    assert tokens.consume(s, new, "verify") is None


def test_token_expires_after_5_minutes(s, monkeypatch):
    t0 = dt.datetime(2026, 9, 23, 10, 0, 0)  # noqa: DTZ001 — 앱 전역이 naive UTC (app.db.utcnow)
    monkeypatch.setattr(tokens, "utcnow", lambda: t0)
    plain = tokens.issue(s, "a@mju.ac.kr", "verify")
    monkeypatch.setattr(tokens, "utcnow", lambda: t0 + dt.timedelta(minutes=5, seconds=1))
    assert tokens.consume(s, plain, "verify") is None
    assert tokens.last_issued_at(s, "a@mju.ac.kr", "verify") == t0


def test_open_verify_extends_for_form_but_capped(s, monkeypatch):
    """링크는 5분 안에 열어야 하고, 연 뒤엔 입력 시간 30분. 여러 번 열어도 발급+35분이 상한 (r2 🟡)."""
    t0 = dt.datetime(2026, 9, 23, 10, 0, 0)  # noqa: DTZ001 — 앱 전역이 naive UTC (app.db.utcnow)
    at = lambda m: monkeypatch.setattr(tokens, "utcnow", lambda: t0 + dt.timedelta(minutes=m))
    at(0)
    plain = tokens.issue(s, "a@mju.ac.kr", "verify")
    at(4)
    assert (
        tokens.open_verify(s, plain) == "a@mju.ac.kr"
    )  # 소비하지 않는다 — 메일 스캐너가 열어도 안전
    at(20)
    assert tokens.open_verify(s, plain) == "a@mju.ac.kr"
    at(34)
    assert (
        tokens.consume(s, plain, "verify") == "a@mju.ac.kr"
    )  # 20분에 다시 열어 상한(발급+35분)까지 늘었다
    late = tokens.issue(s, "b@mju.ac.kr", "verify")
    at(34 + 6)
    assert tokens.open_verify(s, late) is None  # 5분 안에 안 열면 끝
    assert tokens.open_verify(s, "nope") is None
    r = tokens.issue(s, "a@mju.ac.kr", "reset")
    assert tokens.open_verify(s, r) is None  # reset 은 연장 없음
    assert tokens.last_issued_at(s, "a@mju.ac.kr", "reset") == t0 + dt.timedelta(minutes=40)


def test_invalidate_all(s):
    a = tokens.issue(s, "a@mju.ac.kr", "verify")
    b = tokens.issue(s, "a@mju.ac.kr", "reset")
    tokens.invalidate_all(s, "a@mju.ac.kr")
    assert tokens.consume(s, a, "verify") is None and tokens.consume(s, b, "reset") is None


def test_jwt_roundtrip_claims_expiry_and_required(s, monkeypatch):
    st = Settings()
    u = s.get(User, "a@mju.ac.kr")
    tok = tokens.jwt_encode(st, u)
    claims = tokens.jwt_decode(st, tok)
    assert (
        claims["sub"] == "a@mju.ac.kr" and claims["role"] == "student" and claims["school_id"] == 1
    )
    assert claims["tv"] == 0 and claims["exp"] - claims["iat"] == 24 * 3600
    with pytest.raises(jwt.InvalidTokenError):
        tokens.jwt_decode(st, tok[:-2] + "xx")
    no_tv = jwt.encode(
        {"sub": "a@mju.ac.kr", "exp": claims["exp"]}, st.jwt_secret, algorithm="HS256"
    )
    with pytest.raises(jwt.InvalidTokenError):  # require tv
        tokens.jwt_decode(st, no_tv)
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    with pytest.raises(jwt.InvalidTokenError):
        tokens.jwt_decode(Settings(), tok)

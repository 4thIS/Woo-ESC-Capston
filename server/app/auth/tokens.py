"""메일 토큰(5분·1회용) + JWT (S4a §2.3). 시각은 utcnow — 테스트가 monkeypatch 한다."""

from __future__ import annotations

import datetime as dt
import hashlib
import secrets

import jwt
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth.models import EmailToken, User
from app.db import utcnow
from app.settings import Settings

TOKEN_TTL = dt.timedelta(minutes=5)  # 링크를 여는 시간 (기획: 메일 링크 5분)
FORM_TTL = dt.timedelta(minutes=30)  # verify 링크를 연 뒤 이름·학번·비밀번호 입력 시간
RESEND_INTERVAL = dt.timedelta(seconds=60)


def _h(plain: str) -> str:
    return hashlib.sha256(plain.encode()).hexdigest()


def issue(s: Session, email: str, purpose: str) -> str:
    """새 토큰 발급. 평문을 돌려준다 — 메일에만 쓴다. 이전 토큰은 **건드리지 않는다**: 재발급으로 남이 연 링크를
    죽이는 방해를 막는다(이전 것은 5분 뒤 자연 만료, 성공한 verify/reset 이 invalidate_all)."""
    now = utcnow()
    plain = secrets.token_urlsafe(32)
    s.add(
        EmailToken(
            token_hash=_h(plain),
            email=email,
            purpose=purpose,
            created_at=now,
            expires_at=now + TOKEN_TTL,
        )
    )
    s.flush()
    return plain


def open_verify(s: Session, plain: str) -> str | None:
    """verify 링크를 연 순간 — 소비하지 않고 확인만, 입력 시간을 FORM_TTL 로 늘린다(발급+5+30분 상한).
    메일 스캐너가 GET 으로 열어도 토큰이 타지 않게 링크 페이지는 이 POST 를 JS 로 부른다."""
    row = s.get(EmailToken, _h(plain))
    now = utcnow()
    if row is None or row.purpose != "verify" or row.used_at is not None or row.expires_at < now:
        return None
    row.expires_at = max(row.expires_at, min(now + FORM_TTL, row.created_at + TOKEN_TTL + FORM_TTL))
    s.flush()
    return row.email


def consume(s: Session, plain: str, purpose: str) -> str | None:
    """유효하면 used_at 을 찍고 email 을 돌려준다. 만료·사용됨·purpose 불일치·없음 → None."""
    row = s.get(EmailToken, _h(plain))
    now = utcnow()
    if row is None or row.purpose != purpose or row.used_at is not None or row.expires_at < now:
        return None
    row.used_at = now
    s.flush()
    return row.email


def last_issued_at(s: Session, email: str, purpose: str) -> dt.datetime | None:
    return s.scalar(  # expires_at 은 open_verify 가 늘리므로 기준이 될 수 없다
        select(EmailToken.created_at)
        .where(EmailToken.email == email, EmailToken.purpose == purpose)
        .order_by(EmailToken.created_at.desc())
        .limit(1)
    )


def can_send(s: Session, email: str, purpose: str) -> bool:
    last = last_issued_at(s, email, purpose)
    return last is None or utcnow() - last >= RESEND_INTERVAL


def invalidate_all(s: Session, email: str) -> None:
    s.execute(
        update(EmailToken)
        .where(EmailToken.email == email, EmailToken.used_at.is_(None))
        .values(used_at=utcnow())
    )


def jwt_encode(settings: Settings, user: User) -> str:
    now = int(utcnow().replace(tzinfo=dt.UTC).timestamp())
    claims = {
        "sub": user.email,
        "role": user.role,
        "school_id": user.school_id,
        "tv": user.token_version,
        "iat": now,
        "exp": now + settings.jwt_ttl_h * 3600,
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm="HS256")


def jwt_decode(settings: Settings, token: str) -> dict:
    """실패는 jwt.InvalidTokenError (만료·필수 클레임 누락 포함) — 호출자가 401 로 바꾼다."""
    return jwt.decode(
        token, settings.jwt_secret, algorithms=["HS256"], options={"require": ["exp", "sub", "tv"]}
    )

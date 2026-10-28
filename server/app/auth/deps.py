"""가드 (S4a §3.1). JWT 검증 뒤 users 를 다시 읽어 active·token_version 을 확인한다."""

from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth import tokens
from app.auth.models import User
from app.deps import _DB

_BEARER = Depends(HTTPBearer(auto_error=False))  # B008 회피 — _DB 와 같은 모듈 싱글턴


def current_user(
    request: Request,
    cred: HTTPAuthorizationCredentials | None = _BEARER,
    s: Session = _DB,
) -> User:
    if cred is None:
        raise HTTPException(401, "인증 필요")
    try:
        claims = tokens.jwt_decode(request.app.state.settings, cred.credentials)
    except jwt.InvalidTokenError as e:
        raise HTTPException(401, "인증 필요") from e
    user = s.get(User, claims["sub"])
    if user is None or user.status != "active" or user.token_version != claims["tv"]:
        raise HTTPException(401, "인증 필요")
    return user


CurrentUser = Depends(current_user)


def require_admin(user: User = CurrentUser) -> User:
    if user.role != "admin":
        raise HTTPException(403, "관리자만")
    return user


def require_student(user: User = CurrentUser) -> User:
    if user.role != "student":
        raise HTTPException(403, "학생만")
    return user


AdminUser = Depends(require_admin)
StudentUser = Depends(require_student)

"""가드 (S4a §3.1). JWT 검증 뒤 users 를 다시 읽어 active·token_version 을 확인한다."""

from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth import scope, tokens
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
    """최고 관리자(admin)만 (#160). 건물 관리자는 403 — 범위 검사를 붙인 API 만 ManagerUser 로 연다(fail-closed)."""
    if user.role != "admin":
        raise HTTPException(403, "최고 관리자만")
    return user


def require_manager(user: User = CurrentUser) -> User:
    """최고 관리자 · 건물 관리자. 이 가드를 쓰는 API 는 반드시 scope.of 로 건물 범위를 건다 (#160)."""
    if user.role not in ("admin", "building_admin"):
        raise HTTPException(403, "관리자만")
    return user


def require_student(user: User = CurrentUser) -> User:
    if user.role != "student":
        raise HTTPException(403, "학생만")
    return user


AdminUser = Depends(require_admin)
SuperUser = AdminUser  # 최고 관리자 전용 — 이름을 뜻대로 쓰고 싶을 때
ManagerUser = Depends(require_manager)
StudentUser = Depends(require_student)


def manager_scope(user: User = ManagerUser, s: Session = _DB) -> scope.Scope:
    """관리 API 의 범위 — 최고 관리자는 학교 전체, 건물 관리자는 맡은 건물 (#160)."""
    return scope.of(s, user)


MgrScope = Depends(manager_scope)

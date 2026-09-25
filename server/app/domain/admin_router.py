"""관리자 요약·모니터 REST (S4b §4.1). 전부 관리자 전용 + 학교 스코프. 계산은 domain/admin.py."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query
from sqlalchemy.orm import Session

from app import schemas as S
from app.auth import scope
from app.auth.deps import AdminUser
from app.auth.models import User
from app.deps import _DB
from app.domain import admin
from app.domain.models import Building

router = APIRouter(prefix="/api/admin", dependencies=[AdminUser])

Only = Literal["warn", "unseen", "low_batt", "resync", "clock_stale"]


@router.get("/nodes", response_model=list[S.NodeOut])
def nodes(
    building_id: int | None = None,
    only: Only | None = None,
    user: User = AdminUser,
    s: Session = _DB,
):
    if building_id is not None:
        scope.get_scoped(s, Building, building_id, user.school_id)
    rows = admin.expected_nodes(s, user.school_id, building_id)
    if only == "warn":
        rows = [r for r in rows if r["warnings"]]
    elif only is not None:
        rows = [r for r in rows if only in r["warnings"]]
    return rows


@router.get("/outbox/failed", response_model=list[S.FailedOut])
def failed(
    days: int = Query(admin.FAILED_DAYS_DEFAULT, ge=1, le=90),
    limit: int = Query(100, ge=1, le=500),
    user: User = AdminUser,
    s: Session = _DB,
):
    return admin.failed_outbox(s, user.school_id, days, limit)


@router.get("/summary", response_model=S.SummaryOut)
def summary(
    preview: int = Query(admin.PREVIEW_DEFAULT, ge=1, le=admin.PREVIEW_MAX),
    user: User = AdminUser,
    s: Session = _DB,
):
    return admin.summary(s, user.school_id, preview)

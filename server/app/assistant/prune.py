"""오래된 AI 비서 기록 정리 — 매일 작업(app.domain.daily)이 부른다 (spec §5.5: 턴 기록 180일)."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.assistant.models import AssistantConversation, AssistantPreview, AssistantTurn

TURN_KEEP_DAYS = 180
CONV_KEEP_DAYS = 1  # 30분이면 만료 — 하루 지나면 지운다
PREVIEW_KEEP_DAYS = 1  # 10분이면 만료 — 변경 기록은 preview_id 문자열만 가진다


def prune(s: Session, now_utc: dt.datetime) -> dict:
    turn_cut = now_utc - dt.timedelta(days=TURN_KEEP_DAYS)
    conv_cut = now_utc - dt.timedelta(days=CONV_KEEP_DAYS)
    pv_cut = now_utc - dt.timedelta(days=PREVIEW_KEEP_DAYS)
    return {
        "turns": s.execute(
            delete(AssistantTurn).where(AssistantTurn.created_at < turn_cut)
        ).rowcount,
        "conversations": s.execute(
            delete(AssistantConversation).where(AssistantConversation.updated_at < conv_cut)
        ).rowcount,
        "previews": s.execute(
            delete(AssistantPreview).where(AssistantPreview.expires_at < pv_cut)
        ).rowcount,
    }

"""AI 비서 표 (spec §5.5·§9). 마이그레이션 web_assistant_*. 시각은 naive UTC (app.db.utcnow).
JSON 칸은 Text 에 json.dumps(ensure_ascii=False) 로 넣는다."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, utcnow


class AssistantConversation(Base):
    __tablename__ = "assistant_conversations"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # "c_" + 16 hex
    user_email: Mapped[str] = mapped_column(ForeignKey("users.email", ondelete="CASCADE"))
    state: Mapped[str] = mapped_column(Text)  # dialog 상태 JSON, 닫히면 "null"
    created_at: Mapped[dt.datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(default=utcnow)
    closed_at: Mapped[dt.datetime | None]
    __table_args__ = (Index("ix_assistant_conv_updated", "updated_at"),)


class AssistantTurn(Base):
    """학습용 대화 기록 — 서버에만, 180일 뒤 지운다 (spec §5.5)."""

    __tablename__ = "assistant_turns"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String)
    user_email: Mapped[str] = mapped_column(String)
    utterance: Mapped[str] = mapped_column(Text)
    form: Mapped[str | None] = mapped_column(
        Text
    )  # 모델 출력 JSON, 못 읽은 출력(raw_output)은 원문 텍스트, 버튼 선택 턴은 NULL
    choice: Mapped[str | None] = mapped_column(String)
    reply_kind: Mapped[str] = mapped_column(String)
    reply_message: Mapped[str] = mapped_column(Text)
    model_rev: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[dt.datetime] = mapped_column(default=utcnow)
    __table_args__ = (Index("ix_assistant_turns_created", "created_at"),)


class AssistantPreview(Base):
    __tablename__ = "assistant_previews"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # "p_" + 16 hex
    conversation_id: Mapped[str] = mapped_column(String)
    user_email: Mapped[str] = mapped_column(String)
    draft: Mapped[str] = mapped_column(
        Text
    )  # 해석이 끝난 초안 — 지문이 바뀌면 이것으로 다시 미리보기
    ops: Mapped[str] = mapped_column(Text)  # 확정 변경 목록 — 적용은 이것만 실행한다
    room_ids: Mapped[str] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String)
    blockers: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[dt.datetime]
    applied_at: Mapped[dt.datetime | None]
    __table_args__ = (Index("ix_assistant_previews_expires", "expires_at"),)


class AssistantChange(Base):
    __tablename__ = "assistant_changes"
    id: Mapped[int] = mapped_column(primary_key=True)
    preview_id: Mapped[str] = mapped_column(String)
    user_email: Mapped[str] = mapped_column(String)
    school_id: Mapped[int]
    building_ids: Mapped[str] = mapped_column(Text)  # 건물 관리자 목록 범위 거르기
    utterance: Mapped[str] = mapped_column(Text)
    ops: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    outbox_ids: Mapped[str] = mapped_column(Text)
    model_rev: Mapped[str | None] = mapped_column(String)
    applied_at: Mapped[dt.datetime] = mapped_column(default=utcnow)
    __table_args__ = (Index("ix_assistant_changes_school", "school_id", "applied_at"),)

"""턴 처리 — 대화 상태 읽기 → 반영 → 진행 → 저장·기록 (spec §4·§5.5). 라우터는 이 모듈만 부른다.
세션은 단계마다 새로 연다 — 미리보기(별도 세션에서 쓰고 되돌림)와 쓰기 잠금이 엇갈리지 않게."""

from __future__ import annotations

import datetime as dt
import json
import secrets

from assistant_proto import FormError, parse_form, render_prefix, rules
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.assistant import answers, dialog, manifest, preview
from app.assistant.models import AssistantChange, AssistantConversation, AssistantTurn
from app.assistant.schemas import TurnIn
from app.auth.scope import Scope
from app.domain import clock

CONV_TTL = dt.timedelta(minutes=30)
EXAMPLE = "예: '803호 이번 주 금요일 15시부터 18시까지 특강 등록해줘'"
CAN_DO = (
    "일정·시험기간·정규 시간표의 등록·수정·삭제, 학생 신청 승인·거절, "
    "빈 강의실·일정·신청·노드 조회를 할 수 있습니다."
)
EXPIRED = "대화가 만료되었습니다. 다시 말씀해 주세요."


def _j(x) -> str:
    return json.dumps(x, ensure_ascii=False)


def _prefix(state: dict, slot: str | None, question: str) -> str:
    items = rules.state_items(state["intent"], state["target"], state["set"], slot)
    return render_prefix(state["intent"], items, question)


def _out(
    conv_id, kind, message, *, choices=None, prefix=None, closed=False, pv=None, answer=None
) -> dict:
    return {
        "conversation_id": conv_id,
        "kind": kind,
        "message": message,
        "choices": choices or [],
        "next_prefix": None if closed else prefix,
        "closed": closed,
        "preview": pv,
        "answer": answer,
    }


def _keep(conv_id: str, state: dict | None, message: str) -> dict:
    """오류 — 진행 중인 대화가 있으면 그대로 두고 이어서 말하게 한다."""
    if state is None:
        return _out(conv_id, "error", message, closed=True)
    return _out(conv_id, "error", message, prefix=_prefix(state, state.get("asked"), message))


def _step(Session, sc: Scope, conv_id: str, state: dict | None, body: TurnIn, now_local):
    lead = ""
    try:
        if body.raw_output is not None:
            raise FormError("모델 출력이 JSON 이 아님")
        if body.form is not None:
            state, lead = dialog.absorb(state, parse_form(body.form), body.utterance)
        else:
            state = dialog.choose(state, body.choice, body.utterance)
    except FormError:
        return _keep(
            conv_id, state, "요청을 이해하지 못했습니다. 다르게 말씀해 주세요. " + EXAMPLE
        ), state
    except dialog.Unsupported:
        return _keep(conv_id, state, "그 요청은 AI 비서가 할 수 없습니다. " + CAN_DO), state
    except dialog.NeedContext:
        if body.choice is not None:
            return _keep(
                conv_id, state, "그 선택지는 지금 고를 수 없습니다. 다시 말씀해 주세요."
            ), state
        return _keep(conv_id, state, "무엇을 할지 먼저 말씀해 주세요. " + EXAMPLE), state
    if state is None:  # 취소
        return _out(conv_id, "answer", lead, closed=True), None
    with Session() as s:
        d = dialog.advance(s, sc, state, now_local)
        if isinstance(d, dialog.Answer):
            ans = answers.answer(s, sc, d.draft, now_local)
            return _out(conv_id, "answer", lead + ans["title"], closed=True, answer=ans), None
    if isinstance(d, dialog.Ask):
        prefix = _prefix(d.state, d.state["asked"], d.question)
        return _out(conv_id, "ask", lead + d.question, choices=d.choices, prefix=prefix), d.state
    if isinstance(d, dialog.Fail):
        return _out(
            conv_id, "error", lead + d.message, prefix=_prefix(d.state, None, d.message)
        ), d.state
    pv = preview.make_preview(Session, sc, conv_id, d.draft, now_local)
    msg = (
        "적용할 수 없는 변경이 있습니다. 오른쪽에서 이유를 확인해 주세요."
        if pv["blockers"]
        else "오른쪽에서 바뀌는 내용을 확인하고 [적용]을 눌러 주세요."
    )
    return _out(
        conv_id, "preview", lead + msg, prefix=_prefix(d.state, None, rules.PREVIEW_QUESTION), pv=pv
    ), d.state


def _save(Session, sc: Scope, conv_id: str, state: dict | None, now_utc: dt.datetime) -> None:
    with Session() as s, s.begin():
        c = s.get(AssistantConversation, conv_id)
        if c is None:
            if state is not None:
                s.add(
                    AssistantConversation(
                        id=conv_id,
                        user_email=sc.email,
                        state=_j(state),
                        created_at=now_utc,
                        updated_at=now_utc,
                    )
                )
            return
        c.state, c.updated_at = _j(state), now_utc
        if state is None:
            c.closed_at = now_utc


def _log(Session, sc: Scope, conv_id: str, body: TurnIn, out: dict, now_utc: dt.datetime) -> None:
    with Session() as s, s.begin():
        s.add(
            AssistantTurn(
                conversation_id=conv_id,
                user_email=sc.email,
                utterance=body.utterance,
                form=_j(body.form) if body.form is not None else body.raw_output,
                choice=body.choice,
                reply_kind=out["kind"],
                reply_message=out["message"],
                model_rev=manifest.current_revision(),
                created_at=now_utc,
            )
        )


def handle_turn(Session: sessionmaker, sc: Scope, body: TurnIn, now_local: dt.datetime) -> dict:
    now_utc = clock.to_utc(now_local)
    conv_id, state = body.conversation_id, None
    if conv_id is not None:
        with Session() as s:
            c = s.get(AssistantConversation, conv_id)
            alive = (
                c is not None
                and c.user_email == sc.email
                and c.closed_at is None
                and now_utc - c.updated_at <= CONV_TTL
            )
            state = json.loads(c.state) if alive else None
        if not alive:
            out = _out(conv_id, "error", EXPIRED, closed=True)
            _log(Session, sc, conv_id, body, out, now_utc)
            return out
    else:
        conv_id = "c_" + secrets.token_hex(8)
    out, new_state = _step(Session, sc, conv_id, state, body, now_local)
    _save(Session, sc, conv_id, new_state, now_utc)
    _log(Session, sc, conv_id, body, out, now_utc)
    return out


def list_changes(Session: sessionmaker, sc: Scope, limit: int) -> list[dict]:
    """자기 범위의 변경 기록 — 건물 관리자는 맡은 건물 안에서만 바뀐 것."""
    out = []
    with Session() as s:
        q = (
            select(AssistantChange)
            .where(AssistantChange.school_id == sc.school_id)
            .order_by(AssistantChange.id.desc())
            .limit(500)
        )
        for c in s.scalars(q):
            if sc.buildings is not None and not set(json.loads(c.building_ids)) <= sc.buildings:
                continue
            out.append(
                {
                    "id": c.id,
                    "applied_at": c.applied_at.replace(tzinfo=dt.UTC),
                    "user_email": c.user_email,
                    "utterance": c.utterance,
                    "summary": json.loads(c.summary),
                    "outbox_ids": json.loads(c.outbox_ids),
                }
            )
            if len(out) >= limit:
                break
    return out

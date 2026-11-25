"""대화 상태와 한 턴의 진행 (spec §4). 상태는 JSON 으로 DB(assistant_conversations.state)에 둔다 —
프로세스 메모리에 두지 않는다(워커 1개라도 재시작에 안전).

상태 키: intent · target · set(표현 그대로) · room_pick · pick · asked · pending · utterances"""

from __future__ import annotations

import copy
import datetime as dt
from dataclasses import dataclass, field

from assistant_proto import (
    TYPE_LABELS,
    Form,
    form_to_dict,
    resolve_time,
    resolve_weekdays,
    resolve_when,
    rules,
    type_code,
)
from sqlalchemy.orm import Session

from app.assistant import changes, rooms
from app.auth.scope import Scope

TYPE_CHOICES = [{"id": f"type:{x}", "label": x} for x in ("특강", "대여", "휴강", "수업", "시험")]


class Unsupported(Exception):
    """unknown — AI 비서가 할 수 없는 요청."""


class NeedContext(Exception):
    """이어 갈 대화가 없는데 fill·선택이 왔다(또는 내놓지 않은 선택지)."""


@dataclass
class Ask:
    question: str
    state: dict
    choices: list[dict] = field(default_factory=list)


@dataclass
class Fail:
    message: str
    state: dict


@dataclass
class Ready:
    draft: dict
    state: dict


@dataclass
class Answer:
    draft: dict


def new_state(form_dict: dict, utterance: str) -> dict:
    return {
        "intent": form_dict["intent"],
        "target": dict(form_dict["target"]),
        "set": dict(form_dict["set"]),
        "room_pick": {},
        "pick": {},
        "asked": None,
        "pending": None,
        "utterances": [utterance],
    }


def _merge(dst: dict, src: dict) -> None:
    """rooms 는 더하고(순서 유지·중복 제거), 나머지 칸은 덮어쓴다."""
    for k, v in src.items():
        dst[k] = list(dict.fromkeys([*dst.get("rooms", []), *v])) if k == "rooms" else v


def absorb(state: dict | None, form: Form, utterance: str) -> tuple[dict | None, str]:
    d = form_to_dict(form)
    if form.intent == "cancel":
        return None, "취소했습니다."
    if form.intent == "unknown":
        raise Unsupported
    if form.intent == "fill":
        if state is None:
            raise NeedContext
        st = copy.deepcopy(state)
        p = st.get("pending")
        if p and p["kind"] == "room" and "rooms" in d["set"]:  # 버튼 대신 말로 고른 강의실
            sec = p["section"]
            st[sec]["rooms"] = [x for x in st[sec].get("rooms", []) if x != p["expr"]]
        sec = (st["asked"] or f"{rules.PRIMARY[st['intent']]}.any").split(".")[0]
        _merge(st[sec], d["set"])
        _merge(st["target"], d["target"])
        st["utterances"].append(utterance)
        st["asked"], st["pending"], st["pick"] = None, None, {}
        return st, ""
    lead = "앞의 요청은 그만두고 새로 시작합니다. " if state is not None else ""
    return new_state(d, utterance), lead


def choose(state: dict | None, choice: str, utterance: str) -> dict:
    p = (state or {}).get("pending")
    if not p or choice not in p["options"]:
        raise NeedContext
    st = copy.deepcopy(state)
    kind, _, val = choice.partition(":")
    if kind == "room":
        st["room_pick"][p["key"]] = {"ids": [int(val)]}
    elif kind == "bld":
        st["room_pick"][p["key"]] = {"building": int(val)}
    elif kind == "pick":
        room_id, _, key = val.partition(":")
        st["pick"][room_id] = key
    elif kind == "type" and val in TYPE_LABELS:
        st[p["section"]]["type"] = val
    else:
        raise NeedContext
    st["utterances"].append(utterance)
    st["asked"], st["pending"] = None, None
    return st


EVENT_SPAN_MAX = 31  # 날짜 기간을 하루씩 펼칠 때 최대 일수
WEEKLY_HINT = (
    "매주 반복되는 일정은 정규 시간표로 요청해 주세요. (예: 803 매주 월 9~12시 자료구조 추가)"
)


def _ask(state: dict, slot: str, question: str, *, choices=None, pending=None) -> Ask:
    st = copy.deepcopy(state)
    st["asked"], st["pending"] = slot, pending
    return Ask(question, st, choices or [])


def _reask(state: dict, sec: str, f: str, message: str) -> Ask:
    """풀지 못한 칸을 비우고 다시 묻는다 — 다음 답(fill)이 그 칸을 새로 채운다."""
    st = copy.deepcopy(state)
    st[sec].pop(f, None)
    return _ask(st, f"{sec}.{f}", message)


def _rooms(s: Session, sc: Scope, state: dict, sec: str, expr: str) -> list[int] | Ask:
    key = f"{sec}:{expr}"
    pick = state["room_pick"].get(key) or {}
    if "ids" in pick:
        ok = {r.id for r in rooms.scoped_rooms(s, sc)}
        if all(i in ok for i in pick["ids"]):  # 그사이 범위가 줄었으면 다시 푼다
            return pick["ids"]
    got = rooms.resolve_room_expr(s, sc, expr, only_building=pick.get("building"))
    if isinstance(got, rooms.Found):
        return [r.id for r in got.rooms]
    if isinstance(got, rooms.Ambiguous):
        opts = [{"id": i, "label": label} for i, label in got.options]
        return _ask(
            state,
            f"{sec}.rooms",
            f"'{expr}' 강의실이 여러 곳에 있습니다. 어느 곳인가요?",
            choices=opts,
            pending={
                "kind": "room",
                "key": key,
                "section": sec,
                "expr": expr,
                "options": [o["id"] for o in opts],
            },
        )
    st = copy.deepcopy(state)
    st[sec]["rooms"] = [x for x in st[sec]["rooms"] if x != expr]
    if not st[sec]["rooms"]:
        del st[sec]["rooms"]
    return _ask(
        st,
        f"{sec}.rooms",
        f"'{expr}' 강의실을 찾지 못했습니다. 강의실을 다시 알려 주세요. (예: 803, 공학관 803)",
    )


def _when(intent: str, sec: str, expr: str, now_local: dt.datetime) -> dict | str:
    """날짜 표현 → 초안 칸. 문자열을 돌려주면 그 문구로 다시 묻는다."""
    grp = intent.split(".")[0]
    if grp == "class":
        wds = resolve_weekdays(expr)
        if not wds:
            return "요일을 '월', '화목'처럼 알려 주세요."
        if intent == "class.change" and sec == "set" and len(wds) != 1:
            return "옮길 요일을 하나만 알려 주세요."
        return {"weekdays": list(wds)}
    w = resolve_when(expr, now_local)
    if w is None:
        if grp == "exam":
            return "기간을 '12/15~12/19'처럼 알려 주세요."
        return "날짜를 '12/3'이나 '이번 주 금요일'처럼 알려 주세요."
    if w.kind == "weekdays":
        return WEEKLY_HINT
    if grp == "exam":
        if w.kind == "range":
            return {"range": [w.start.isoformat(), w.end.isoformat()]}
        if len(w.dates) == 1:
            return {"range": [w.dates[0].isoformat()] * 2}
        return "시험기간은 '12/15~12/19'처럼 이어진 기간으로 알려 주세요."
    if w.kind == "range":
        n = (w.end - w.start).days + 1
        if n > EVENT_SPAN_MAX:
            return f"기간은 {EVENT_SPAN_MAX}일까지 한 번에 다룰 수 있습니다."
        days = [w.start + dt.timedelta(days=i) for i in range(n)]
        out = {
            "dates": [d.isoformat() for d in days],
            "range": [w.start.isoformat(), w.end.isoformat()],
        }
    else:
        out = {"dates": [d.isoformat() for d in w.dates]}
    if intent == "event.change" and sec == "set" and len(out["dates"]) != 1:
        return "옮길 날짜를 하나만 알려 주세요."
    return out


def advance(
    s: Session, sc: Scope, state: dict, now_local: dt.datetime
) -> Ask | Fail | Ready | Answer:
    """빈 칸 → 강의실 → 날짜·시각 → (휴강 펼치기) → 대상 찾기 순으로 막히는 곳에서 묻는다."""
    intent = state["intent"]
    slot = rules.missing(intent, state["target"], state["set"])
    if slot:
        sec, f = slot.split(".")
        q = rules.question(intent, slot, state["set"].get("type") or state["target"].get("type"))
        if f == "type":
            return _ask(
                state,
                slot,
                q,
                choices=TYPE_CHOICES,
                pending={
                    "kind": "type",
                    "section": sec,
                    "options": [c["id"] for c in TYPE_CHOICES],
                },
            )
        return _ask(state, slot, q)
    res: dict = {"target": {}, "set": {}}
    for sec in ("target", "set"):
        for expr in list(state[sec].get("rooms", [])):
            got = _rooms(s, sc, state, sec, expr)
            if isinstance(got, Ask):
                return got
            res[sec]["rooms"] = list(dict.fromkeys([*res[sec].get("rooms", []), *got]))
    for sec in ("target", "set"):
        d = state[sec]
        if "when" in d:
            v = _when(intent, sec, d["when"], now_local)
            if isinstance(v, str):
                return _reask(state, sec, "when", v)
            res[sec].update(v)
        if "time" in d:
            ts = resolve_time(d["time"])
            if ts is None:
                return _reask(state, sec, "time", "시각을 '15시~18시'처럼 알려 주세요.")
            end = ts.end.strftime("%H:%M") if ts.end else None
            res[sec]["time"] = [ts.start.strftime("%H:%M"), end]
        if "type" in d:
            res[sec]["type"] = type_code(d["type"])
        for f in ("subject", "professor", "reason", "requester"):
            if f in d:
                res[sec][f] = d[f]
    draft = {
        "intent": intent,
        "target": res["target"],
        "set": res["set"],
        "pick": dict(state["pick"]),
        "utterances": list(state["utterances"]),
    }
    if intent.startswith("ask."):
        return Answer(draft)
    if intent == "event.add" and (need := changes.fill_from_slots(s, draft)):
        return _reask(state, "set", need[0], need[1])
    st = draft["set"]
    if intent in ("event.add", "class.add") and "entries" not in st and st["time"][1] is None:
        return _reask(state, "set", "time", "끝나는 시각도 알려 주세요. (예: 15시~18시)")
    if intent.endswith(".add"):
        return Ready(draft, state)
    cands = changes.find_candidates(s, sc, draft, now_local)
    if not any(cands.values()):
        return Fail(changes.not_found_message(intent), state)
    labels = changes.room_labels(s, [r for r in cands if r])
    for room_id, lst in cands.items():
        if len(lst) > 1 and draft["pick"].get(str(room_id)) not in {c["key"] for c in lst}:
            opts = [
                {
                    "id": f"pick:{room_id}:{c['key']}",
                    "label": f"{labels[room_id]} · {c['label']}" if room_id else c["label"],
                }
                for c in lst
            ]
            return _ask(
                state,
                "target.pick",
                "어느 것인가요?",
                choices=opts,
                pending={"kind": "pick", "options": [o["id"] for o in opts]},
            )
    return Ready(draft, state)

"""대화 상태와 한 턴의 진행 (spec §4). 상태는 JSON 으로 DB(assistant_conversations.state)에 둔다 —
프로세스 메모리에 두지 않는다(워커 1개라도 재시작에 안전).

상태 키: intent · target · set(표현 그대로) · room_pick · pick · asked · pending · utterances ·
q(직전에 접두어에 넣은 질문 — 오류 턴이 이어 쓴다, service 가 채운다) ·
room_menu(강의실 목록에서 고른 건물 {칸: 건물 id}) · fixed(못 찾은 대상 대신 목록에서 고른 것
{방 id: 후보 key}) — 둘은 나중에 더한 키라 옛 상태에는 없다(.get 으로 읽는다)

접두어 질문 줄(Ask.question·PICK_QUESTION·PREVIEW_QUESTION)은 항상 assistant_proto.rules 의 글자다.
사람에게 보여 줄 설명(날짜를 '12/3'처럼…, 여러 곳에 있습니다…)은 Ask.message 에만 둔다."""

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

ROOM_LIST_MAX = 24  # 범위 안 강의실이 이보다 많고 건물이 여럿이면 건물을 먼저 고른다
FIX_MAX = 20  # 대상을 못 찾았을 때 보여 줄 그 강의실 일정·수업 수
ROOM_HINT = "현재 있는 강의실은 아래와 같습니다. 고르거나 직접 알려 주세요."
BLD_HINT = "건물을 먼저 골라 주세요."
FIX_HINT = {
    "event": "이 강의실의 2주 안 일정은 아래와 같습니다. 고르거나 다시 알려 주세요.",
    "class": "이 강의실의 정규 수업은 아래와 같습니다. 고르거나 다시 알려 주세요.",
}

TYPE_CHOICES = [{"id": f"type:{x}", "label": x} for x in ("특강", "대여", "휴강", "수업", "시험")]


class Unsupported(Exception):
    """unknown — AI 비서가 할 수 없는 요청."""


class NeedContext(Exception):
    """이어 갈 대화가 없는데 fill·선택이 왔다(또는 내놓지 않은 선택지)."""


@dataclass
class Ask:
    question: str  # 접두어 '질문:' 줄 — rules 글자
    state: dict
    choices: list[dict] = field(default_factory=list)
    message: str = ""  # 화면에 보일 문구 (비면 question)

    def __post_init__(self):
        self.message = self.message or self.question


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
        st.pop("room_menu", None)
        st.pop("fixed", None)
        return st, ""
    lead = "앞의 요청은 그만두고 새로 시작합니다. " if state is not None else ""
    return new_state(d, utterance), lead


def choose(state: dict | None, choice: str, utterance: str) -> dict:
    p = (state or {}).get("pending")
    if not p or choice not in p["options"]:
        raise NeedContext
    st = copy.deepcopy(state)
    kind, _, val = choice.partition(":")
    if (
        p["kind"] == "room_list"
    ):  # 강의실 목록 — 고른 방을 그 라벨로 더하고, 그 라벨은 고른 방으로 못 박는다
        sec = p["section"]
        if kind == "room":
            label = p["labels"][val]
            st[sec]["rooms"] = list(dict.fromkeys([*st[sec].get("rooms", []), label]))
            st["room_pick"][f"{sec}:{label}"] = {"ids": [int(val)]}
            (st.get("room_menu") or {}).pop(sec, None)
        else:
            st.setdefault("room_menu", {})[sec] = int(val)
    elif kind == "fix":
        room_id, _, key = val.partition(":")
        st.setdefault("fixed", {})[room_id] = key
    elif kind == "room":
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


def _slot_q(state: dict, slot: str) -> str:
    return rules.question(
        state["intent"], slot, state["set"].get("type") or state["target"].get("type")
    )


def _ask(
    state: dict, slot: str, question: str, *, message: str = "", choices=None, pending=None
) -> Ask:
    st = copy.deepcopy(state)
    st["asked"], st["pending"] = slot, pending
    return Ask(question, st, choices or [], message)


def _reask(state: dict, sec: str, f: str, message: str) -> Ask:
    """풀지 못한 칸을 비우고 다시 묻는다 — 다음 답(fill)이 그 칸을 새로 채운다.
    접두어 질문은 그 칸의 rules 질문, 안내(message)는 따로."""
    st = copy.deepcopy(state)
    st[sec].pop(f, None)
    return _ask(st, f"{sec}.{f}", _slot_q(st, f"{sec}.{f}"), message=message)


def _room_menu(s: Session, sc: Scope, state: dict, slot: str, message: str = "") -> Ask:
    """강의실을 묻는 질문 + 범위 안 강의실 버튼. 많고 건물이 여럿이면 건물 버튼부터."""
    sec = slot.split(".")[0]
    q = _slot_q(state, slot)
    refs = rooms.scoped_rooms(s, sc)
    bld = (state.get("room_menu") or {}).get(sec)
    if bld is not None:
        refs = [r for r in refs if r.building_id == bld] or refs
    blds = list(dict.fromkeys(r.building_id for r in refs))
    if len(refs) > ROOM_LIST_MAX and len(blds) > 1:
        names = {r.building_id: r.building for r in refs}
        opts = [
            {"id": f"bld:{b}", "label": f"{names[b]} ({sum(r.building_id == b for r in refs)}개)"}
            for b in blds
        ]
        hint, labels = BLD_HINT, {}
    else:
        opts = [{"id": f"room:{r.id}", "label": r.label} for r in refs]
        hint, labels = ROOM_HINT, {str(r.id): r.label for r in refs}
    if not opts:
        return _ask(state, slot, q, message=message)
    return _ask(
        state,
        slot,
        q,
        message=f"{message or q} {hint}",
        choices=opts,
        pending={
            "kind": "room_list",
            "section": sec,
            "options": [o["id"] for o in opts],
            "labels": labels,
        },
    )


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
            rules.PICK_QUESTION,
            message=f"'{expr}' 강의실이 여러 곳에 있습니다. 어느 곳인가요?",
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
    return _room_menu(s, sc, st, f"{sec}.rooms", message=f"'{expr}' 강의실을 찾지 못했습니다.")


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
    for sec in state.get("room_menu") or {}:  # 건물을 골랐다 — 그 건물 강의실을 보여 준다
        return _room_menu(s, sc, state, f"{sec}.rooms")
    slot = rules.missing(intent, state["target"], state["set"])
    if slot:
        sec, f = slot.split(".")
        q = _slot_q(state, slot)
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
        if f == "rooms":
            return _room_menu(s, sc, state, slot)
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
    if state.get("fixed"):
        draft["fixed"] = dict(state["fixed"])
    if intent.startswith("ask."):
        return Answer(draft)
    if intent == "event.add" and (need := changes.fill_from_slots(s, draft, now_local)):
        return _reask(state, "set", need[0], need[1])
    st = draft["set"]
    if intent in ("event.add", "class.add") and "entries" not in st and st["time"][1] is None:
        return _reask(state, "set", "time", "끝나는 시각도 알려 주세요. (예: 15시~18시)")
    if intent.endswith(".add"):
        return Ready(draft, state)
    cands = changes.find_candidates(s, sc, draft, now_local)
    if not any(cands.values()):
        st = copy.deepcopy(state)  # 다음 답은 '대상'을 고쳐 말하는 것 — target 칸으로 합친다
        st["asked"], st["pending"] = "target.any", None
        grp = intent.split(".")[0]
        if grp in FIX_HINT:  # 그 강의실에 있는 일정·수업을 버튼으로 — 고르면 그것이 대상이다
            loose = changes.loose_candidates(s, draft, now_local)
            labels = changes.room_labels(s, list(loose))
            opts = [
                {"id": f"fix:{rid}:{c['key']}", "label": f"{labels[rid]} · {c['label']}"}
                for rid, lst in loose.items()
                for c in lst
            ][:FIX_MAX]
            if opts:
                return _ask(
                    st,
                    "target.any",
                    rules.question(intent, "target.any"),
                    message=f"{changes.not_found_message(intent)} {FIX_HINT[grp]}",
                    choices=opts,
                    pending={"kind": "fix", "options": [o["id"] for o in opts]},
                )
        return Fail(changes.not_found_message(intent), st)
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
                rules.PICK_QUESTION,
                message="어느 것인가요?",
                choices=opts,
                pending={"kind": "pick", "options": [o["id"] for o in opts]},
            )
    return Ready(draft, state)

"""대화 상태와 한 턴의 진행 (spec §4). 상태는 JSON 으로 DB(assistant_conversations.state)에 둔다 —
프로세스 메모리에 두지 않는다(워커 1개라도 재시작에 안전).

상태 키: intent · target · set(표현 그대로) · room_pick · pick · asked · pending · utterances"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from assistant_proto import TYPE_LABELS, Form, form_to_dict, rules

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

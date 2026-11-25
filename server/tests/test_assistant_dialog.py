import pytest
from assistant_proto import parse_form

from app.assistant import dialog as D


def F(intent, target=None, set_=None):
    return parse_form({"v": 1, "intent": intent, "target": target or {}, "set": set_ or {}})


def test_new_request_starts_state():
    st, lead = D.absorb(None, F("event.add", set_={"rooms": ["803"]}), "803 특강")
    assert lead == ""
    assert st == {
        "intent": "event.add",
        "target": {},
        "set": {"rooms": ["803"]},
        "room_pick": {},
        "pick": {},
        "asked": None,
        "pending": None,
        "utterances": ["803 특강"],
    }


def test_cancel_unknown_and_fill_without_state():
    st = D.new_state({"intent": "event.add", "target": {}, "set": {}}, "u")
    assert D.absorb(st, F("cancel"), "취소") == (None, "취소했습니다.")
    with pytest.raises(D.Unsupported):
        D.absorb(st, F("unknown"), "안녕")
    with pytest.raises(D.NeedContext):
        D.absorb(None, F("fill", set_={"subject": "x"}), "x")


def test_fill_goes_to_asked_section_and_rooms_accumulate():
    st = D.new_state({"intent": "event.change", "target": {"rooms": ["803"]}, "set": {}}, "u1")
    st["asked"] = "target.when"
    st2, lead = D.absorb(st, F("fill", set_={"when": "금요일"}), "금요일")
    assert lead == "" and st2["target"] == {"rooms": ["803"], "when": "금요일"} and st2["set"] == {}
    assert st2["asked"] is None and st2["utterances"] == ["u1", "금요일"]
    assert st["target"] == {"rooms": ["803"]}  # 원본은 그대로(깊은 복사)

    add = D.new_state({"intent": "event.add", "target": {}, "set": {"rooms": ["803"]}}, "u")
    add2, _ = D.absorb(add, F("fill", set_={"rooms": ["801", "803"]}), "801도")
    assert add2["set"]["rooms"] == ["803", "801"]

    # 묻는 칸이 없으면 intent 의 기본 묶음 — 수정은 새 값(set)
    ch = D.new_state({"intent": "event.change", "target": {"rooms": ["803"]}, "set": {}}, "u")
    ch2, _ = D.absorb(ch, F("fill", set_={"time": "16시"}), "16시로")
    assert ch2["set"] == {"time": "16시"}


def test_fill_after_room_question_replaces_ambiguous_expr():
    st = D.new_state({"intent": "event.add", "target": {}, "set": {"rooms": ["803", "801"]}}, "u")
    st["asked"] = "set.rooms"
    st["pending"] = {
        "kind": "room",
        "key": "set:803",
        "section": "set",
        "expr": "803",
        "options": ["room:1", "room:2"],
    }
    st2, _ = D.absorb(st, F("fill", set_={"rooms": ["공학관 803"]}), "공학관 803")
    assert st2["set"]["rooms"] == ["801", "공학관 803"] and st2["pending"] is None


def test_new_intent_replaces_with_notice():
    st = D.new_state({"intent": "event.add", "target": {}, "set": {"rooms": ["803"]}}, "u")
    st2, lead = D.absorb(st, F("ask.requests"), "신청 보여줘")
    assert lead == "앞의 요청은 그만두고 새로 시작합니다. "
    assert st2["intent"] == "ask.requests" and st2["utterances"] == ["신청 보여줘"]


def test_choose_only_offered_options():
    st = D.new_state({"intent": "event.add", "target": {}, "set": {"rooms": ["803"]}}, "u")
    with pytest.raises(D.NeedContext):
        D.choose(st, "room:7", "x")  # 내놓은 선택지 없음
    st["pending"] = {
        "kind": "room",
        "key": "set:803",
        "section": "set",
        "expr": "803",
        "options": ["room:7", "room:8"],
    }
    st["asked"] = "set.rooms"
    with pytest.raises(D.NeedContext):
        D.choose(st, "room:9", "x")
    st2 = D.choose(st, "room:7", "공학관 803")
    assert st2["room_pick"] == {"set:803": {"ids": [7]}} and st2["pending"] is None
    assert st2["asked"] is None and st2["utterances"] == ["u", "공학관 803"]

    st["pending"] = {
        "kind": "room",
        "key": "set:8층",
        "section": "set",
        "expr": "8층",
        "options": ["bld:3"],
    }
    assert D.choose(st, "bld:3", "공학관")["room_pick"] == {"set:8층": {"building": 3}}

    st["pending"] = {"kind": "pick", "options": ["pick:7:r17", "pick:7:r18"]}
    assert D.choose(st, "pick:7:r18", "x")["pick"] == {"7": "r18"}

    st["pending"] = {"kind": "type", "section": "set", "options": [c["id"] for c in D.TYPE_CHOICES]}
    assert D.choose(st, "type:특강", "특강")["set"]["type"] == "특강"

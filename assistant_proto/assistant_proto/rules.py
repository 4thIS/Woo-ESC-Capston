"""대화 규칙 — 작업별 꼭 필요한 칸 · 묻는 문구 · 상태 요약 칸 (spec §3.3·§3.4).

서버(server/app/assistant)가 대화를 진행할 때 쓰고, ml 이 학습용 '이어지는 대화' 접두어를 서버와
글자 하나 다르지 않게 만들 때 쓴다. 순수 함수 — DB 없음."""

from __future__ import annotations

from assistant_proto.form import FIELD_ORDER

# 이어지는 답(fill)의 칸이 기본으로 들어갈 묶음. 수정은 '새 값'(set)이 기본이다
PRIMARY: dict[str, str] = {
    "event.add": "set",
    "exam.add": "set",
    "class.add": "set",
    "event.change": "set",
    "exam.change": "set",
    "class.change": "set",
    "event.remove": "target",
    "exam.remove": "target",
    "class.remove": "target",
    "request.approve": "target",
    "request.reject": "target",
    "ask.free_rooms": "target",
    "ask.schedule": "target",
    "ask.requests": "target",
    "ask.node": "target",
}
# 미리보기를 띄운 뒤 서버가 다음 접두어에 넣는 질문 — ml 도 같은 글자로 접두어를 만든다
PREVIEW_QUESTION = "확인 화면을 보고 [적용]을 눌러 주세요. 바꿀 것이 있으면 말씀해 주세요."
# 같은 조건에 맞는 항목이 여럿이라 고르게 할 때 접두어 질문 (선택 버튼과 함께) — 서버·ml 공용
PICK_QUESTION = "어느 것인가요? 목록에서 골라 주시거나 날짜·시각·이름으로 알려 주세요."
CHANGE_INTENTS = ("event.change", "exam.change", "class.change")
_LABEL = {
    "rooms": "강의실",
    "time": "시각",
    "type": "유형",
    "professor": "교수",
    "reason": "사유",
    "requester": "신청자",
}


def _first(sec: str, d: dict, fields: tuple[str, ...]) -> str | None:
    for f in fields:
        if f not in d:
            return f"{sec}.{f}"
    return None


def missing(intent: str, target: dict, set_: dict) -> str | None:
    t, st = target, set_
    if intent == "event.add":
        if slot := _first("set", st, ("rooms", "when", "type")):
            return slot
        if st["type"] == "휴강":  # 시각·과목은 그날 정규 수업에서 찾는다(서버)
            return None
        return _first("set", st, ("time", "subject"))
    if intent in ("event.change", "event.remove", "class.change", "class.remove"):
        if slot := _first("target", t, ("rooms", "when")):
            return slot
        if not {"time", "subject", "type"} & t.keys():
            return "target.time"
        if intent in CHANGE_INTENTS and not st:
            return "set.any"
        return None
    if intent == "exam.add":
        return _first("set", st, ("rooms", "when"))
    if intent == "exam.change":
        return _first("target", t, ("rooms",)) or _first("set", st, ("when",))
    if intent == "exam.remove":
        return _first("target", t, ("rooms",))
    if intent == "class.add":
        return _first("set", st, ("rooms", "when", "time", "subject"))
    if intent == "ask.free_rooms":
        return _first("target", t, ("when",))
    if intent in ("ask.schedule", "ask.node"):
        return _first("target", t, ("rooms",))
    return None  # request.*, ask.requests — 조건이 없어도 목록에서 고른다


def question(intent: str, slot: str, type_label: str | None = None) -> str:
    grp = intent.split(".")[0]
    sec, f = slot.split(".")
    if f == "rooms":
        return "어느 강의실인가요? (예: 803, 공학관 803, 8층 전체)"
    if f == "when":
        if grp == "class":
            return "무슨 요일인가요? (예: 월, 화목)"
        if grp == "exam":
            return "시험기간은 언제부터 언제까지인가요? (예: 12/15~12/19)"
        if grp == "ask":
            return "언제 빈 강의실을 찾을까요? (예: 이번 주 금요일 오후)"
        if sec == "target":
            return "언제 일정인가요? (예: 이번 주 금요일, 12/3)"
        return "날짜는 언제인가요? (예: 12/3, 이번 주 금요일)"
    if f == "time":
        if sec == "target":
            if grp == "class":
                return "몇 시 수업인가요? 과목 이름으로 알려 주셔도 됩니다."
            return "몇 시 일정인가요? 과목·행사 이름으로 알려 주셔도 됩니다."
        return "몇 시부터 몇 시까지인가요? (예: 15시~18시)"
    if f == "type":
        return "어떤 일정인가요? 특강·대여·휴강·보강·시험 중에서 골라 주세요."
    if f == "subject":
        return (
            "과목명은 무엇인가요?"
            if grp == "class"
            else f"{type_label or '일정'} 이름은 무엇인가요?"
        )
    if f == "any":
        if sec == "target":  # 바꾸거나 지울 대상을 못 찾았을 때
            return "어떤 일정인가요? 날짜·시각·이름으로 다시 알려 주세요."
        return "무엇을 어떻게 바꿀까요? (예: 16시부터 18시까지로, 이름을 ○○로)"
    return "조금 더 자세히 알려 주세요."


def _label(intent: str, sec: str, f: str) -> str:
    grp = intent.split(".")[0]
    if f == "when":
        base = {"class": "요일", "exam": "기간"}.get(grp, "날짜")
    elif f == "subject":
        base = "과목" if grp == "class" else "이름"
    else:
        base = _LABEL[f]
    return f"대상 {base}" if sec == "target" and intent in CHANGE_INTENTS else base


def state_items(
    intent: str, target: dict, set_: dict, missing_slot: str | None = None
) -> list[tuple[str, str | None]]:
    """render_prefix 의 items — 채운 칸은 표현 그대로(rooms 는 ', ' 로 잇는다), 묻는 칸은 None('?')."""
    items: list[tuple[str, str | None]] = []
    for sec, d in (("target", target), ("set", set_)):
        for f in FIELD_ORDER:
            if f in d:
                v = d[f]
                items.append((_label(intent, sec, f), ", ".join(v) if f == "rooms" else v))
    if missing_slot:
        sec, f = missing_slot.split(".")
        d = target if sec == "target" else set_
        if f in FIELD_ORDER and f not in d:
            items.append((_label(intent, sec, f), None))
    return items

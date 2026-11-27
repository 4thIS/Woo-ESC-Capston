"""생성기 — 틀 × 가상 값 → Example. 정답 표현은 문장에 넣은 글자 그대로라 항상 맞다."""

from __future__ import annotations

import datetime as dt
import random
import re
from collections import Counter

from assistant_proto import FIRST_PREFIX, SCHEMA_VERSION, render_prefix, rules

from esc_ml.gen import values as V
from esc_ml.gen.templates import (
    FIELD_OF,
    FILL_TEMPLATES,
    MORE_TEMPLATES,
    PLACEHOLDER,
    TEMPLATES,
    Tpl,
)
from esc_ml.records import Example

KST = dt.timezone(dt.timedelta(hours=9))
VAL_SHARE = 0.06
DIALOG_SHARE = {"fill": 0.08, "cancel": 0.03, "unknown": 0.04}  # 합 15% (spec §8.2 10~15%)
MID_DIALOG_SHARE = 0.05  # 대화 중 전혀 다른 새 요청
MORE_SHARE = 0.15  # fill 중 "아 801도 같이"
TASK_INTENTS = tuple(sorted({t.intent for t in TEMPLATES} - {"cancel", "unknown"}))

# 서버(01 Task 9~10)가 실제로 되묻는 작업과 칸 — rules.missing 이 그 칸을 돌려주는 경우만 만든다.
# (섹션, 칸 목록). professor·request.* 는 서버가 묻지 않으므로 넣지 않는다.
FILL_BASE = {
    "event.add": ("set", ("rooms", "when", "type", "time", "subject")),
    "class.add": ("set", ("rooms", "when", "time", "subject")),
    "exam.add": ("set", ("rooms", "when")),
    "event.remove": ("target", ("rooms", "when", "time")),
    "class.remove": ("target", ("rooms", "when", "time")),
    "ask.free_rooms": ("target", ("when",)),
    "ask.schedule": ("target", ("rooms",)),
    "ask.node": ("target", ("rooms",)),
}
WHEN_KIND = {
    "exam.add": "range",
    "class.add": "days",
    "class.remove": "days",
}  # when 자리를 이 종류로 뽑는다


def _sample(rng: random.Random, kind: str, intent: str) -> tuple[str, object]:
    """(문장에 넣을 글자, 양식 값). rooms 만 값이 목록이다."""
    if kind == "rooms":
        k = 1 if rng.random() < 0.75 else rng.choice((2, 3))
        rooms: list[str] = []
        while len(rooms) < k:
            r = V.room_expr(rng)
            if r not in rooms:
                rooms.append(r)
        return rng.choice(V.JOINERS).join(rooms), rooms
    if kind == "group":
        g = V.group_expr(rng)
        return g, [g]
    if kind == "type":
        label = rng.choice(V.TYPE_LABELS_FOR_EVENTS)
        return rng.choice(V.TYPE_WORDS[label]), label
    if kind == "when":
        pool = V.DATE_LISTS if intent == "event.add" and rng.random() < 0.15 else V.DATES
    elif kind == "range":
        pool = V.RANGES
    elif kind == "days":
        pool = V.WEEKDAY_MULTI if intent == "class.add" and rng.random() < 0.2 else V.WEEKDAY_SINGLE
    elif kind == "time":
        pool = V.SPANS
    elif kind == "start":
        pool = V.STARTS
    elif kind == "subject":
        if intent.startswith("class.") or rng.random() < 0.5:
            v = rng.choice(V.SUBJECTS) + rng.choice(V.SECTIONS)
            return v, v
        pool = V.EVENTS
    else:
        pool = {"professor": V.PROFESSORS, "reason": V.REASONS, "requester": V.REQUESTERS}[kind]
    v = rng.choice(pool)
    return v, v


# 숫자 끝자리 읽기(영·일·이·삼·사·오·육·칠·팔·구)의 받침 — 0 은 십·백·천으로 읽어 받침이 있다
_DIGIT_JONG = {"0": 1, "1": 8, "2": 0, "3": 16, "4": 0, "5": 0, "6": 1, "7": 8, "8": 8, "9": 0}
_PARTICLE_AFTER = re.compile(r"(으로|로|이요|요)")


def _jong(text: str) -> int | None:
    """마지막 글자의 받침 번호(0 = 없음, 8 = ㄹ). 한글·숫자가 아니면 None."""
    c = text.rstrip()[-1:] if text.strip() else ""
    if "가" <= c <= "힣":
        return (ord(c) - 0xAC00) % 28
    return _DIGIT_JONG.get(c)


def fix_particle(word: str, particle: str) -> str:
    """'{값}로'·'{값}이요' 의 조사를 값의 끝소리에 맞춘다. 모르는 끝(영문 등)은 그대로."""
    j = _jong(word)
    if j is None:
        return particle
    if particle in ("으로", "로"):
        return "로" if j in (0, 8) else "으로"
    if particle in ("이요", "요"):
        return "요" if j == 0 else "이요"
    return particle


def fill_template(
    rng: random.Random,
    tpl: Tpl,
    kind_override: dict[str, str] | None = None,
    ctx_intent: str | None = None,
) -> tuple[str, dict]:
    form: dict = {"v": SCHEMA_VERSION, "intent": tpl.intent, "target": {}, "set": {}}
    intent_for_values = ctx_intent or tpl.intent

    def repl(m: re.Match[str]) -> str:
        side, name = m.group(1), m.group(2)
        kind = (kind_override or {}).get(name, name)
        text, value = _sample(rng, kind, intent_for_values)
        if side != "x":
            form["target" if side == "t" else "set"][FIELD_OF[name]] = value
        return text

    # 자리표시 바로 뒤 조사(로·으로·이요)는 채운 값의 끝소리에 맞춘다 — 값을 뽑는 순서(rng)는 그대로
    parts: list[str] = []
    pos = 0
    for m in PLACEHOLDER.finditer(tpl.text):
        parts.append(tpl.text[pos : m.start()])
        text = repl(m)
        parts.append(text)
        pos = m.end()
        after = _PARTICLE_AFTER.match(tpl.text, pos)
        if after:
            parts.append(fix_particle(text, after.group(1)))
            pos = after.end()
    parts.append(tpl.text[pos:])
    utterance = "".join(parts)
    if tpl.type_label is not None:
        form["set"]["type"] = tpl.type_label
    return utterance, form


def state_prefix(
    rng: random.Random, base: str | None = None, missing: str | None = None
) -> tuple[str, str, str]:
    """서버가 되물을 때 주는 접두어와 **같은 함수**로 만든다 — rules.state_items·rules.question
    (01 작업지시서 Task 3). 칸 값은 서버처럼 문장 속 표현 그대로. 반환 (접두어, 작업, 빠진 칸)."""
    base = base or rng.choice(sorted(FILL_BASE))
    sec, fields = FILL_BASE[base]
    missing = missing or rng.choice(fields)
    filled: dict = {}
    for f in fields:
        if f == missing:
            continue
        kind = WHEN_KIND.get(base, "when") if f == "when" else f
        filled[f] = _sample(rng, kind, base)[1]
    if filled.get("type") == "휴강" and missing in ("time", "subject"):
        filled["type"] = "특강"  # 휴강이면 서버가 시각·이름을 묻지 않는다(rules.missing)
    target, set_ = (filled, {}) if sec == "target" else ({}, filled)
    slot = f"{sec}.{missing}"
    assert rules.missing(base, target, set_) == slot, (base, slot)  # 서버가 실제로 묻는 칸만
    items = rules.state_items(base, target, set_, slot)
    question = rules.question(base, slot, set_.get("type"))
    return render_prefix(base, items, question), base, missing


def preview_prefix(rng: random.Random) -> str:
    """미리보기를 띄운 뒤의 접두어 — 모든 칸이 찬 상태 + rules.PREVIEW_QUESTION (서버와 같은 글자)."""
    base = rng.choice(sorted(FILL_BASE))
    sec, fields = FILL_BASE[base]
    filled = {}
    for f in fields:
        kind = WHEN_KIND.get(base, "when") if f == "when" else f
        filled[f] = _sample(rng, kind, base)[1]
    if filled.get("type") == "휴강":
        filled["type"] = "특강"
    target, set_ = (filled, {}) if sec == "target" else ({}, filled)
    return render_prefix(base, rules.state_items(base, target, set_), rules.PREVIEW_QUESTION)


def _fill(rng: random.Random, split: str) -> tuple[str, str, dict, str]:
    prefix, base, missing = state_prefix(rng)
    if rng.random() < MORE_SHARE:
        tpl = rng.choice([t for t in MORE_TEMPLATES if t.split == split])
    else:
        tpl = rng.choice([t for t in FILL_TEMPLATES[missing] if t.split == split])
    override = {"when": WHEN_KIND[base]} if base in WHEN_KIND else None
    utterance, form = fill_template(rng, tpl, override, ctx_intent=base)
    return prefix, utterance, form, tpl.id


def _now(rng: random.Random) -> str:
    d = dt.date(2026, 9, 1) + dt.timedelta(days=rng.randrange(110))
    t = dt.datetime(
        d.year, d.month, d.day, rng.randint(9, 17), rng.choice((0, 15, 30, 45)), tzinfo=KST
    )
    return t.isoformat()


def _pick_intent(rng: random.Random) -> str:
    r = rng.random()
    acc = 0.0
    for name, share in DIALOG_SHARE.items():
        acc += share
        if r < acc:
            return name
    return rng.choice(TASK_INTENTS)


def generate(n: int, seed: int) -> list[Example]:
    rng = random.Random(seed)
    n_val = round(n * VAL_SHARE)
    out: list[Example] = []
    for split, count in (("train", n - n_val), ("val", n_val)):
        for i in range(count):
            intent = _pick_intent(rng)
            if intent == "fill":
                prefix, utterance, form, tid = _fill(rng, split)
            else:
                tpl = rng.choice([t for t in TEMPLATES if t.intent == intent and t.split == split])
                utterance, form = fill_template(rng, tpl)
                mid = 0.8 if intent == "cancel" else MID_DIALOG_SHARE
                if rng.random() < mid:
                    prefix = preview_prefix(rng) if rng.random() < 0.4 else state_prefix(rng)[0]
                else:
                    prefix = FIRST_PREFIX
                tid = tpl.id
            out.append(
                Example(
                    id=f"g{seed}-{split[0]}{i:06d}",
                    split=split,
                    template=tid,
                    now=_now(rng),
                    prefix=prefix,
                    utterance=utterance,
                    form=form,
                )
            )
    return out


def intent_counts(rows: list[Example]) -> Counter:
    return Counter(r.form["intent"] for r in rows)

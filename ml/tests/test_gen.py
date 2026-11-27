from assistant_proto import FIRST_PREFIX, INTENTS, canonical_json, parse_form

from esc_ml.gen.build import generate
from esc_ml.gen.templates import FILL_TEMPLATES, MORE_TEMPLATES, PLACEHOLDER, TEMPLATES
from esc_ml.records import missing_spans

ROWS = generate(3000, seed=1)
ALL_TPLS = (*TEMPLATES, *MORE_TEMPLATES, *(t for ts in FILL_TEMPLATES.values() for t in ts))


def test_forms_follow_schema():
    for r in ROWS:
        parse_form(r.form)


def test_canonical_roundtrip():
    for r in ROWS[:300]:
        assert canonical_json(parse_form(canonical_json(r.form))) == canonical_json(r.form)


def test_spans_are_verbatim():
    bad = [
        (r.id, missing_spans(r.utterance, r.form))
        for r in ROWS
        if missing_spans(r.utterance, r.form)
    ]
    assert bad == []


def test_all_intents_covered():
    assert {r.form["intent"] for r in ROWS} == set(INTENTS)


def test_dialog_share():
    share = sum(r.form["intent"] in ("fill", "cancel", "unknown") for r in ROWS) / len(ROWS)
    assert 0.10 <= share <= 0.18


def test_val_templates_never_in_train():
    train = {r.template for r in ROWS if r.split == "train"}
    val = {r.template for r in ROWS if r.split == "val"}
    assert val and train.isdisjoint(val)
    assert all("/v" in t for t in val)


def test_deterministic():
    assert generate(50, seed=3) == generate(50, seed=3)
    assert generate(50, seed=3) != generate(50, seed=4)


def test_prefix_shape():
    for r in ROWS:
        assert r.prefix == FIRST_PREFIX or (
            r.prefix.startswith("상태: ") and r.prefix.endswith("관리자: ")
        )


def test_fill_prefix_matches_server_rules():
    # 이어지는 답의 접두어는 서버와 같은 rules 함수로 만든다 — 학습·운영 입력 모양이 같아야 한다
    import random

    from assistant_proto import rules

    from esc_ml.gen.build import FILL_BASE, state_prefix

    rng = random.Random(0)
    for base, (sec, fields) in FILL_BASE.items():
        for f in fields:
            prefix, _, missing = state_prefix(rng, base, f)
            q = prefix.split("\n")[1]
            assert missing == f
            assert q.startswith("질문: ")
            assert q.removeprefix("질문: ") in {
                rules.question(base, f"{sec}.{f}", t)
                for t in (None, "특강", "대여", "수업", "시험", "휴강", "빈강의실")
            }


def test_each_placeholder_once():
    for t in ALL_TPLS:
        names = PLACEHOLDER.findall(t.text)
        assert len(names) == len(set(names)), t.id


def test_every_intent_has_train_and_val_template():
    for intent in {t.intent for t in TEMPLATES}:
        splits = {t.split for t in TEMPLATES if t.intent == intent}
        assert splits == {"train", "val"}, intent
    for field, ts in FILL_TEMPLATES.items():
        assert {t.split for t in ts} == {"train", "val"}, field


def test_dialog_forms_shape():
    for r in ROWS:
        intent = r.form["intent"]
        if intent == "fill":
            assert r.form["target"] == {} and len(r.form["set"]) == 1
        if intent in ("cancel", "unknown"):
            assert r.form["target"] == {} and r.form["set"] == {}


def test_preview_prefix_uses_server_question():
    from assistant_proto import rules

    lines = [r.prefix.split("\n")[1] for r in ROWS if "\n" in r.prefix]
    assert f"질문: {rules.PREVIEW_QUESTION}" in lines


def test_particle_follows_final_consonant():
    """틀의 '{값}로'·'{값}이요' 는 값의 끝소리에 맞춘다 — '강수아으로'·'인공지능개론로' 같은 문장을 만들지 않는다."""
    from esc_ml.gen.build import fix_particle

    assert fix_particle("강수아", "으로") == "로"
    assert fix_particle("인공지능개론", "로") == "으로"
    assert fix_particle("16시", "으로") == "로"  # ㄹ 받침은 '로'
    assert fix_particle("803", "로") == "으로"  # 삼 — 받침
    assert fix_particle("12/15~19", "으로") == "로"  # 구
    assert fix_particle("810", "로") == "으로"  # 십
    assert fix_particle("801호", "으로") == "로"
    assert fix_particle("모레", "이요") == "요"
    assert fix_particle("금요일", "요") == "이요"


def test_generated_particles_are_correct():
    import re

    from esc_ml.gen.build import fix_particle, generate

    exs = generate(3000, 7)
    for ex in exs:
        for m in re.finditer(r"(\S+?)(으로|로)(?=\s|$)", ex.utterance):
            word, p = m.group(1), m.group(2)
            if word.endswith(("새", "시험기간", "기간")):
                continue
            assert fix_particle(word, p) == p, ex.utterance

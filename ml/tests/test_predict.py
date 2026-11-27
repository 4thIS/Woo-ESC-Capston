from assistant_proto import FIRST_PREFIX, SYSTEM_PROMPT, canonical_json

from esc_ml.predict_hf import build_messages, pick_fewshot
from esc_ml.records import Example


def ex(i, intent):
    form = {"v": 1, "intent": intent, "target": {}, "set": {}}
    return Example(
        i, "train", f"{intent}/01", "2026-11-25T10:00:00+09:00", FIRST_PREFIX, f"문장 {i}", form
    )


POOL = [
    ex(f"p{i}", intent)
    for i, intent in enumerate(["cancel", "unknown", "cancel", "ask.requests", "unknown"])
]


def test_build_messages_with_fewshot():
    msgs = build_messages(ex("t", "cancel"), POOL[:2])
    assert msgs[0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert [m["role"] for m in msgs[1:]] == ["user", "assistant", "user", "assistant", "user"]
    assert msgs[2]["content"] == canonical_json(POOL[0].form)
    assert msgs[-1]["content"] == FIRST_PREFIX + "문장 t"


def test_pick_fewshot_distinct_intents_and_deterministic():
    got = pick_fewshot(POOL, k=3, seed=1)
    assert len(got) == 3 and len({e.form["intent"] for e in got}) == 3
    assert got == pick_fewshot(POOL, k=3, seed=1)

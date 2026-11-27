from assistant_proto import FIRST_PREFIX, SYSTEM_PROMPT, canonical_json, json_schema

from esc_ml.agree import agreement
from esc_ml.records import Example, Prediction
from esc_ml.suite import build_suite

FORM = {"v": 1, "intent": "exam.remove", "target": {"rooms": ["801"]}, "set": {}}
EX = Example(
    "v-1", "test", "vector", "2026-11-25T10:00:00+09:00", FIRST_PREFIX, "801 시험기간 없애줘", FORM
)


def test_build_suite_shape():
    s = build_suite([EX], gbnf="root ::= x")
    assert s["system_prompt"] == SYSTEM_PROMPT and s["json_schema"] == json_schema()
    assert s["gbnf"] == "root ::= x"
    assert s["examples"] == [
        {"id": "v-1", "user": FIRST_PREFIX + "801 시험기간 없애줘", "gold": FORM}
    ]


def test_agreement_compares_parsed_forms():
    text = canonical_json(FORM)
    spaced = text.replace(",", ", ")
    a = {"x": Prediction("x", text), "y": Prediction("y", text), "z": Prediction("z", "깨짐")}
    b = {
        "x": Prediction("x", spaced),
        "y": Prediction("y", text.replace("801", "803")),
        "z": Prediction("z", "깨짐"),
    }
    same, total, diffs = agreement(a, b, ["x", "y", "z"])
    assert (same, total) == (1, 3) and diffs == ["y", "z"]

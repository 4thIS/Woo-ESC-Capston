from assistant_proto import FIRST_PREFIX, SYSTEM_PROMPT, canonical_json

from esc_ml.records import (
    Example,
    Prediction,
    load_vectors,
    missing_spans,
    read_examples,
    read_predictions,
    span_values,
    write_examples,
    write_predictions,
)

EX = Example(
    id="t1",
    split="train",
    template="event.add/01",
    now="2026-11-25T10:00:00+09:00",
    prefix=FIRST_PREFIX,
    utterance="803 금요일 15시부터 18시까지 특강 예약해줘",
    form={
        "v": 1,
        "intent": "event.add",
        "target": {},
        "set": {"rooms": ["803"], "when": "금요일", "time": "15시부터 18시까지", "type": "특강"},
    },
)


def test_examples_roundtrip(tmp_path):
    p = tmp_path / "a.jsonl"
    write_examples(p, [EX])
    assert read_examples(p) == [EX]


def test_messages_shape():
    msgs = EX.messages()
    assert [m["role"] for m in msgs] == ["system", "user", "assistant"]
    assert msgs[0]["content"] == SYSTEM_PROMPT
    assert msgs[1]["content"] == FIRST_PREFIX + EX.utterance
    assert msgs[2]["content"] == canonical_json(EX.form)


def test_span_values_and_missing():
    assert span_values(EX.form) == ["803", "금요일", "15시부터 18시까지"]
    assert missing_spans(EX.utterance, EX.form) == []
    bad = dict(EX.form, set={**EX.form["set"], "when": "목요일"})
    assert missing_spans(EX.utterance, bad) == ["목요일"]


def test_predictions_roundtrip_and_extra_keys(tmp_path):
    p = tmp_path / "p.jsonl"
    write_predictions(p, [Prediction("t1", '{"v":1}', 1200.0)])
    p.write_text(
        p.read_text(encoding="utf-8") + '{"id":"t2","text":"x","valid":false}\n', encoding="utf-8"
    )
    got = read_predictions(p)
    assert got["t1"] == Prediction("t1", '{"v":1}', 1200.0)
    assert got["t2"] == Prediction("t2", "x", None)


def test_load_vectors_defaults(tmp_path):
    p = tmp_path / "forms.v1.jsonl"
    p.write_text(
        '{"id": "a", "utterance": "801 시험기간 없애줘", '
        '"form": {"v": 1, "intent": "exam.remove", "target": {"rooms": ["801"]}, "set": {}}}\n',
        encoding="utf-8",
    )
    (ex,) = load_vectors(p)
    assert ex.id == "v-a" and ex.split == "test" and ex.template == "vector"
    assert ex.prefix == FIRST_PREFIX and ex.now.endswith("+09:00")

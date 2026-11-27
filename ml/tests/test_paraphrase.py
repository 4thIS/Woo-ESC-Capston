import json

from assistant_proto import FIRST_PREFIX

from esc_ml import paraphrase as P
from esc_ml.records import Example, read_examples, write_examples

EX = Example(
    id="g1-t000001",
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
EX_SUBJ = Example(
    id="g1-t000002",
    split="train",
    template="event.add/02",
    now="2026-11-25T10:00:00+09:00",
    prefix=FIRST_PREFIX,
    utterance="금요일 3시부터 6시에 803에서 알고리즘 특강 특강 잡아줘",
    form={
        "v": 1,
        "intent": "event.add",
        "target": {},
        "set": {
            "rooms": ["803"],
            "when": "금요일",
            "time": "3시부터 6시",
            "subject": "알고리즘 특강",
            "type": "특강",
        },
    },
)


def variant(text, **set_):
    empty = {k: None for k in P.SPAN_FIELDS}
    return {"text": text, "target": dict(empty), "set": {**empty, **set_}}


GOOD = variant(
    "803호 금요일 3시부터 6시 특강 잡아줘", rooms=["803호"], when="금요일", time="3시부터 6시"
)


def test_accepts_same_meaning():
    got = P.accept(EX, GOOD, idx=0)
    assert got is not None
    assert got.utterance == "803호 금요일 3시부터 6시 특강 잡아줘"
    assert got.form["set"]["time"] == "3시부터 6시" and got.form["set"]["rooms"] == ["803호"]
    assert got.form["set"]["type"] == "특강" and got.id == "g1-t000001-p0"
    assert got.template == "event.add/01+p"


def test_rejects_changed_time():
    v = variant("803 금요일 4시부터 6시 특강", rooms=["803"], when="금요일", time="4시부터 6시")
    assert P.accept(EX, v, idx=0) is None
    assert P.check(EX, v) == "value_changed"


def test_rejects_span_not_in_text():
    v = variant("803 금요일 오후 특강 잡아줘", rooms=["803"], when="금요일", time="3시부터 6시")
    assert P.accept(EX, v, idx=0) is None
    assert P.check(EX, v) == "span_not_in_text"


def test_rejects_new_field():
    v = variant(
        "803 금요일 3시부터 6시 김하늘 특강",
        rooms=["803"],
        when="금요일",
        time="3시부터 6시",
        professor="김하늘",
    )
    assert P.accept(EX, v, idx=0) is None
    assert P.check(EX, v) == "new_field"


def test_subject_spacing_ok_but_change_rejected():
    ok = variant(
        "금요일 3시부터 6시 803 알고리즘특강 잡아줘",
        rooms=["803"],
        when="금요일",
        time="3시부터 6시",
        subject="알고리즘특강",
    )
    assert P.accept(EX_SUBJ, ok, idx=1) is not None
    bad = variant(
        "금요일 3시부터 6시 803 AI 특강 잡아줘",
        rooms=["803"],
        when="금요일",
        time="3시부터 6시",
        subject="AI 특강",
    )
    assert P.accept(EX_SUBJ, bad, idx=1) is None


def test_check_other_reasons():
    assert P.check(EX, variant(EX.utterance, rooms=["803"])) == "same_text"
    assert P.check(EX, {"text": "x"}) == "malformed"
    dropped = variant("803 금요일 특강", rooms=["803"], when="금요일")
    assert P.check(EX, dropped) == "missing_field"
    assert P.check(EX, GOOD) is None


def test_same_value_rules():
    now = P.datetime.fromisoformat(EX.now)
    assert P.same_value("time", "3시부터 6시", "15시부터 18시까지", now, "event.add")
    assert not P.same_value("time", "3시부터 6시", "4시부터 6시", now, "event.add")
    assert P.same_value("rooms", ["803"], ["803호"], now, "event.add")
    assert P.same_value("subject", "알고리즘 특강", "알고리즘특강", now, "event.add")


def _jl(path, rows):
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )


def _many(n):
    return [
        Example(**{**EX.__dict__, "id": f"g1-t{i:06d}", "split": "train" if i % 2 == 0 else "val"})
        for i in range(n)
    ]


def test_export_batches_and_instructions(tmp_path):
    write_examples(tmp_path / "in.jsonl", _many(250))
    out = tmp_path / "req"
    code = P.main(
        ["export", "--in", str(tmp_path / "in.jsonl"), "--out", str(out)]
        + ["--batch", "100", "--limit", "230", "--variants", "3"]
    )
    assert code == 0
    files = sorted(p.name for p in out.glob("batch-*.jsonl"))
    assert files == ["batch-0001.jsonl", "batch-0002.jsonl", "batch-0003.jsonl"]
    rows = [json.loads(x) for x in (out / "batch-0003.jsonl").read_text("utf-8").splitlines()]
    assert len(rows) == 30
    assert set(rows[0]) == {"id", "utterance", "form", "k"} and rows[0]["k"] == 3
    text = (out / "INSTRUCTIONS.md").read_text("utf-8")
    assert "batch-0001.out.jsonl" in text and "가상" in text and "rooms" in text


def test_ingest_counts(tmp_path):
    write_examples(tmp_path / "in.jsonl", [EX, EX_SUBJ])
    d = tmp_path / "req"
    d.mkdir()
    bad = variant("803 금요일 4시부터 6시 특강", rooms=["803"], when="금요일", time="4시부터 6시")
    _jl(d / "batch-0001.out.jsonl", [{"id": EX.id, "variants": [GOOD, bad, GOOD]}])
    with (d / "batch-0002.out.jsonl").open("w", encoding="utf-8") as f:
        f.write("이건 깨진 줄\n")
        f.write(json.dumps({"id": "nope", "variants": [GOOD]}, ensure_ascii=False) + "\n")
        f.write(json.dumps({"id": EX_SUBJ.id, "variants": "x"}) + "\n")
    out = tmp_path / "o" / "train.jsonl"
    stats = P.ingest(tmp_path / "in.jsonl", d, out)
    assert stats.asked == 3 and stats.kept == 2
    assert stats.reasons == {"value_changed": 1}
    assert stats.broken == 2 and stats.unknown == 1
    got = read_examples(out)
    assert [g.id for g in got] == [f"{EX.id}-p0", f"{EX.id}-p2"]


def test_ingest_cli_prints_summary(tmp_path, capsys):
    write_examples(tmp_path / "in.jsonl", [EX])
    d = tmp_path / "req"
    d.mkdir()
    _jl(d / "batch-0001.out.jsonl", [{"id": EX.id, "variants": [GOOD]}])
    code = P.main(
        ["ingest", "--in", str(tmp_path / "in.jsonl"), "--variants-dir", str(d)]
        + ["--out", str(tmp_path / "o.jsonl")]
    )
    assert code == 0
    assert "변형 1개 중 1개 남김" in capsys.readouterr().out

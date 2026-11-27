import pytest
from assistant_proto import FIRST_PREFIX, render_prefix

from esc_ml.label import label_row, main, parse_items, parse_kv, row_prefix
from esc_ml.records import read_examples

ROW = {
    "id": "h001",
    "now": "2026-12-01 10:00",
    "ctx_intent": "",
    "ctx_items": "",
    "ctx_question": "",
    "utterance": "803호 이번주 금요일 3시부터 6시까지 세미나 잡아줘",
}


def scripted(answers):
    it = iter(answers)
    said = []
    return (lambda prompt: next(it)), said.append, said


def test_parse_kv():
    assert parse_kv("rooms=803, 801; when=이번 주 금요일; type=특강") == {
        "rooms": ["803", "801"],
        "when": "이번 주 금요일",
        "type": "특강",
    }
    assert parse_kv("  ") == {}
    with pytest.raises(ValueError):
        parse_kv("room=803")
    with pytest.raises(ValueError):
        parse_kv("rooms 803")


def test_parse_items_and_prefix():
    items = parse_items("강의실=803; 이름=?")
    assert items == [("강의실", "803"), ("이름", None)]
    row = dict(ROW, ctx_intent="event.add", ctx_items="강의실=803; 이름=?", ctx_question="이름은?")
    assert row_prefix(row) == render_prefix("event.add", items, "이름은?")
    assert row_prefix(ROW) == FIRST_PREFIX


def test_label_row_happy_path():
    ask, say, said = scripted(
        ["event.add", "", "rooms=803호; when=이번주 금요일; time=3시부터 6시까지; type=특강", "y"]
    )
    ex = label_row(ROW, ask, say)
    assert ex.id == "h-h001" and ex.split == "test" and ex.template == "human"
    assert ex.now == "2026-12-01T10:00:00+09:00"
    assert ex.form["set"]["rooms"] == ["803호"] and ex.form["set"]["type"] == "특강"
    assert any('"intent":"event.add"' in s for s in said)


def test_label_row_retries_on_bad_input():
    ask, say, said = scripted(["event.ad", "", "", "event.add", "", "rooms=803호; type=특강", "y"])
    ex = label_row(ROW, ask, say)
    assert ex.form["intent"] == "event.add"
    assert any(s.startswith("다시:") for s in said)


def test_label_row_warns_missing_span():
    ask, say, said = scripted(["event.add", "", "rooms=901", "y"])
    label_row(ROW, ask, say)
    assert any("문장에 그대로 없는 값" in s for s in said)


# ---- 라벨이 붙은 CSV (--labeled) ----

HEAD = "id,now,ctx_intent,ctx_items,ctx_question,utterance,writer,memo,intent,target,set"


def lrow(id_, utt, intent, target="", set_="", **kw):
    row = dict(ROW, id=id_, utterance=utt, intent=intent, target=target, set=set_)
    row.update(kw)
    return row


def write_csv(path, rows, bom=True):
    import csv

    cols = HEAD.split(",")
    with path.open("w", encoding="utf-8-sig" if bom else "utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})


GOOD = lrow("h001", ROW["utterance"], "event.add", "", "rooms=803호; when=이번주 금요일; type=특강")
FOLLOW = lrow(
    "h002",
    "알고리즘 특강이요",
    "event.add",
    "",
    "subject=알고리즘 특강",
    ctx_intent="event.add",
    ctx_items="강의실=803; 이름=?",
    ctx_question="특강 이름은 무엇인가요?",
)


def test_labeled_happy_path(tmp_path, capsys):
    c = tmp_path / "a.csv"
    out = tmp_path / "o" / "t.jsonl"
    write_csv(c, [GOOD, FOLLOW])
    assert main(["--labeled", "--csv", str(c), "--out", str(out)]) == 0
    exs = read_examples(out)
    assert [e.id for e in exs] == ["h-h001", "h-h002"]
    assert exs[0].prefix == FIRST_PREFIX and exs[0].form["set"]["type"] == "특강"
    assert exs[0].now == "2026-12-01T10:00:00+09:00"
    text = capsys.readouterr().out
    assert "시험 2문장" in text and "event.add" in text and "이어지는 턴 1" in text


def test_labeled_continuation_prefix(tmp_path):
    c = tmp_path / "a.csv"
    out = tmp_path / "t.jsonl"
    write_csv(c, [FOLLOW], bom=False)
    assert main(["--labeled", "--csv", str(c), "--out", str(out)]) == 0
    ex = read_examples(out)[0]
    assert ex.prefix == render_prefix(
        "event.add", [("강의실", "803"), ("이름", None)], "특강 이름은 무엇인가요?"
    )


def test_labeled_schema_violation_reported(tmp_path, capsys):
    c = tmp_path / "a.csv"
    out = tmp_path / "t.jsonl"
    write_csv(c, [GOOD, lrow("h003", "취소해줘 제발요", "event.ad")])
    assert main(["--labeled", "--csv", str(c), "--out", str(out)]) == 1
    assert "h003:" in capsys.readouterr().out
    assert not out.exists()


def test_labeled_span_mismatch_reported(tmp_path, capsys):
    c = tmp_path / "a.csv"
    out = tmp_path / "t.jsonl"
    write_csv(c, [lrow("h004", ROW["utterance"], "event.add", "", "rooms=901")])
    assert main(["--labeled", "--csv", str(c), "--out", str(out)]) == 1
    text = capsys.readouterr().out
    assert "h004:" in text and "901" in text


def test_labeled_duplicate_id_across_files(tmp_path, capsys):
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    out = tmp_path / "t.jsonl"
    write_csv(a, [GOOD])
    write_csv(b, [GOOD])
    assert main(["--labeled", "--csv", str(a), str(b), "--out", str(out)]) == 1
    assert "h001: id 중복" in capsys.readouterr().out


def test_labeled_bad_kv_and_now(tmp_path, capsys):
    c = tmp_path / "a.csv"
    write_csv(
        c,
        [
            lrow("h005", "x", "cancel", set_="room=803"),
            lrow("h006", "x", "cancel", now="어제"),
        ],
    )
    assert main(["--labeled", "--csv", str(c), "--out", str(tmp_path / "t.jsonl")]) == 1
    text = capsys.readouterr().out
    assert "h005:" in text and "h006:" in text

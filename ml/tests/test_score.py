from assistant_proto import FIRST_PREFIX, canonical_json

from esc_ml.records import Example, Prediction
from esc_ml.score import gate_results, render_report, score_one, summarize

NOW = "2026-11-25T10:00:00+09:00"


def ex(i, form):
    return Example(i, "test", "human", NOW, FIRST_PREFIX, "문장", form)


ADD = {
    "v": 1,
    "intent": "event.add",
    "target": {},
    "set": {"rooms": ["803"], "time": "15시부터 18시까지", "type": "특강"},
}


def pred(i, form_or_text, ms=None):
    text = form_or_text if isinstance(form_or_text, str) else canonical_json(form_or_text)
    return Prediction(i, text, ms)


def test_exact_match():
    r = score_one(ex("a", ADD), pred("a", ADD))
    assert r.format_ok and r.exact and r.fields_ok == r.fields_total == 3


def test_equivalent_expressions_count_as_correct():
    p = {**ADD, "set": {"rooms": ["803호"], "time": "3~6시", "type": "특강"}}
    r = score_one(ex("a", ADD), pred("a", p))
    assert r.exact and r.fields_ok == 3


def test_extra_field_breaks_exact():
    p = {**ADD, "set": {**ADD["set"], "professor": "김하늘"}}
    r = score_one(ex("a", ADD), pred("a", p))
    assert not r.exact and r.fields_total == 4 and r.fields_ok == 3


def test_format_error():
    for text in ("```json\n{}\n```", '{"v":1,"intent":"event.added","target":{},"set":{}}', ""):
        r = score_one(ex("a", ADD), pred("a", text))
        assert not r.format_ok and not r.exact and r.fields_ok == 0 and r.fields_total == 3


def test_missing_prediction_is_format_error():
    r = score_one(ex("a", ADD), None)
    assert not r.format_ok and r.error == "예측 없음"


def test_dangerous_and_summary():
    rm = {"v": 1, "intent": "event.remove", "target": {"rooms": ["803"]}, "set": {}}
    rows = [
        score_one(ex("a", ADD), pred("a", rm, 1000)),
        score_one(ex("b", ADD), pred("b", ADD, 3000)),
    ]
    s = summarize(rows)
    assert s.n == 2 and s.intent_acc == 0.5 and s.danger_rate == 0.5
    assert s.latency_mean_ms == 2000 and s.format_err == 0.0


def test_gates_pass_and_latency_na():
    rows = [score_one(ex(str(i), ADD), pred(str(i), ADD)) for i in range(10)]
    s = summarize(rows)
    gates = gate_results(s, grammar=True)
    assert all(g.passed for g in gates if g.passed is not None)
    lat = next(g for g in gates if g.name.startswith("응답 시간"))
    assert lat.passed is None
    lat_req = next(
        g
        for g in gate_results(s, grammar=True, require_latency=True)
        if g.name.startswith("응답 시간")
    )
    assert lat_req.passed is False


def test_report_renders():
    rows = [score_one(ex("a", ADD), pred("a", "깨진 출력"))]
    s = summarize(rows)
    md = render_report(
        "시험",
        s,
        rows,
        gate_results(s, grammar=False),
        {"a": ex("a", ADD)},
        {"a": pred("a", "깨진 출력")},
    )
    assert "# 시험" in md and "합격선" in md and "깨진 출력" in md and "event.add" in md

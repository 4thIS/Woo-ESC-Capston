import datetime as dt

from app.assistant import answers as A
from tests.assistant_util import ALL, NOW, building_admin, campus, resv


def _ans(app, intent, target):
    draft = {"intent": intent, "target": target, "set": {}, "pick": {}, "utterances": ["u"]}
    with app.state.Session() as s:
        return A.answer(s, ALL, draft, NOW)


def test_free_rooms_window(app, school):
    campus(app)
    a = _ans(app, "ask.free_rooms", {"dates": ["2026-11-27"], "time": ["15:00", "16:00"]})
    labels = [r[0] for r in a["rows"]]
    assert "공학관 803" not in labels  # 금 15:00–16:15 자료구조
    assert {"공학관 801", "인문관 803"} <= set(labels) and "타교관 803" not in labels
    assert a["columns"] == ["강의실", "빈 시간"]
    assert a["title"] == f"11/27(금) 15:00~16:00 빈 강의실 {len(a['rows'])}곳"


def test_free_rooms_limited_to_rooms(app, school):
    ids = campus(app)
    a = _ans(app, "ask.free_rooms", {"dates": ["2026-11-27"], "rooms": [ids["E803"]]})
    assert a["rows"] == [["공학관 803", "09:00–15:00, 16:15–21:00"]]


def test_schedule_defaults_to_this_week(app, school):
    ids = campus(app)
    resv(app, ids["E803"], dt.date(2026, 11, 26), (13, 0), (14, 0), id_=9, subject="세미나")
    a = _ans(app, "ask.schedule", {"rooms": [ids["E803"]]})
    assert a["rows"] == [
        ["공학관 803", "11/23(월)", "09:00–12:00", "수업", "알고리즘", "정규"],
        ["공학관 803", "11/26(목)", "13:00–14:00", "특강", "세미나", "승인"],
        ["공학관 803", "11/27(금)", "15:00–16:15", "수업", "자료구조", "정규"],
    ]
    assert a["title"] == "11/23(월)~11/29(일) 일정 3건"


def test_requests_list(app, school, students):
    ids = campus(app)
    resv(
        app,
        ids["E801"],
        dt.date(2026, 11, 26),
        (13, 0),
        (14, 0),
        id_=31,
        type_=6,
        subject="스터디",
        status="requested",
        requested_by="s1@mju.ac.kr",
    )
    a = _ans(app, "ask.requests", {})
    assert a["rows"] == [["공학관 801", "11/26(목)", "13:00–14:00", "학생1", "스터디"]]
    assert _ans(app, "ask.requests", {"rooms": [ids["E802"]]})["rows"] == []


def test_node_status(app, school):
    ids = campus(app)
    a = _ans(app, "ask.node", {"rooms": [ids["E803"]]})
    assert a["rows"] == [["공학관 803", "1", "-", "-", "-", "응답 없음"]]
    assert a["title"] == "노드 1대"


def test_building_admin_sees_only_own_buildings(app, school):
    ids = campus(app)
    building_admin(app, "ba@mju.ac.kr", [ids["H"]])
    from app.auth.scope import Scope

    sc = Scope(1, frozenset({ids["H"]}), "ba@mju.ac.kr")

    def ans(intent, target):
        draft = {"intent": intent, "target": target, "set": {}, "pick": {}, "utterances": ["u"]}
        with app.state.Session() as s:
            return A.answer(s, sc, draft, NOW)

    both = [ids["E803"], ids["H803"]]
    assert [r[0] for r in ans("ask.schedule", {"rooms": both})["rows"]] == []
    assert [r[0] for r in ans("ask.node", {"rooms": both})["rows"]] == ["인문관 803"]
    free = [r[0] for r in ans("ask.free_rooms", {"dates": ["2026-11-27"]})["rows"]]
    assert free and all(x.startswith("인문관") for x in free)

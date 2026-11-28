"""되묻기 선택 버튼 — 강의실을 못 찾거나 말하지 않았을 때 강의실 목록, 대상을 못 찾았을 때 그 강의실의 일정·수업 목록."""

import datetime as dt
import json

import pytest
from assistant_proto import parse_form

from app.assistant import changes
from app.assistant import dialog as D
from app.auth.scope import Scope
from tests.assistant_util import ALL, NOW, campus, resv

FRI = dt.date(2026, 11, 27)
SPECIAL = {"rooms": ["803"], "when": "이번주 금요일", "time": "15시부터 18시까지", "type": "특강"}
SCHOOL1 = [
    "공학관 301",
    "공학관 801",
    "공학관 802",
    "공학관 803",
    "공학관 805",
    "인문관 201",
    "인문관 803",
]


def st(intent, target=None, set_=None):
    return D.new_state({"intent": intent, "target": target or {}, "set": set_ or {}}, "u")


def adv(app, state, sc=ALL):
    with app.state.Session() as s:
        return D.advance(s, sc, state, NOW)


def test_unknown_room_lists_rooms_and_choice_resolves(app, school):
    ids = campus(app)
    d = adv(app, st("event.add", set_={**SPECIAL, "rooms": ["999"], "subject": "x"}))
    assert isinstance(d, D.Ask) and d.state["asked"] == "set.rooms"
    assert d.message.startswith("'999' 강의실을 찾지 못했습니다")
    assert "현재 있는 강의실" in d.message
    assert [c["label"] for c in d.choices] == SCHOOL1  # 다른 학교(타교관) 방은 없다
    assert d.choices[1] == {"id": f"room:{ids['E801']}", "label": "공학관 801"}
    st2 = D.choose(d.state, f"room:{ids['E801']}", "공학관 801")
    assert st2["set"]["rooms"] == ["공학관 801"]
    d2 = adv(app, st2)
    assert isinstance(d2, D.Ready) and d2.draft["set"]["rooms"] == [ids["E801"]]
    json.dumps(d2.state)


def test_room_not_given_lists_rooms(app, school):
    ids = campus(app)
    d = adv(app, st("class.add", set_={"when": "월", "time": "9시~12시", "subject": "자료구조"}))
    assert isinstance(d, D.Ask) and d.state["asked"] == "set.rooms"
    assert d.message.startswith(d.question) and "현재 있는 강의실" in d.message
    assert [c["label"] for c in d.choices] == SCHOOL1
    d2 = adv(app, D.choose(d.state, f"room:{ids['E802']}", "공학관 802"))
    assert isinstance(d2, D.Ready) and d2.draft["set"]["rooms"] == [ids["E802"]]


def test_room_list_respects_building_scope(app, school):
    ids = campus(app)
    sc = Scope(1, frozenset({ids["H"]}), "b@mju.ac.kr")
    d = adv(app, st("class.add", set_={"when": "월", "time": "9시~12시", "subject": "x"}), sc)
    assert [c["label"] for c in d.choices] == ["인문관 201", "인문관 803"]


def test_many_rooms_pick_building_first(app, school, monkeypatch):
    ids = campus(app)
    monkeypatch.setattr(D, "ROOM_LIST_MAX", 3)
    d = adv(app, st("event.add", set_={**SPECIAL, "rooms": ["999"], "subject": "x"}))
    assert d.choices == [
        {"id": f"bld:{ids['E']}", "label": "공학관 (5개)"},
        {"id": f"bld:{ids['H']}", "label": "인문관 (2개)"},
    ]
    assert "건물" in d.message
    d2 = adv(app, D.choose(d.state, f"bld:{ids['H']}", "인문관"))
    assert isinstance(d2, D.Ask) and d2.state["asked"] == "set.rooms"
    assert [c["label"] for c in d2.choices] == ["인문관 201", "인문관 803"]
    d3 = adv(app, D.choose(d2.state, f"room:{ids['H201']}", "인문관 201"))
    assert isinstance(d3, D.Ready) and d3.draft["set"]["rooms"] == [ids["H201"]]
    assert "room_menu" not in d3.state or not d3.state["room_menu"]


def test_typed_room_after_menu_still_works(app, school):
    ids = campus(app)
    d = adv(app, st("event.add", set_={**SPECIAL, "rooms": ["999"], "subject": "x"}))
    form = {"v": 1, "intent": "fill", "target": {}, "set": {"rooms": ["공학관 805"]}}
    st2, _ = D.absorb(d.state, parse_form(form), "공학관 805")
    d2 = adv(app, st2)
    assert isinstance(d2, D.Ready) and d2.draft["set"]["rooms"] == [ids["E805"]]


def test_event_not_found_lists_room_events_and_pick_targets_it(app, school):
    ids = campus(app)
    resv(app, ids["E803"], FRI, (17, 0), (18, 0), id_=21)
    resv(app, ids["E803"], dt.date(2026, 12, 30), (9, 0), (10, 0), id_=22)  # 2주 밖 — 목록에 없다
    d = adv(
        app,
        st(
            "event.remove",
            target={"rooms": ["공학관 803"], "when": "이번주 목요일", "type": "특강"},
        ),
    )
    assert isinstance(d, D.Ask) and d.state["asked"] == "target.any"
    assert d.message.startswith("말씀하신 일정을 찾지 못했습니다")
    assert d.choices == [
        {"id": f"fix:{ids['E803']}:r21", "label": "공학관 803 · 11/27(금) 17:00–18:00 특강 특강"}
    ]
    d2 = adv(app, D.choose(d.state, f"fix:{ids['E803']}:r21", "그거"))
    assert isinstance(d2, D.Ready)
    with app.state.Session() as s:
        cands = changes.find_candidates(s, ALL, d2.draft, NOW)
        assert [c["key"] for c in cands[ids["E803"]]] == ["r21"]
        b = changes.plan(s, ALL, d2.draft, NOW)
    assert b.ops and b.ops[0]["id"] == 21


def test_class_not_found_lists_room_classes(app, school):
    ids = campus(app)
    d = adv(
        app,
        st("class.remove", target={"rooms": ["공학관 803"], "when": "화", "subject": "운영체제"}),
    )
    assert isinstance(d, D.Ask) and d.message.startswith("말씀하신 정규 수업을 찾지 못했습니다")
    assert [c["label"] for c in d.choices] == [
        "공학관 803 · 월 09:00–12:00 알고리즘",
        "공학관 803 · 금 15:00–16:15 자료구조",
    ]
    key = d.choices[1]["id"]
    d2 = adv(app, D.choose(d.state, key, "자료구조"))
    assert isinstance(d2, D.Ready)
    with app.state.Session() as s:
        b = changes.plan(s, ALL, d2.draft, NOW)
    assert b.ops == [{"op": "slot.del", "room_id": ids["E803"], "day": 5, "s_h": 15, "s_m": 0}]


def test_not_found_in_empty_room_still_fails(app, school):
    campus(app)
    d = adv(
        app,
        st(
            "event.remove",
            target={"rooms": ["공학관 801"], "when": "이번주 금요일", "type": "특강"},
        ),
    )
    assert isinstance(d, D.Fail)


def test_typed_correction_after_fix_menu_drops_fix(app, school):
    ids = campus(app)
    resv(app, ids["E803"], FRI, (17, 0), (18, 0), id_=21)
    resv(app, ids["E803"], FRI, (19, 0), (20, 0), id_=23)
    d = adv(
        app,
        st(
            "event.remove",
            target={"rooms": ["공학관 803"], "when": "이번주 목요일", "type": "특강"},
        ),
    )
    st2 = D.choose(d.state, f"fix:{ids['E803']}:r21", "그거")
    form = {
        "v": 1,
        "intent": "fill",
        "target": {},
        "set": {"when": "이번주 금요일", "time": "19시"},
    }
    st3, _ = D.absorb(st2, parse_form(form), "아니 금요일 19시")
    assert not st3.get("fixed")


def test_stale_fix_choice_rejected(app, school):
    campus(app)
    d = adv(app, st("event.add", set_={"rooms": ["803"], "when": "금요일"}))
    with pytest.raises(D.NeedContext):
        D.choose(d.state, "fix:1:r1", "x")

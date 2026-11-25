import datetime as dt

from app.assistant import dialog as D
from tests.assistant_util import ALL, NOW, campus, resv

SPECIAL = {"rooms": ["803"], "when": "이번주 금요일", "time": "15시부터 18시까지", "type": "특강"}


def st(intent, target=None, set_=None):
    return D.new_state({"intent": intent, "target": target or {}, "set": set_ or {}}, "u")


def adv(app, state):
    with app.state.Session() as s:
        return D.advance(s, ALL, state, NOW)


def test_asks_missing_subject_first(app, school):
    campus(app)
    d = adv(app, st("event.add", set_=SPECIAL))
    assert isinstance(d, D.Ask) and d.question == "특강 이름은 무엇인가요?"
    assert d.state["asked"] == "set.subject" and d.choices == []


def test_type_question_offers_choices(app, school):
    campus(app)
    d = adv(app, st("event.add", set_={"rooms": ["803"], "when": "금요일"}))
    assert d.state["asked"] == "set.type" and d.choices[0] == {"id": "type:특강", "label": "특강"}
    assert d.state["pending"]["kind"] == "type"


def test_room_ambiguity_then_ready(app, school):
    ids = campus(app)
    d = adv(app, st("event.add", set_={**SPECIAL, "subject": "알고리즘 특강"}))
    assert isinstance(d, D.Ask)
    assert d.choices == [
        {"id": f"room:{ids['E803']}", "label": "공학관 803"},
        {"id": f"room:{ids['H803']}", "label": "인문관 803"},
    ]
    d2 = adv(app, D.choose(d.state, f"room:{ids['E803']}", "공학관 803"))
    assert isinstance(d2, D.Ready)
    assert d2.draft["set"] == {
        "rooms": [ids["E803"]],
        "dates": ["2026-11-27"],
        "time": ["15:00", "18:00"],
        "type": 5,
        "subject": "알고리즘 특강",
    }
    assert d2.draft["utterances"] == ["u", "공학관 803"]


def test_missing_room_reasks_and_drops_expr(app, school):
    campus(app)
    d = adv(app, st("event.add", set_={**SPECIAL, "rooms": ["999"], "subject": "x"}))
    assert isinstance(d, D.Ask) and d.question.startswith("'999' 강의실을 찾지 못했습니다")
    assert "rooms" not in d.state["set"] and d.state["asked"] == "set.rooms"


def test_bad_time_weekly_event_and_open_end(app, school):
    campus(app)
    base = {**SPECIAL, "rooms": ["공학관 803"], "subject": "x"}
    d = adv(app, st("event.add", set_={**base, "time": "몇 시"}))
    assert d.question == "시각을 '15시~18시'처럼 알려 주세요." and "time" not in d.state["set"]
    d = adv(app, st("event.add", set_={**base, "when": "매주 월"}))
    assert d.question == D.WEEKLY_HINT
    d = adv(app, st("event.add", set_={**base, "time": "15시"}))
    assert d.question.startswith("끝나는 시각도")


def test_holiday_fills_from_regular_class(app, school):
    ids = campus(app)
    d = adv(
        app,
        st(
            "event.add",
            set_={
                "rooms": ["공학관 803"],
                "when": "다음 주 월요일",
                "type": "휴강",
                "subject": "알고리즘",
            },
        ),
    )
    assert isinstance(d, D.Ready)
    assert d.draft["set"]["entries"] == [
        {
            "room_id": ids["E803"],
            "date": "2026-11-30",
            "start": "09:00",
            "end": "12:00",
            "subject": "알고리즘",
            "professor": "이",
        }
    ]


def test_whole_day_holiday_takes_every_class(app, school):
    campus(app)
    d = adv(
        app,
        st("event.add", set_={"rooms": ["공학관 803"], "when": "이번주 금요일", "type": "휴강"}),
    )
    assert [e["subject"] for e in d.draft["set"]["entries"]] == ["자료구조"]
    d = adv(
        app,
        st("event.add", set_={"rooms": ["공학관 801"], "when": "이번주 금요일", "type": "휴강"}),
    )
    assert isinstance(d, D.Ask) and d.state["asked"] == "set.time"  # 801 은 그날 수업이 없다


def test_change_with_two_candidates_asks_pick(app, school):
    ids = campus(app)
    resv(app, ids["E803"], dt.date(2026, 11, 27), (17, 0), (18, 0), id_=17)
    resv(app, ids["E803"], dt.date(2026, 11, 27), (19, 0), (20, 0), id_=18)
    state = st(
        "event.change",
        target={"rooms": ["공학관 803"], "when": "이번주 금요일", "type": "특강"},
        set_={"time": "16시"},
    )
    d = adv(app, state)
    assert isinstance(d, D.Ask)
    assert [c["id"] for c in d.choices] == [f"pick:{ids['E803']}:r17", f"pick:{ids['E803']}:r18"]
    assert d.choices[0]["label"] == "공학관 803 · 11/27(금) 17:00–18:00 특강 특강"
    d2 = adv(app, D.choose(d.state, f"pick:{ids['E803']}:r18", "19시 것"))
    assert isinstance(d2, D.Ready) and d2.draft["pick"] == {str(ids["E803"]): "r18"}


def test_change_not_found_fails(app, school):
    campus(app)
    d = adv(
        app,
        st(
            "event.remove",
            target={"rooms": ["공학관 803"], "when": "이번주 금요일", "type": "특강"},
        ),
    )
    assert isinstance(d, D.Fail) and d.message.startswith("말씀하신 일정을 찾지 못했습니다")


def test_ask_answer_and_request_lists(app, school, students):
    ids = campus(app)
    d = adv(app, st("ask.node", target={"rooms": ["공학관 803"]}))
    assert isinstance(d, D.Answer) and d.draft["target"]["rooms"] == [ids["E803"]]
    for id_, room, who in ((31, "E801", "s1@mju.ac.kr"), (32, "E802", "s2@mju.ac.kr")):
        resv(
            app,
            ids[room],
            dt.date(2026, 11, 26),
            (13, 0),
            (14, 0),
            id_=id_,
            type_=6,
            subject="스터디",
            status="requested",
            requested_by=who,
        )
    d = adv(app, st("request.approve"))
    assert isinstance(d, D.Ask) and [c["id"] for c in d.choices] == ["pick:0:q31", "pick:0:q32"]
    assert d.choices[0]["label"] == '공학관 801 11/26(목) 13:00–14:00 학생1 "스터디"'
    d = adv(app, st("request.approve", target={"requester": "학생1"}))
    assert isinstance(d, D.Ready)

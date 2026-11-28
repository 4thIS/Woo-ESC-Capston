import datetime as dt

from assistant_proto import rules

from app.assistant import changes
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
    assert isinstance(d, D.Ask) and d.message.startswith("'999' 강의실을 찾지 못했습니다")
    assert "rooms" not in d.state["set"] and d.state["asked"] == "set.rooms"


def test_bad_time_weekly_event_and_open_end(app, school):
    campus(app)
    base = {**SPECIAL, "rooms": ["공학관 803"], "subject": "x"}
    d = adv(app, st("event.add", set_={**base, "time": "몇 시"}))
    assert d.message == "시각을 '15시~18시'처럼 알려 주세요." and "time" not in d.state["set"]
    d = adv(app, st("event.add", set_={**base, "when": "매주 월"}))
    assert d.message == D.WEEKLY_HINT
    d = adv(app, st("event.add", set_={**base, "time": "15시"}))
    assert d.message.startswith("끝나는 시각도")


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
    assert (
        isinstance(d, D.Ask) and d.question == rules.PICK_QUESTION and d.message == "어느 것인가요?"
    )
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


# --- 검토 반영 ---------------------------------------------------------------
import json

import pytest

from app.auth.scope import Scope
from app.domain.models import ExamPeriod
from tests.assistant_util import UTC_NOW

FRI = dt.date(2026, 11, 27)
CH = {"rooms": ["공학관 803"], "when": "이번주 금요일", "type": "특강"}


def ok_json(d):
    """Ask/Ready 의 상태·초안이 JSON 으로 직렬화되는가."""
    json.dumps(d.state)
    if isinstance(d, D.Ready):
        json.dumps(d.draft)
    return d


def test_building_admin_scope_hides_other_building(app, school):
    ids = campus(app)
    sc = Scope(1, frozenset({ids["E"]}), "b@mju.ac.kr")
    resv(app, ids["H803"], FRI, (17, 0), (18, 0), id_=21)
    resv(app, ids["E803"], FRI, (17, 0), (18, 0), id_=22)
    with app.state.Session() as s:
        d = D.advance(s, sc, st("event.remove", target={**CH, "rooms": ["인문관 803"]}), NOW)
        assert isinstance(d, D.Ask) and d.state["asked"] == "target.rooms"
        assert "찾지 못했습니다" in d.message
        # '803' 은 범위 안의 공학관 803 하나로만 풀린다 — 인문관 예약은 후보가 아니다
        d = ok_json(D.advance(s, sc, st("event.remove", target={**CH, "rooms": ["803"]}), NOW))
        assert isinstance(d, D.Ready)
        from app.assistant import changes

        cands = changes.find_candidates(s, sc, d.draft, NOW)
        assert list(cands) == [ids["E803"]] and [c["key"] for c in cands[ids["E803"]]] == ["r22"]


@pytest.mark.parametrize("status", ["cancelled", "rejected", "expired", "requested"])
def test_not_approved_is_not_candidate(app, school, status):
    ids = campus(app)
    resv(app, ids["E803"], FRI, (17, 0), (18, 0), id_=23, status=status)
    d = adv(app, st("event.remove", target=CH))
    assert isinstance(d, D.Fail)


def test_other_day_or_room_not_matched(app, school):
    ids = campus(app)
    resv(app, ids["E803"], dt.date(2026, 11, 28), (17, 0), (18, 0), id_=24, subject="알고리즘 특강")
    resv(app, ids["E802"], FRI, (17, 0), (18, 0), id_=25, subject="알고리즘 특강")
    t = {**CH, "subject": "알고리즘 특강"}
    d = adv(app, st("event.remove", target=t))
    # 다른 날은 대상으로 잡지 않는다 — 못 찾았다며 그 강의실(803) 일정만 버튼으로 내놓는다(802 것은 없다)
    assert isinstance(d, D.Ask) and d.state["asked"] == "target.any"
    assert [c["id"] for c in d.choices] == [f"fix:{ids['E803']}:r24"]


def test_past_reservation_not_candidate(app, school):
    ids = campus(app)
    resv(app, ids["E803"], dt.date(2026, 11, 24), (17, 0), (18, 0), id_=26)
    t = {"rooms": ["공학관 803"], "when": "11/24", "type": "특강"}
    assert isinstance(adv(app, st("event.remove", target=t)), D.Fail)


def test_subject_matching_rules(app, school):
    ids = campus(app)
    resv(app, ids["E803"], FRI, (17, 0), (18, 0), id_=27, subject="알고리즘")
    with app.state.Session() as s:
        from app.assistant import changes

        assert changes.same_subject("알고리즘 수업", "알고리즘")
        assert changes.same_subject("알 고리즘", "알고리즘")
        assert changes.same_subject("수", "수")
        assert not changes.same_subject("수", "수학")
        assert not changes.same_subject("자료구조", "알고리즘")
        assert not changes.same_subject("", "알고리즘")
        _ = s
    t = {**CH, "subject": "알고리즘 특강"}
    assert isinstance(adv(app, st("event.remove", target=t)), D.Ready)


def test_student_reservation_targetable_and_labeled(app, school, students):
    ids = campus(app)
    for i, who in ((28, "s1@mju.ac.kr"), (29, None)):
        resv(
            app,
            ids["E803"],
            FRI,
            (17 + i - 28, 0),
            (18 + i - 28, 0),
            id_=i,
            type_=6,
            subject="스터디",
            requested_by=who,
        )
    t = {**CH, "type": "대여"}
    d = ok_json(adv(app, st("event.remove", target=t)))
    assert isinstance(d, D.Ask)
    assert d.choices[0]["label"].endswith("(학생 예약)")
    assert not d.choices[1]["label"].endswith("(학생 예약)")


def test_class_candidates_skip_empty_room_slots(app, school):
    ids = campus(app)
    from app.domain.models import Slot

    with app.state.Session() as s, s.begin():
        s.add(
            Slot(
                room_id=ids["E803"],
                day=1,
                s_h=13,
                s_m=0,
                e_h=14,
                e_m=0,
                type=4,
                subject="",
                professor="",
            )
        )
    d = adv(
        app,
        st("class.remove", target={"rooms": ["공학관 803"], "when": "월", "subject": "알고리즘"}),
    )
    assert isinstance(d, D.Ready)
    from app.assistant import changes

    with app.state.Session() as s:
        c = changes.find_candidates(s, ALL, d.draft, NOW)
    assert [x["key"] for x in c[ids["E803"]]] == ["d1-0900"]


def test_exam_remove_overlap_asks(app, school):
    ids = campus(app)
    with app.state.Session() as s, s.begin():
        s.add_all(
            [
                ExamPeriod(
                    id=1,
                    room_id=ids["E803"],
                    date_start=dt.date(2026, 11, 30),
                    date_end=dt.date(2026, 12, 4),
                ),
                ExamPeriod(
                    id=2,
                    room_id=ids["E803"],
                    date_start=dt.date(2026, 12, 2),
                    date_end=dt.date(2026, 12, 6),
                ),
            ]
        )
    d = ok_json(adv(app, st("exam.remove", target={"rooms": ["공학관 803"], "when": "12/1~12/5"})))
    assert isinstance(d, D.Ask)
    assert [c["id"] for c in d.choices] == [f"pick:{ids['E803']}:e1", f"pick:{ids['E803']}:e2"]


def test_stale_choice_rejected(app, school):
    campus(app)
    d = adv(app, st("event.add", set_={"rooms": ["803"], "when": "금요일"}))
    with pytest.raises(D.NeedContext):
        D.choose(d.state, "pick:1:r99", "x")
    with pytest.raises(D.NeedContext):
        D.choose(None, "type:특강", "x")


def test_states_serialize(app, school):
    ids = campus(app)
    d = ok_json(adv(app, st("event.add", set_=SPECIAL)))
    d = ok_json(adv(app, st("event.add", set_={**SPECIAL, "subject": "x"})))
    ok_json(adv(app, D.choose(d.state, f"room:{ids['E803']}", "공학관 803")))
    _ = UTC_NOW


def test_exam_candidates_skip_finished_periods(app, school):
    ids = campus(app)
    with app.state.Session() as s, s.begin():
        s.add_all(
            [
                ExamPeriod(
                    room_id=ids["E803"],
                    date_start=dt.date(2026, 11, 1),
                    date_end=dt.date(2026, 11, 5),
                ),
                ExamPeriod(
                    id=9,
                    room_id=ids["E803"],
                    date_start=dt.date(2026, 11, 30),
                    date_end=dt.date(2026, 12, 4),
                ),
            ]
        )
    d = ok_json(adv(app, st("exam.remove", target={"rooms": ["공학관 803"]})))
    assert isinstance(d, D.Ready)
    with app.state.Session() as s:
        c = changes.find_candidates(s, ALL, d.draft, NOW)
    assert [x["key"] for x in c[ids["E803"]]] == ["e9"]

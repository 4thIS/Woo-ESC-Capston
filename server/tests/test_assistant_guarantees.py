"""spec §13 — 모든 바꾸는 작업에서 (1) 미리보기는 아무것도 남기지 않고 (2) 적용 결과가 미리보기의 '바뀐 뒤'와 같다."""

import datetime as dt

import pytest
from sqlalchemy import func, select

from app.assistant import preview as P
from app.domain.models import ExamPeriod, Reservation, Slot
from app.lora_service.models import Outbox, RoomVersion
from tests.assistant_util import ALL, NOW, campus, fix_clock, resv


def _d(intent, target=None, set_=None):
    return {
        "intent": intent,
        "target": target or {},
        "set": set_ or {},
        "pick": {},
        "utterances": ["u"],
    }


CASES = {
    "event.add": lambda i: _d(
        "event.add",
        set_={
            "rooms": [i["E801"], i["E802"]],
            "dates": ["2026-11-27"],
            "time": ["10:00", "12:00"],
            "type": 6,
            "subject": "대관",
        },
    ),
    "event.add.holiday": lambda i: _d(
        "event.add",
        set_={
            "rooms": [i["E803"]],
            "dates": ["2026-11-30"],
            "type": 3,
            "entries": [
                {
                    "room_id": i["E803"],
                    "date": "2026-11-30",
                    "start": "09:00",
                    "end": "12:00",
                    "subject": "알고리즘",
                    "professor": "이",
                }
            ],
        },
    ),
    "event.change": lambda i: _d(
        "event.change",
        target={"rooms": [i["E803"]], "dates": ["2026-11-27"], "type": 5},
        set_={"time": ["19:00", None]},
    ),
    "event.remove": lambda i: _d(
        "event.remove", target={"rooms": [i["E803"]], "dates": ["2026-11-27"], "type": 5}
    ),
    "exam.add": lambda i: _d(
        "exam.add", set_={"rooms": [i["E801"]], "range": ["2026-12-14", "2026-12-18"]}
    ),
    "exam.change": lambda i: _d(
        "exam.change",
        target={"rooms": [i["E803"]]},
        set_={"range": ["2026-12-15", "2026-12-19"]},
    ),
    "exam.remove": lambda i: _d("exam.remove", target={"rooms": [i["E803"]]}),
    "class.add": lambda i: _d(
        "class.add",
        set_={
            "rooms": [i["E801"]],
            "weekdays": [2, 4],
            "time": ["09:00", "10:30"],
            "type": 1,
            "subject": "운영체제",
        },
    ),
    "class.change": lambda i: _d(
        "class.change",
        target={"rooms": [i["E803"]], "weekdays": [1], "subject": "알고리즘"},
        set_={"weekdays": [3], "time": ["13:00", None]},
    ),
    "class.remove": lambda i: _d(
        "class.remove", target={"rooms": [i["E803"]], "weekdays": [5], "subject": "자료구조"}
    ),
    "request.approve": lambda i: _d("request.approve", target={"requester": "학생1"}),
    "request.reject": lambda i: _d(
        "request.reject", target={"requester": "학생1"}, set_={"reason": "점검"}
    ),
}

_OLD_RESV = {17, 31}  # 미리 넣어 둔 예약 id
_OLD_EXAM = {5}


def _snap(app):
    """도메인 행 수 + outbox + room_versions 내용 — 미리보기 전후 비교용."""
    with app.state.Session() as s:
        counts = tuple(
            s.scalar(select(func.count()).select_from(m))
            for m in (Slot, Reservation, ExamPeriod, Outbox)
        )
        rv = tuple(sorted((r.bld, r.room, r.kind, r.ver) for r in s.scalars(select(RoomVersion))))
    return counts, rv


def _norm(w):
    """새 예약·시험기간 id 는 미리보기와 적용에서 다를 수 있다(`_free_id` 는 전역 채번) —
    새 행은 id 를 빼고 내용으로 비교하고, 기존 행(17·31·시험 5)은 id 까지 그대로 비교한다."""

    def fix(rows, old):
        return [x if x["id"] in old else {**x, "id": None} for x in rows]

    return {
        "slots": w["slots"],
        "reservations": fix(w["reservations"], _OLD_RESV),
        "exams": fix(w["exams"], _OLD_EXAM),
    }


@pytest.mark.parametrize("case", list(CASES))
def test_preview_leaves_nothing_and_equals_apply(client, app, students, monkeypatch, case):
    fix_clock(monkeypatch)
    ids = campus(app)
    resv(app, ids["E803"], dt.date(2026, 11, 27), (17, 0), (18, 0), id_=17)
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
    with app.state.Session() as s, s.begin():
        s.add(
            ExamPeriod(
                id=5,
                room_id=ids["E803"],
                date_start=dt.date(2026, 12, 14),
                date_end=dt.date(2026, 12, 18),
            )
        )
    before = _snap(app)
    pv = P.make_preview(app.state.Session, ALL, "c_t", CASES[case](ids), NOW)
    assert pv["blockers"] == [], pv["blockers"]
    assert _snap(app) == before  # (1) 미리보기는 흔적이 없다 (도메인·outbox·room_versions)
    assert any(w["changes"] for r in pv["rooms"] for w in r["weeks"]), case
    code, body = P.apply_preview(app.state.Session, ALL, pv["preview_id"], NOW)
    assert code == 200, body
    with app.state.Session() as s:  # (2) 적용 = 미리보기의 '바뀐 뒤'
        for room in pv["rooms"]:
            for w in room["weeks"]:
                got = P.week_data(s, room["room_id"], w["week_start"])
                assert _norm(got) == _norm(w["after"]), (case, room["label"], w["week_start"])

import datetime as dt
import json
import pathlib

import pytest

from app.domain import room_state as RS
from app.domain.models import Building, ExamPeriod, Reservation, Room, Slot
from app.domain.room_state import Span

M = lambda h, m=0: h * 60 + m
SLOTS = [
    Span(M(9), M(10, 50), 1, "수업"),
    Span(M(11), M(12), 3, "휴강"),
    Span(M(13), M(14), 5, "특강"),
    Span(M(15), M(16), 6, "대여"),
    Span(M(16), M(17), 2, "시험"),
]


VECTORS = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "room_state_vectors.json").read_text(
        encoding="utf-8"
    )
)


def _spans(xs):
    return [Span(x["s"], x["e"], x["type"], x.get("label", "")) for x in xs]


def _building(app, school_id, bld, rooms=((101, 1),)):
    with app.state.Session() as s, s.begin():
        b = Building(school_id=school_id, name=f"{bld}동", bld=bld)
        s.add(b)
        s.flush()
        ids = {}
        for room, units in rooms:
            r = Room(building_id=b.id, room=room, units=units)
            s.add(r)
            s.flush()
            ids[room] = r.id
        bid = b.id
    return bid, ids


def _slot(app, room_id, day, s_h, s_m, e_h, e_m, *, type=1, subject="수업", professor=""):
    with app.state.Session() as s, s.begin():
        s.add(
            Slot(
                room_id=room_id,
                day=day,
                s_h=s_h,
                s_m=s_m,
                e_h=e_h,
                e_m=e_m,
                type=type,
                subject=subject,
                professor=professor,
            )
        )


def _resv(
    app,
    room_id,
    date,
    s_h,
    s_m,
    e_h,
    e_m,
    *,
    id_,
    type=6,
    subject="예약",
    professor="",
    status="approved",
    requested_by=None,
):
    with app.state.Session() as s, s.begin():
        s.add(
            Reservation(
                id=id_,
                room_id=room_id,
                date=date,
                s_h=s_h,
                s_m=s_m,
                e_h=e_h,
                e_m=e_m,
                type=type,
                subject=subject,
                professor=professor,
                status=status,
                requested_by=requested_by,
            )
        )


def _exam(app, room_id, id_, date_start, date_end):
    with app.state.Session() as s, s.begin():
        s.add(ExamPeriod(id=id_, room_id=room_id, date_start=date_start, date_end=date_end))


@pytest.mark.parametrize("v", VECTORS["vectors"], ids=[v["name"] for v in VECTORS["vectors"]])
def test_room_state_vectors(v):
    if v.get("xfail"):
        pytest.xfail(v["xfail"])
    got = RS.room_state(_spans(VECTORS["slots"]), _spans(v["resvs"]), v["in_exam"], v["at"])
    assert got == (v["layout"], v["until"])


def test_room_state_exam_only_during_slots_and_resv_beats_exam():
    assert RS.room_state(SLOTS, [], True, M(12, 30)) == (4, M(13))  # 시험기간이라도 슬롯 밖은 빈
    assert RS.room_state(SLOTS, [Span(M(12), M(13), 6, "r")], True, M(12, 30)) == (7, M(13))
    assert RS.room_state([], [], False, M(10)) == (4, None)
    assert RS.room_state(SLOTS, [Span(M(10, 50), M(11, 30), 6, "r")], False, M(9, 55)) == (
        2,
        M(10),
    )  # 쉬는시간 → 정각 수업


def test_type_map_and_fmt():
    assert RS.TYPE_TO_LAYOUT == {1: 1, 2: 5, 3: 3, 4: 4, 5: 6, 6: 7} and RS.FREE == 4
    assert RS.fmt_hhmm(M(9, 5)) == "09:05" and RS.fmt_hhmm(None) is None


def test_load_inputs_and_state_of(app, school, students):
    _, ids = _building(app, 1, "E")
    rid = ids[101]
    _slot(app, rid, 3, 9, 0, 10, 50)  # 수요일
    _resv(
        app,
        rid,
        dt.date(2026, 9, 23),
        13,
        0,
        14,
        0,
        id_=1,
        requested_by="s1@mju.ac.kr",
        subject="스터디",
    )
    _resv(app, rid, dt.date(2026, 9, 23), 15, 0, 16, 0, id_=2, status="requested")  # 신청 중은 제외
    _exam(app, rid, 1, dt.date(2026, 9, 22), dt.date(2026, 9, 24))
    with app.state.Session() as s:
        slots, resvs, in_exam = RS.load_inputs(
            s, rid, dt.date(2026, 9, 23), viewer_email="s1@mju.ac.kr"
        )
        assert [(x.s, x.e, x.type) for x in slots] == [(M(9), M(10, 50), 1)]
        assert [(x.s, x.e, x.label, x.mine) for x in resvs] == [(M(13), M(14), "스터디", True)]
        assert in_exam is True
        assert (
            RS.load_inputs(s, rid, dt.date(2026, 9, 23), viewer_email="s2@mju.ac.kr")[1][0].label
            == "예약됨"
        )
        assert RS.state_of(s, rid, dt.datetime(2026, 9, 23, 9, 30)) == (5, M(10, 50))  # noqa: DTZ001
        assert RS.state_of(s, rid, dt.datetime(2026, 9, 25, 9, 30)) == (4, None)  # noqa: DTZ001

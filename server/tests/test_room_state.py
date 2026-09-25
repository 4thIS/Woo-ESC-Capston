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


def _vector_params():
    params = []
    for v in VECTORS["vectors"]:
        marks = [pytest.mark.xfail(strict=True, reason=v["xfail"])] if v.get("xfail") else []
        params.append(pytest.param(v, id=v["name"], marks=marks))
    return params


@pytest.mark.parametrize("v", _vector_params())
def test_room_state_vectors(v):
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


def test_midnight_never_returned_as_until():
    # 슬롯·예약이 자정에 정확히 끝나면 "24:00" 을 만들지 않고 None (자정 이후 변화 없음) 으로 정규화한다.
    assert RS.room_state([Span(M(23), RS.DAY_MIN, 6, "x")], [], False, M(23, 30)) == (7, None)
    assert RS.room_state([], [Span(M(23), RS.DAY_MIN, 6, "x")], False, M(23, 30)) == (7, None)


def test_week_busy_reservation_query_orders_by_id(app, school, students):
    """id 로 정렬해야 동률 구간의 머리(먼저 나온 것)가 폴마다 안 바뀐다 — 정렬이 없으면 DB 의 스캔
    순서(인덱스 선택 등)에 맡겨져 달라질 수 있다. 실행된 SQL 에 ORDER BY 가 있는지로 직접 확인한다."""
    from sqlalchemy import event

    _, ids = _building(app, 1, "E")
    rid = ids[101]
    seen = []

    def _capture(conn, cursor, statement, parameters, context, executemany):
        seen.append(statement)

    with app.state.Session() as s:
        event.listen(s.bind, "before_cursor_execute", _capture)
        try:
            RS.week_busy(s, rid, dt.date(2026, 9, 21), "s1@mju.ac.kr")
        finally:
            event.remove(s.bind, "before_cursor_execute", _capture)
    resv_sql = next(sql for sql in seen if "reservations" in sql and "SELECT" in sql)
    assert "ORDER BY reservations.id" in resv_sql


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


def test_merge_busy_chains_overlaps_but_keeps_touching_apart():
    out = RS.merge_busy(
        [
            Span(M(11), M(13), 6, "동아리 대관"),
            Span(M(10), M(12), 1, "알고리즘"),
            Span(M(12, 30), M(14), 6, "예약됨", mine=True),
            Span(M(14), M(15), 1, "운영체제"),  # 14:00 에 맞닿기만 — 따로 둔다
            Span(M(16), M(15), 1, "뒤집힘"),  # 관리자 입력엔 시작<끝 검증이 없다 — 버린다
        ]
    )
    assert [(x.s, x.e, x.type, x.label, x.mine) for x in out] == [
        (M(10), M(14), 1, "알고리즘 외 2건", True),
        (M(14), M(15), 1, "운영체제", False),
    ]
    same = RS.merge_busy([Span(M(9), M(10), 6, "짧은"), Span(M(9), M(11), 1, "긴")])
    assert [(x.label, x.e) for x in same] == [("긴 외 1건", M(11))]  # 같은 시작이면 긴 것이 머리
    mixed = RS.merge_busy(
        [Span(M(9), M(11), 1, "수업"), Span(M(10), M(12), 6, "스터디", True, status="requested")]
    )
    assert [(x.label, x.mine, x.status) for x in mixed] == [("수업 외 1건", True, "requested")]
    assert RS.merge_busy([]) == []


def test_merge_busy_type_flips_to_in_use_when_head_is_cancelled_or_free_slot():
    # 휴강(3) 슬롯 + 관리자 예약(6) 겹침 — 라벨은 머리(휴강)지만 type 은 실사용중(6)이어야 한다
    out = RS.merge_busy([Span(M(10), M(12), 3, "휴강"), Span(M(10), M(12), 6, "대여")])
    assert [(x.label, x.type) for x in out] == [("휴강 외 1건", 6)]
    # 시험기간 슬롯(2, 이미 실사용) 위 예약은 그대로 2 유지
    out2 = RS.merge_busy([Span(M(10), M(11), 2, "시험"), Span(M(10), M(11), 6, "대여")])
    assert [(x.label, x.type) for x in out2] == [("시험 외 1건", 2)]

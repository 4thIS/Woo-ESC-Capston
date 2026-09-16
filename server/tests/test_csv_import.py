import pytest

from app.domain import csv_import as CI
from app.domain.models import Building, Room, School, Slot
from app.lora_service.models import Modem

HEADER = "school,building,room,day,start,end,type,subject,professor\n"


@pytest.fixture
def seeded(app):
    """명지 E동 301(units=2)·302(units=1). 301 에 수동 슬롯 월 09:00, 긴급 슬롯 화 09:00."""
    with app.state.Session() as s, s.begin():
        s.add(Modem(modem_id="mjc-eng", token_hash="x"))
        sch = School(name="명지", net_id=0x4B)
        s.add(sch)
        s.flush()
        b = Building(school_id=sch.id, name="공학관", bld="E", modem_id="mjc-eng")
        s.add(b)
        s.flush()
        r1 = Room(building_id=b.id, room=301, units=2)
        r2 = Room(building_id=b.id, room=302, units=1)
        s.add_all([r1, r2])
        s.flush()
        s.add(
            Slot(
                room_id=r1.id,
                day=1,
                s_h=9,
                s_m=0,
                e_h=10,
                e_m=0,
                type=1,
                subject="수동",
                professor="",
                source=2,
            )
        )
        s.add(
            Slot(
                room_id=r1.id,
                day=2,
                s_h=9,
                s_m=0,
                e_h=10,
                e_m=0,
                type=3,
                subject="휴강",
                professor="",
                source=3,
            )
        )
        ids = (r1.id, r2.id)
    return ids


def _parse(app, text):
    with app.state.Session() as s:
        return CI.parse(text, s)


def test_parse_ok_both_notations(app, seeded):
    r1, r2 = seeded
    text = HEADER + (
        "명지,E,301,수,09:00,10:30,수업,자료구조,김\n"
        " 명지 , E , 302 , 3 , 9:00 , 10:30 , 1 , 자료구조 , 김 \n"
        "\n"
        "명지,E,302,일,13:00,14:50,대여,,\n"
    )
    rows, errors = _parse(app, text)
    assert errors == []
    assert [
        (r.row, r.room_id, r.day, r.s_h, r.s_m, r.e_h, r.e_m, r.type, r.subject, r.professor)
        for r in rows
    ] == [
        (2, r1, 3, 9, 0, 10, 30, 1, "자료구조", "김"),
        (3, r2, 3, 9, 0, 10, 30, 1, "자료구조", "김"),
        (5, r2, 7, 13, 0, 14, 50, 6, "", ""),
    ]
    assert rows[0].bld == "E" and rows[0].room == 301


def test_parse_bom_and_header_case_order(app, seeded):
    text = "﻿Professor, Subject ,TYPE,end,start,day,room,building,school\n김,자료구조,수업,10:30,09:00,월,302,E,명지\n"
    rows, errors = _parse(app, text)
    assert errors == [] and rows[0].day == 1 and rows[0].subject == "자료구조"


def test_parse_missing_header_is_row0(app, seeded):
    rows, errors = _parse(
        app, "school,building,room,day,start,end,type,subject\n명지,E,301,월,09:00,10:00,1,a\n"
    )
    assert rows == [] and errors == [CI.RowError(0, "헤더에 없는 컬럼: professor")]


@pytest.mark.parametrize(
    "line,msg",
    [
        ("서울대,E,301,월,09:00,10:00,1,a,", "school: '서울대' 없음"),
        ("명지,Z,301,월,09:00,10:00,1,a,", "building: 'Z' 없음 (명지)"),
        ("명지,E,999,월,09:00,10:00,1,a,", "room: 999 없음 (명지 E)"),
        ("명지,E,abc,월,09:00,10:00,1,a,", "room: 'abc' 은 1~9999"),
        ("명지,E,301,월요일,09:00,10:00,1,a,", "day: '월요일' 은 월~일 또는 1~7"),
        ("명지,E,301,8,09:00,10:00,1,a,", "day: '8' 은 월~일 또는 1~7"),
        ("명지,E,301,월,9시,10:00,1,a,", "start: '9시' 은 HH:MM"),
        ("명지,E,301,월,09:00,24:00,1,a,", "end: '24:00' 은 HH:MM"),
        ("명지,E,301,월,10:00,09:00,1,a,", "end 09:00 ≤ start 10:00"),
        ("명지,E,301,월,09:00,09:00,1,a,", "end 09:00 ≤ start 09:00"),
        ("명지,E,301,월,09:00,10:00,실습,a,", "type: '실습' 은 수업~대여 또는 1~6"),
        ("명지,E,301,월,09:00,10:00,7,a,", "type: '7' 은 수업~대여 또는 1~6"),
        ("명지,E,301,월,09:00,10:00,1,가나다라마바사,", "subject 21 B > 20 B (UTF-8)"),
        ("명지,E,301,월,09:00,10:00,1,a,가나다라마", "professor 15 B > 12 B (UTF-8)"),
    ],
)
def test_parse_row_errors(app, seeded, line, msg):
    _rows, errors = _parse(app, HEADER + line + "\n")
    assert errors == [CI.RowError(2, msg)]


def test_parse_collects_all_errors_up_to_100(app, seeded):
    text = HEADER + "".join("명지,E,301,9,09:00,10:00,1,a,\n" for _ in range(150))
    _rows, errors = _parse(app, text)
    assert len(errors) == 100 and errors[0].row == 2 and errors[-1].row == 101


def test_parse_duplicate_key_in_file(app, seeded):
    text = (
        HEADER
        + "명지,E,301,월,09:00,10:00,1,a,\n명지,E,302,월,09:00,10:00,1,a,\n명지,E,301,1,9:00,11:00,2,b,\n"
    )
    _rows, errors = _parse(app, text)
    assert errors == [CI.RowError(4, "row 2 와 중복 (301 월 09:00)")]


def test_parse_node_slot_cap_counts_surviving_higher_source(app, seeded):
    # 301 에 source≥2 슬롯 2개(월 09:00, 화 09:00). 포털 47행(월 09:00 겹침 1 포함) →
    # 겹치는 1행은 skip 이라 46 + 2 = 48 → OK. 48행이면 47 + 2 = 49 → 오류.
    def lines(n):
        out = ["명지,E,301,월,09:00,10:00,1,a,"]  # 겹침
        h = 10
        d = 1
        while len(out) < n:
            out.append(f"명지,E,301,{d},{h:02d}:00,{h:02d}:30,1,a,")
            h += 1
            if h == 23:
                h, d = 10, d + 1
        return "".join(x + "\n" for x in out)

    assert _parse(app, HEADER + lines(47))[1] == []
    _rows, errors = _parse(app, HEADER + lines(48))
    assert errors == [CI.RowError(0, "301: 슬롯 49 개 > 48 (노드 상한)")]

import json

import pytest
from sqlalchemy import select

from app.domain import csv_import as CI
from app.domain.models import Building, Room, Slot
from app.lora_service.models import Modem, Outbox, RoomVersion

HEADER = "school,building,room,day,start,end,type,subject,professor\n"


@pytest.fixture
def seeded(app, school):
    """명지 E동 301(units=2)·302(units=1). 301 에 수동 슬롯 월 09:00, 긴급 슬롯 화 09:00."""
    with app.state.Session() as s, s.begin():
        s.add(Modem(modem_id="mjc-eng", token_hash="x"))
        s.flush()  # buildings.modem_id FK — 부모 먼저
        b = Building(school_id=school, name="공학관", bld="E", modem_id="mjc-eng")
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


def _slots(app, rid):
    with app.state.Session() as s:
        return [
            (x.day, x.s_h, x.s_m, x.subject, x.source)
            for x in s.scalars(select(Slot).where(Slot.room_id == rid).order_by(Slot.day, Slot.s_h))
        ]


def test_apply_replaces_portal_keeps_higher_source(app, seeded):
    r1, r2 = seeded
    with app.state.Session() as s, s.begin():
        s.add(
            Slot(
                room_id=r1,
                day=3,
                s_h=9,
                s_m=0,
                e_h=10,
                e_m=0,
                type=1,
                subject="옛포털",
                professor="",
                source=1,
            )
        )
        s.add(
            Slot(
                room_id=r1,
                day=4,
                s_h=9,
                s_m=0,
                e_h=10,
                e_m=0,
                type=1,
                subject="유지될포털",
                professor="",
                source=1,
            )
        )
        s.add(
            Slot(
                room_id=r2,
                day=1,
                s_h=9,
                s_m=0,
                e_h=10,
                e_m=0,
                type=1,
                subject="302포털",
                professor="",
                source=1,
            )
        )
    # 월: 수동(source 2) 과 겹침 → skipped / 화: 긴급(source 3) 과 겹침 → skipped
    # 목: 기존 포털 갱신 / 금: 삽입 / 수 09:00 옛포털 → 삭제 / 302 는 파일에 없음 → 불변
    text = HEADER + (
        "명지,E,301,월,09:00,10:00,수업,포털월,\n"
        "명지,E,301,화,09:00,10:00,수업,포털화,\n"
        "명지,E,301,목,09:00,10:00,수업,갱신됨,\n"
        "명지,E,301,금,09:00,10:00,수업,새로,\n"
    )
    with app.state.Session() as s, s.begin():
        rows, errors = CI.parse(text, s)
        assert errors == []
        summary = CI.apply(rows, s)
    assert (summary.rooms, summary.added, summary.updated, summary.deleted) == (1, 1, 1, 1)
    assert summary.skipped == [
        {"row": 2, "reason": "수동 슬롯 있음 (source=2)"},
        {"row": 3, "reason": "긴급 슬롯 있음 (source=3)"},
    ]
    assert summary.changed == [("E", 301)]
    assert _slots(app, r1) == [
        (1, 9, 0, "수동", 2),
        (2, 9, 0, "휴강", 3),
        (4, 9, 0, "갱신됨", 1),
        (5, 9, 0, "새로", 1),
    ]
    assert _slots(app, r2) == [(1, 9, 0, "302포털", 1)]


def test_apply_same_file_twice_counts_updated_and_still_changed(app, seeded):
    _r1, r2 = seeded
    text = HEADER + "명지,E,302,월,09:00,10:00,수업,a,\n"
    for expect in ((1, 0), (0, 1)):  # (added, updated)
        with app.state.Session() as s, s.begin():
            rows, _ = CI.parse(text, s)
            sm = CI.apply(rows, s)
        assert (sm.added, sm.updated, sm.deleted) == (*expect, 0) and sm.changed == [("E", 302)]
    assert _slots(app, r2) == [(1, 9, 0, "a", 1)]


def test_apply_no_change_room_not_in_changed(app, seeded):
    # 302 의 유일한 행이 수동 슬롯과 겹쳐 skipped → 변경 0 → changed 에 없음, rooms 0
    _r1, r2 = seeded
    with app.state.Session() as s, s.begin():
        s.add(
            Slot(
                room_id=r2,
                day=1,
                s_h=9,
                s_m=0,
                e_h=10,
                e_m=0,
                type=1,
                subject="수동302",
                professor="",
                source=2,
            )
        )
    text = HEADER + "명지,E,302,월,09:00,10:00,수업,a,\n"
    with app.state.Session() as s, s.begin():
        rows, _ = CI.parse(text, s)
        sm = CI.apply(rows, s)
    assert sm.rooms == 0 and sm.changed == [] and len(sm.skipped) == 1


def test_apply_dry_run_writes_nothing(app, seeded):
    r1, _r2 = seeded
    text = HEADER + "명지,E,301,금,09:00,10:00,수업,새로,\n"
    with app.state.Session() as s, s.begin():
        rows, _ = CI.parse(text, s)
        sm = CI.apply(rows, s, dry_run=True)
    assert sm.added == 1 and sm.changed == [("E", 301)]
    assert _slots(app, r1) == [(1, 9, 0, "수동", 2), (2, 9, 0, "휴강", 3)]


def _post(client, text, **params):
    return client.post(
        "/api/import/slots",
        params=params,
        content=text.encode("utf-8"),
        headers={"content-type": "text/csv; charset=utf-8"},
    )


def _outbox(app):
    with app.state.Session() as s:
        return s.scalars(select(Outbox).order_by(Outbox.id)).all()


def test_import_400_leaves_db_and_outbox_untouched(client, app, seeded):
    r1, _ = seeded
    text = HEADER + "명지,E,301,금,09:00,10:00,수업,새로,\n명지,E,301,토,25:00,10:00,수업,x,\n"
    res = _post(client, text)
    assert res.status_code == 400
    assert res.json() == {"errors": [{"row": 3, "error": "start: '25:00' 은 HH:MM"}]}
    assert len(_slots(app, r1)) == 2 and _outbox(app) == []


def test_import_200_creates_file_per_unit_and_bumps_ver(client, app, seeded):
    _r1, _r2 = seeded
    # 월(301): 수동과 겹침 → skipped
    text = HEADER + (
        "명지,E,301,월,09:00,10:00,수업,포털월,\n"
        "명지,E,301,금,09:00,10:00,수업,새로,\n"
        "명지,E,302,월,09:00,10:00,수업,302,\n"
    )
    res = _post(client, text)
    assert res.status_code == 200, res.text
    body = res.json()
    assert (body["rooms"], body["added"], body["updated"], body["deleted"]) == (2, 2, 0, 0)
    assert body["skipped"] == [{"row": 2, "reason": "수동 슬롯 있음 (source=2)"}]
    rows = _outbox(app)
    assert [x.id for x in rows] == body["outbox_ids"] and len(rows) == 3  # 301 유닛 2 + 302 유닛 1
    assert all(x.type == "FILE" and x.new_ver == 1 for x in rows)
    recs = json.loads(rows[0].payload)["records"]
    assert [r["subject"] for r in recs] == ["수동", "휴강", "새로"]  # 커밋된 DB 를 읽음
    with app.state.Session() as s:
        assert s.get(RoomVersion, ("E", 301, "schedule")).ver == 1
    # 재업로드: updated, ver 2, FILE 다시
    res = _post(client, text)
    assert res.json()["updated"] == 2 and res.json()["rooms"] == 2
    assert _outbox(app)[-1].new_ver == 2


def test_import_dry_run_changes_nothing(client, app, seeded):
    r1, _ = seeded
    res = _post(client, HEADER + "명지,E,301,금,09:00,10:00,수업,새로,\n", dry_run="true")
    assert res.status_code == 200 and res.json()["added"] == 1 and res.json()["outbox_ids"] == []
    assert len(_slots(app, r1)) == 2 and _outbox(app) == []


def test_import_rejects_non_utf8_and_too_large(client, seeded):
    res = client.post(
        "/api/import/slots",
        content=(HEADER + "명지,E,301,월,09:00,10:00,1,a,\n").encode("cp949"),
        headers={"content-type": "text/csv"},
    )
    assert res.status_code == 400 and "UTF-8" in res.json()["detail"]
    res = client.post(
        "/api/import/slots", content=b"x" * (1024 * 1024 + 1), headers={"content-type": "text/csv"}
    )
    assert res.status_code == 413


def test_import_enqueue_failure_after_commit_returns_500_with_hint(
    client, app, seeded, monkeypatch
):
    from app.lora_service import api

    def boom(*a, **k):
        raise RuntimeError("hub down")

    monkeypatch.setattr(api, "enqueue_file_replace", boom)
    r1, _ = seeded
    res = _post(client, HEADER + "명지,E,301,금,09:00,10:00,수업,새로,\n")
    assert res.status_code == 500
    assert "sync" in res.json()["detail"]
    assert "E301" in res.json()["detail"]
    assert len(_slots(app, r1)) == 3  # DB 는 반영됨

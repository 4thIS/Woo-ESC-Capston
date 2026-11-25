import datetime as dt
import json

from sqlalchemy import func, select

from app.assistant import preview as P
from app.assistant.models import AssistantPreview
from app.domain.models import ExamPeriod, Reservation, Slot
from app.lora_service.models import Outbox
from tests.assistant_util import ALL, NOW, UTC_NOW, campus, fix_clock, resv


def _draft(intent, target=None, set_=None, pick=None):
    return {
        "intent": intent,
        "target": target or {},
        "set": set_ or {},
        "pick": pick or {},
        "utterances": ["u"],
    }


def _counts(app):
    with app.state.Session() as s:
        return tuple(
            s.scalar(select(func.count()).select_from(m))
            for m in (Slot, Reservation, ExamPeriod, Outbox)
        )


def _special(ids, date="2026-11-27", start="15:00", end="18:00"):
    return _draft(
        "event.add",
        set_={
            "rooms": [ids["E803"]],
            "dates": [date],
            "time": [start, end],
            "type": 5,
            "subject": "알고리즘 특강",
        },
    )


def test_event_add_preview_diff_and_no_residue(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    before = _counts(app)
    pv = P.make_preview(app.state.Session, ALL, "c_t", _special(ids), NOW)
    assert pv["blockers"] == []
    assert pv["summary"] == ['+ 11/27(금) 15:00–18:00 특강 "알고리즘 특강" (공학관 803)']
    assert any("자료구조" in w for w in pv["warnings"])
    [room] = pv["rooms"]
    assert (room["room_id"], room["label"], room["added"], room["removed"], room["changed"]) == (
        ids["E803"],
        "공학관 803",
        1,
        0,
        0,
    )
    [wk] = room["weeks"]
    assert wk["week_start"] == "2026-11-23" and wk["before"]["reservations"] == []
    assert [x["subject"] for x in wk["after"]["slots"]] == ["알고리즘", "자료구조"]
    [new] = wk["after"]["reservations"]
    assert (new["subject"], new["date"], new["type"]) == ("알고리즘 특강", "2026-11-27", 5)
    assert wk["changes"] == [{"entity": "resv", "key": f"r{new['id']}", "op": "add", "fields": []}]
    assert _counts(app) == before  # rollback — 도메인 행·outbox 아무것도 남지 않는다
    with app.state.Session() as s:
        p = s.get(AssistantPreview, pv["preview_id"])
        assert p.applied_at is None and json.loads(p.ops)[0]["op"] == "resv.put"
        assert p.expires_at - UTC_NOW == dt.timedelta(minutes=10)


def test_past_time_is_blocked(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    pv = P.make_preview(
        app.state.Session, ALL, "c_t", _special(ids, "2026-11-25", "09:00", "10:00"), NOW
    )
    assert any("이미 지난 시각" in b for b in pv["blockers"])


def test_notice_outside_node_window(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    pv = P.make_preview(app.state.Session, ALL, "c_t", _special(ids, "2026-12-10"), NOW)
    assert "12/10(목) 일정은 저장해 두고 12/3(목)부터 문 앞 화면에 보냅니다." in pv["notices"]


def test_op_error_becomes_blocker(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    with app.state.Session() as s, s.begin():
        s.add(
            Slot(
                room_id=ids["E801"],
                day=2,
                s_h=9,
                s_m=0,
                e_h=10,
                e_m=0,
                type=1,
                subject="긴급",
                professor="",
                source=3,
            )
        )
    d = _draft(
        "class.change",
        target={"rooms": [ids["E801"]], "weekdays": [2], "time": ["09:00", None]},
        set_={"subject": "새과목"},
    )
    pv = P.make_preview(app.state.Session, ALL, "c_t", d, NOW)
    assert any("source 3" in b for b in pv["blockers"])
    assert pv["rooms"][0]["weeks"][0]["changes"] == []  # 실패하면 바뀐 뒤 = 바뀌기 전


def test_class_change_moves_slot(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    d = _draft(
        "class.change",
        target={"rooms": [ids["E803"]], "weekdays": [1], "subject": "알고리즘"},
        set_={"weekdays": [2]},
    )
    pv = P.make_preview(app.state.Session, ALL, "c_t", d, NOW)
    [wk] = pv["rooms"][0]["weeks"]
    assert wk["week_start"] is None and wk["after"]["reservations"] == []
    assert [(m["key"], m["op"]) for m in wk["changes"]] == [
        ("d1-0900", "remove"),
        ("d2-0900", "add"),
    ]
    assert pv["summary"][0].startswith("~ 매주 월 09:00–12:00 알고리즘 → 화 09:00–12:00")


def test_request_approve_marks_status_change(client, app, students, monkeypatch):
    fix_clock(monkeypatch)
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
    pv = P.make_preview(
        app.state.Session, ALL, "c_t", _draft("request.approve", target={"requester": "학생1"}), NOW
    )
    assert pv["summary"] == ['✓ 승인 공학관 801 11/26(목) 13:00–14:00 학생1 "스터디"']
    [wk] = pv["rooms"][0]["weeks"]
    assert wk["changes"] == [{"entity": "resv", "key": "r31", "op": "change", "fields": ["status"]}]


def test_fingerprint_tracks_only_given_rooms(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    with app.state.Session() as s:
        fp = P.fingerprint(s, [ids["E803"]])
    resv(app, ids["E801"], dt.date(2026, 11, 27), (9, 0), (10, 0), id_=40)
    with app.state.Session() as s:
        assert P.fingerprint(s, [ids["E803"]]) == fp
    resv(app, ids["E803"], dt.date(2026, 11, 27), (9, 0), (10, 0), id_=41)
    with app.state.Session() as s:
        assert P.fingerprint(s, [ids["E803"]]) != fp

import datetime as dt
import json

import pytest
from sqlalchemy import func, select

from app.assistant import preview as P
from app.assistant.models import AssistantPreview
from app.auth.scope import Scope
from app.domain.models import Building, ExamPeriod, Reservation, Slot
from app.lora_service import api
from app.lora_service.models import Modem, Outbox, RoomVersion
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


# ---- 수정 1차: 범위·주 수·덮어쓰기·보호·만료 ----


def _versions(app):
    with app.state.Session() as s:
        return sorted((r.bld, r.room, r.kind, r.ver) for r in s.scalars(select(RoomVersion)))


def _modems(app, ids):
    with app.state.Session() as s, s.begin():
        s.add_all(
            [
                Modem(modem_id="mA", token_hash="x", school_id=1),
                Modem(modem_id="mB", token_hash="x", school_id=1),
            ]
        )
        s.flush()
        s.get(Building, ids["E"]).modem_id = "mA"
        s.get(Building, ids["H"]).modem_id = "mB"


def test_preview_leaves_versions_and_does_not_notify(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    _modems(app, ids)
    calls = []
    monkeypatch.setattr(api, "notify", lambda m: calls.append(m))
    P.make_preview(app.state.Session, ALL, "c_t", _special(ids), NOW)  # 버전 행이 아직 없을 때
    assert _versions(app) == []
    with app.state.Session() as s, s.begin():
        s.add(RoomVersion(bld="E", room=803, kind="resv", ver=7))
    before = _versions(app)
    P.make_preview(app.state.Session, ALL, "c_t", _special(ids), NOW)
    assert _versions(app) == before
    assert calls == []


def test_preview_rolls_back_approve(client, app, students, monkeypatch):
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
    P.make_preview(
        app.state.Session, ALL, "c_t", _draft("request.approve", target={"requester": "학생1"}), NOW
    )
    with app.state.Session() as s:
        r = s.get(Reservation, 31)
        assert (r.status, r.decided_by, r.pushed_at) == ("requested", None, None)


def test_out_of_scope_room_is_blocked_without_data(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    resv(app, ids["E803"], dt.date(2026, 11, 28), (9, 0), (10, 0), id_=50, subject="비밀회의")
    only_h = Scope(1, frozenset({ids["H"]}), "admin@mju.ac.kr")
    pv = P.make_preview(app.state.Session, only_h, "c_t", _special(ids), NOW)
    assert pv["blockers"] == ["권한 밖 강의실이 있습니다"]
    assert pv["rooms"] == [] and pv["summary"] == []
    assert "비밀회의" not in json.dumps(pv, ensure_ascii=False, default=str)
    assert "알고리즘" not in json.dumps(pv, ensure_ascii=False, default=str)
    other_school = Scope(2, None, "x@other.ac.kr")  # 다른 학교
    pv = P.make_preview(app.state.Session, other_school, "c_t", _special(ids), NOW)
    assert pv["blockers"] == ["권한 밖 강의실이 있습니다"] and pv["rooms"] == []


def test_fingerprint_detects_status_slot_and_exam_changes(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    resv(app, ids["E803"], dt.date(2026, 11, 28), (9, 0), (10, 0), id_=60, status="requested")

    def fp():
        with app.state.Session() as s:
            return P.fingerprint(s, [ids["E803"]])

    seen = [fp()]
    with app.state.Session() as s, s.begin():
        s.get(Reservation, 60).status = "approved"
    seen.append(fp())
    with app.state.Session() as s, s.begin():
        x = s.scalar(select(Slot).where(Slot.room_id == ids["E803"], Slot.day == 1))
        x.source = 3
    seen.append(fp())
    with app.state.Session() as s, s.begin():
        x = s.scalar(select(Slot).where(Slot.room_id == ids["E803"], Slot.day == 1))
        x.subject = "알고리즘2"
    seen.append(fp())
    with app.state.Session() as s, s.begin():
        s.add(
            ExamPeriod(
                room_id=ids["E803"], date_start=dt.date(2026, 12, 1), date_end=dt.date(2026, 12, 5)
            )
        )
    seen.append(fp())
    assert len(set(seen)) == len(seen)


def _class(intent, ids, target=None, set_=None):
    return _draft(intent, target={"rooms": [ids["E803"]], **(target or {})}, set_=set_)


def test_class_add_same_start_warns_overwrite(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    d = _draft(
        "class.add",
        set_={
            "rooms": [ids["E803"]],
            "weekdays": [1],
            "time": ["09:00", "10:00"],
            "subject": "새수업",
        },
    )
    pv = P.make_preview(app.state.Session, ALL, "c_t", d, NOW)
    assert '공학관 803 기존 수업 "알고리즘"(월 09:00–12:00)을 바꿉니다.' in pv["warnings"]
    assert '공학관 803 기존 수업 "알고리즘"(월 09:00–12:00)와 겹칩니다.' in pv["warnings"]
    assert "− 매주 월 09:00–12:00 알고리즘 (공학관 803)" in pv["summary"]


def test_class_change_checks_overlap_with_other_slots(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    d = _class(
        "class.change",
        ids,
        {"weekdays": [5], "subject": "자료구조"},
        {"weekdays": [1], "time": ["10:00", "11:00"]},
    )
    pv = P.make_preview(app.state.Session, ALL, "c_t", d, NOW)
    assert any("기존 수업" in w and "알고리즘" in w and "겹칩니다" in w for w in pv["warnings"])
    # 제자리 수정은 자기 자신과 겹친다고 하지 않는다
    d = _class(
        "class.change", ids, {"weekdays": [5], "subject": "자료구조"}, {"time": ["15:00", "16:00"]}
    )
    pv = P.make_preview(app.state.Session, ALL, "c_t", d, NOW)
    assert not [w for w in pv["warnings"] if "겹칩니다" in w or "바꿉니다" in w]


@pytest.mark.parametrize("intent", ["class.remove", "class.change"])
def test_portal_slot_cannot_be_removed_or_moved(client, app, monkeypatch, intent):
    fix_clock(monkeypatch)
    ids = campus(app)
    with app.state.Session() as s, s.begin():
        s.scalar(select(Slot).where(Slot.room_id == ids["E803"], Slot.day == 1)).source = 3
    set_ = {"weekdays": [2]} if intent == "class.change" else None
    d = _class(intent, ids, {"weekdays": [1], "subject": "알고리즘"}, set_)
    pv = P.make_preview(app.state.Session, ALL, "c_t", d, NOW)
    assert any("포털·긴급 수업은 AI 비서로 지우거나 옮길 수 없습니다" in b for b in pv["blockers"])


def test_exam_change_past_range_is_blocked(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    with app.state.Session() as s, s.begin():
        s.add(
            ExamPeriod(
                room_id=ids["E803"], date_start=dt.date(2026, 12, 1), date_end=dt.date(2026, 12, 5)
            )
        )
    d = _class("exam.change", ids, {}, {"range": ["2026-11-01", "2026-11-05"]})
    pv = P.make_preview(app.state.Session, ALL, "c_t", d, NOW)
    assert any("이미 지난 기간" in b for b in pv["blockers"])


def test_many_weeks_counts_all_and_draws_six(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    d = _draft("exam.add", set_={"rooms": [ids["E803"]], "range": ["2026-11-30", "2027-02-07"]})
    pv = P.make_preview(app.state.Session, ALL, "c_t", d, NOW)
    [room] = pv["rooms"]
    assert len(room["weeks"]) == 6 and room["added"] == 1  # 시험기간은 10주에 걸치지만 하나
    assert "공학관 803: 10주 중 앞 6주만 그렸습니다" in pv["notices"]


def test_preview_expires_at_event_start(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    d = _draft(
        "event.add",
        set_={
            "rooms": [ids["E803"]],
            "dates": ["2026-11-25"],
            "time": ["10:05", "11:00"],
            "type": 5,
            "subject": "곧",
        },
    )
    pv = P.make_preview(app.state.Session, ALL, "c_t", d, NOW)
    assert pv["blockers"] == []
    assert pv["expires_at"] == (UTC_NOW + dt.timedelta(minutes=5)).replace(tzinfo=dt.UTC)
    code, _ = P.apply_preview(
        app.state.Session, ALL, pv["preview_id"], NOW + dt.timedelta(minutes=6)
    )
    assert code == 410

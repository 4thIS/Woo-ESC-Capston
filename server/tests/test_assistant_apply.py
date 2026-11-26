import datetime as dt
import json
import threading

from fastapi import HTTPException
from sqlalchemy import func, select

from app.assistant import preview as P
from app.assistant.models import AssistantChange, AssistantPreview
from app.auth.scope import Scope
from app.domain import ops
from app.domain.models import Building, Reservation
from app.lora_service import api
from app.lora_service.models import Modem, Outbox
from tests.assistant_util import ALL, NOW, campus, fix_clock, resv


def _pv(app, room_ids, date="2026-11-27"):
    d = {
        "intent": "event.add",
        "target": {},
        "set": {
            "rooms": room_ids,
            "dates": [date],
            "time": ["15:00", "18:00"],
            "type": 5,
            "subject": "알고리즘 특강",
        },
        "pick": {},
        "utterances": ["803 특강", "알고리즘 특강"],
    }
    return P.make_preview(app.state.Session, ALL, "c_t", d, NOW)


def _apply(app, pid, now=NOW, sc=ALL):
    return P.apply_preview(app.state.Session, sc, pid, now)


def test_apply_commits_what_preview_showed(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    pv = _pv(app, [ids["E803"]])
    code, body = _apply(app, pv["preview_id"])
    assert code == 200 and body["outbox_ids"]
    with app.state.Session() as s:
        assert P.week_data(s, ids["E803"], "2026-11-23") == pv["rooms"][0]["weeks"][0]["after"]
        ch = s.get(AssistantChange, body["change_id"])
        assert (
            ch.utterance == "803 특강 / 알고리즘 특강" and json.loads(ch.summary) == pv["summary"]
        )
        assert (
            json.loads(ch.building_ids) == [ids["E"]]
            and json.loads(ch.outbox_ids) == body["outbox_ids"]
        )
        assert ch.user_email == "admin@mju.ac.kr" and ch.school_id == 1
        assert s.get(AssistantPreview, pv["preview_id"]).applied_at is not None
        assert [o.type for o in s.scalars(select(Outbox))] == ["RESV_SET"]


def test_apply_twice_or_after_ttl_is_410(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    pv = _pv(app, [ids["E803"]])
    assert _apply(app, pv["preview_id"])[0] == 200
    assert _apply(app, pv["preview_id"]) == (410, {"detail": "expired"})
    pv2 = _pv(app, [ids["E801"]])
    assert _apply(app, pv2["preview_id"], NOW + dt.timedelta(minutes=11)) == (
        410,
        {"detail": "expired"},
    )


def test_stale_preview_returns_new_preview(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    pv = _pv(app, [ids["E803"]])
    resv(
        app, ids["E803"], dt.date(2026, 11, 28), (9, 0), (10, 0), id_=50
    )  # 다른 관리자가 같은 방을 바꿈
    code, body = _apply(app, pv["preview_id"])
    assert code == 409 and body["detail"] == "stale"
    assert body["preview"]["preview_id"] != pv["preview_id"] and body["preview"]["blockers"] == []
    assert body["preview"]["expires_at"].endswith("Z")  # /turns 의 미리보기와 같은 직렬화
    assert _apply(app, pv["preview_id"])[0] == 410  # 옛 미리보기는 더 못 쓴다
    assert _apply(app, body["preview"]["preview_id"])[0] == 200


def test_blocked_preview_is_422(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    pv = _pv(app, [ids["E803"]], date="2026-11-24")  # 지난 날짜
    code, body = _apply(app, pv["preview_id"])
    assert code == 422 and body["detail"] == "blocked" and body["blockers"] == pv["blockers"]


def test_apply_is_atomic_across_rooms(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    pv = _pv(app, [ids["E801"], ids["E802"]])
    assert pv["blockers"] == []
    orig = ops.write_resv

    def boom(s, room_id, *a, **kw):
        if room_id == ids["E802"]:
            raise HTTPException(409, "용량 초과(테스트)")
        return orig(s, room_id, *a, **kw)

    monkeypatch.setattr(ops, "write_resv", boom)
    assert _apply(app, pv["preview_id"]) == (
        422,
        {"detail": "blocked", "blockers": ["용량 초과(테스트)"]},
    )
    with app.state.Session() as s:
        assert s.scalar(select(func.count()).select_from(Reservation)) == 0  # 801 도 안 들어갔다
        assert s.scalar(select(func.count()).select_from(Outbox)) == 0
        assert s.get(AssistantPreview, pv["preview_id"]).applied_at is None


def test_other_admin_cannot_apply(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    pv = _pv(app, [ids["E803"]])
    other = Scope(1, None, "someone@mju.ac.kr")
    assert _apply(app, pv["preview_id"], sc=other) == (404, {"detail": "미리보기 없음"})


def test_missing_preview_is_404(client, app, monkeypatch):
    fix_clock(monkeypatch)
    campus(app)
    assert _apply(app, "p_nope") == (404, {"detail": "미리보기 없음"})


# ---- 수정 1차 ----


def test_apply_notifies_each_modem(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
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
    pv = _pv(app, [ids["E803"], ids["H803"]])
    calls = []
    monkeypatch.setattr(api, "notify", lambda m: calls.append(m))
    assert _apply(app, pv["preview_id"])[0] == 200
    assert sorted(calls) == ["mA", "mB"]


def test_scope_lost_before_apply_is_404_without_data(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    pv = _pv(app, [ids["E803"]])
    resv(app, ids["E803"], dt.date(2026, 11, 28), (9, 0), (10, 0), id_=50, subject="비밀회의")
    only_h = Scope(1, frozenset({ids["H"]}), "admin@mju.ac.kr")
    code, body = _apply(app, pv["preview_id"], sc=only_h)
    assert (code, body) == (404, {"detail": "미리보기 없음"})
    with app.state.Session() as s:  # 새 미리보기도 만들지 않았다
        assert s.scalar(select(func.count()).select_from(AssistantPreview)) == 1


def test_concurrent_apply_commits_once(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    pv = _pv(app, [ids["E803"]])
    codes = []
    barrier = threading.Barrier(4)

    def go():
        barrier.wait()
        codes.append(_apply(app, pv["preview_id"])[0])

    ts = [threading.Thread(target=go) for _ in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert sorted(codes) == [200, 410, 410, 410]
    with app.state.Session() as s:
        assert s.scalar(select(func.count()).select_from(AssistantChange)) == 1
        assert s.scalar(select(func.count()).select_from(Reservation)) == 1


def test_apply_error_rolls_back_and_does_not_notify(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    pv = _pv(app, [ids["E803"]])
    calls = []
    monkeypatch.setattr(api, "notify", lambda m: calls.append(m))

    def boom(*a, **kw):
        raise HTTPException(409, "터짐")

    monkeypatch.setattr(ops, "write_resv", boom)
    assert _apply(app, pv["preview_id"]) == (422, {"detail": "blocked", "blockers": ["터짐"]})
    assert calls == []
    with app.state.Session() as s:
        assert s.scalar(select(func.count()).select_from(AssistantChange)) == 0
        assert s.get(AssistantPreview, pv["preview_id"]).applied_at is None

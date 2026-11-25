import datetime as dt
import json

import pytest
from assistant_proto import SYSTEM_PROMPT, rules
from sqlalchemy import select

from app.assistant import manifest
from app.assistant import router as assistant_router
from app.assistant.models import AssistantTurn
from tests.assistant_util import UTC_NOW, building_admin, campus, fix_clock, form, turn
from tests.conftest import _hdr

GOOD_MODEL = {
    "enabled": True,
    "runtime": "webllm",
    "repo": "4thIS/esc-assistant-e2b",
    "revision": "a" * 40,
    "files": [{"name": "model.bin", "size": 123, "sha256": "b" * 64}],
    "generation": {"temperature": 0, "max_tokens": 256},
}
FIRST = form(
    "event.add",
    set_={"rooms": ["803호"], "when": "이번주 금요일", "time": "15시부터 18시까지", "type": "특강"},
)
FIRST_TEXT = "803호 이번주 금요일 15시부터 18시까지 특강 예약해줘"


def test_model_disabled_without_manifest_flag(client, tmp_path, monkeypatch):
    p = tmp_path / "model.json"
    p.write_text(json.dumps({"enabled": False}), encoding="utf-8")
    monkeypatch.setattr(manifest, "MODEL_FILE", p)
    assert client.get("/api/assistant/model").json() == {"enabled": False}
    assert manifest.load() == {"enabled": False} and manifest.current_revision() is None


def test_model_enabled_and_validated(client, tmp_path, monkeypatch):
    p = tmp_path / "model.json"
    p.write_text(json.dumps(GOOD_MODEL), encoding="utf-8")
    monkeypatch.setattr(manifest, "MODEL_FILE", p)
    j = client.get("/api/assistant/model").json()
    assert (
        j["enabled"]
        and j["schema_v"] == 1
        and j["revision"] == "a" * 40
        and j["runtime"] == "webllm"
    )
    assert j["system_prompt"] == SYSTEM_PROMPT and j["first_prefix"] == "관리자: "
    assert j["json_schema"]["properties"]["v"] == {"const": 1} and j["files"] == GOOD_MODEL["files"]
    assert manifest.current_revision() == "a" * 40
    p.write_text(json.dumps({**GOOD_MODEL, "revision": "main"}), encoding="utf-8")
    with pytest.raises(ValueError):
        manifest.load()


def test_flow_ask_fill_choose_preview_apply(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    j = turn(client, FIRST_TEXT, FIRST)
    assert j["kind"] == "ask" and j["message"] == "특강 이름은 무엇인가요?" and not j["closed"]
    assert j["next_prefix"] == (
        "상태: event.add | 강의실 803호 | 날짜 이번주 금요일 | 시각 15시부터 18시까지 | 유형 특강 | 이름 ?\n"
        "질문: 특강 이름은 무엇인가요?\n관리자: "
    )
    conv = j["conversation_id"]
    j = turn(
        client, "알고리즘 특강이요", form("fill", set_={"subject": "알고리즘 특강"}), conv=conv
    )
    assert j["kind"] == "ask" and [c["label"] for c in j["choices"]] == ["공학관 803", "인문관 803"]
    j = turn(client, "공학관 803", conv=conv, choice=f"room:{ids['E803']}")
    assert j["kind"] == "preview" and j["preview"]["blockers"] == [] and not j["closed"]
    assert j["next_prefix"].endswith(
        "질문: 확인 화면을 보고 [적용]을 눌러 주세요. 바꿀 것이 있으면 말씀해 주세요.\n관리자: "
    )
    assert j["preview"]["expires_at"].endswith("Z")
    pid = j["preview"]["preview_id"]
    r = client.post(f"/api/assistant/previews/{pid}/apply")
    assert r.status_code == 200 and r.json()["outbox_ids"]
    rows = client.get(f"/api/rooms/{ids['E803']}/reservations").json()
    assert [(x["subject"], x["date"], x["s_h"], x["e_h"]) for x in rows] == [
        ("알고리즘 특강", "2026-11-27", 15, 18)
    ]
    assert client.post(f"/api/assistant/previews/{pid}/apply").status_code == 410
    [ch] = client.get("/api/assistant/changes").json()
    assert ch["summary"] == j["preview"]["summary"] and ch["utterance"].startswith(FIRST_TEXT)
    assert ch["applied_at"].endswith("Z")


def test_refine_after_preview_makes_new_preview(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    f = form(
        "event.add",
        set_={
            "rooms": ["공학관 803"],
            "when": "이번주 금요일",
            "time": "17시~18시",
            "type": "특강",
            "subject": "세미나",
        },
    )
    j = turn(client, "공학관 803 금 17~18 세미나 특강", f)
    assert j["kind"] == "preview"
    j2 = turn(
        client, "아 801도", form("fill", set_={"rooms": ["공학관 801"]}), conv=j["conversation_id"]
    )
    assert j2["kind"] == "preview" and j2["preview"]["preview_id"] != j["preview"]["preview_id"]
    assert {r["room_id"] for r in j2["preview"]["rooms"]} == {ids["E803"], ids["E801"]}


def test_schema_version_and_body_shape(client):
    r = client.post(
        "/api/assistant/turns",
        json={"conversation_id": None, "utterance": "x", "form": {**form("cancel"), "v": 2}},
    )
    assert r.status_code == 409 and r.json() == {"detail": "schema_version"}
    assert client.post("/api/assistant/turns", json={"utterance": "x"}).status_code == 422
    both = {"utterance": "x", "form": form("cancel"), "choice": "room:1"}
    assert client.post("/api/assistant/turns", json=both).status_code == 422
    also_raw = {"utterance": "x", "form": form("cancel"), "raw_output": "{"}
    assert client.post("/api/assistant/turns", json=also_raw).status_code == 422


def test_raw_output_is_logged_and_answered_as_error(client, app):
    r = client.post(
        "/api/assistant/turns", json={"utterance": "803 금 특강", "raw_output": '{"v":1,"intent"'}
    )
    j = r.json()
    assert r.status_code == 200 and j["kind"] == "error" and j["closed"]
    assert j["message"].startswith("요청을 이해하지 못했습니다")
    with app.state.Session() as s:
        t = s.scalars(select(AssistantTurn).order_by(AssistantTurn.id.desc())).first()
        assert t.form == '{"v":1,"intent"' and t.reply_kind == "error"


def test_requires_manager(client_raw, student_hdr):
    assert client_raw.get("/api/assistant/model").status_code == 401
    assert client_raw.get("/api/assistant/model", headers=student_hdr).status_code == 403
    r = client_raw.post(
        "/api/assistant/turns", json={"utterance": "x", "form": form("cancel")}, headers=student_hdr
    )
    assert r.status_code == 403


def test_rate_limited(client, monkeypatch):
    monkeypatch.setattr(assistant_router, "TURNS_PER_MIN", 2)
    for _ in range(2):
        turn(client, "취소", form("cancel"))
    r = client.post("/api/assistant/turns", json={"utterance": "취소", "form": form("cancel")})
    assert r.status_code == 429


def test_cancel_unknown_fill_and_bad_choice(client, app, monkeypatch):
    fix_clock(monkeypatch)
    campus(app)
    j = turn(client, "취소", form("cancel"))
    assert (j["kind"], j["message"], j["closed"], j["next_prefix"]) == (
        "answer",
        "취소했습니다.",
        True,
        None,
    )
    j = turn(client, "안녕", form("unknown"))
    assert (
        j["kind"] == "error"
        and j["closed"]
        and j["message"].startswith("그 요청은 AI 비서가 할 수 없습니다")
    )
    j = turn(client, "자료구조", form("fill", set_={"subject": "자료구조"}))
    assert j["kind"] == "error" and j["message"].startswith("무엇을 할지 먼저 말씀해 주세요")
    j = turn(client, FIRST_TEXT, FIRST)
    j = turn(client, "아무거나", conv=j["conversation_id"], choice="room:999999")
    assert (
        j["kind"] == "error"
        and not j["closed"]
        and j["message"].startswith("그 선택지는 지금 고를 수 없습니다")
    )
    j = turn(
        client,
        "x",
        {"v": 1, "intent": "event.add", "target": {}, "set": {"rooms": []}},
        conv=j["conversation_id"],
    )
    assert j["kind"] == "error" and j["message"].startswith("요청을 이해하지 못했습니다")


def test_answer_closes_conversation(client, app, monkeypatch):
    fix_clock(monkeypatch)
    campus(app)
    j = turn(client, "공학관 803 노드 상태", form("ask.node", target={"rooms": ["공학관 803"]}))
    assert j["kind"] == "answer" and j["closed"] and j["answer"]["columns"][0] == "강의실"


def test_expired_conversation(client, app, monkeypatch):
    fix_clock(monkeypatch)
    campus(app)
    j = turn(client, FIRST_TEXT, FIRST)
    fix_clock(monkeypatch, UTC_NOW + dt.timedelta(minutes=31))
    j = turn(
        client,
        "알고리즘 특강",
        form("fill", set_={"subject": "알고리즘 특강"}),
        conv=j["conversation_id"],
    )
    assert (j["kind"], j["closed"]) == ("error", True)
    assert j["message"] == "대화가 만료되었습니다. 다시 말씀해 주세요."


def test_turns_are_logged(client, app, monkeypatch):
    fix_clock(monkeypatch)
    campus(app)
    j = turn(client, FIRST_TEXT, FIRST)
    turn(
        client,
        "알고리즘 특강이요",
        form("fill", set_={"subject": "알고리즘 특강"}),
        conv=j["conversation_id"],
    )
    with app.state.Session() as s:
        rows = s.scalars(select(AssistantTurn).order_by(AssistantTurn.id)).all()
    assert [(r.utterance, r.reply_kind) for r in rows] == [
        (FIRST_TEXT, "ask"),
        ("알고리즘 특강이요", "ask"),
    ]
    assert json.loads(rows[0].form) == FIRST and rows[0].user_email == "admin@mju.ac.kr"
    assert rows[0].conversation_id == rows[1].conversation_id == j["conversation_id"]


def test_building_admin_scope(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    building_admin(app, "h@mju.ac.kr", [ids["H"]])
    h = _hdr(app, "h@mju.ac.kr")
    f = form(
        "event.add",
        set_={
            "rooms": ["공학관 803"],
            "when": "이번주 금요일",
            "time": "17시~18시",
            "type": "특강",
            "subject": "세미나",
        },
    )
    j = turn(client, "공학관 803 세미나", f, headers=h)
    assert j["kind"] == "ask" and j["message"].startswith("'공학관 803' 강의실을 찾지 못했습니다")
    j = turn(client, "공학관 803 세미나", f)  # 최고 관리자
    pid = j["preview"]["preview_id"]
    assert client.post(f"/api/assistant/previews/{pid}/apply", headers=h).status_code == 404
    assert client.post(f"/api/assistant/previews/{pid}/apply").status_code == 200
    assert client.get("/api/assistant/changes", headers=h).json() == []
    assert len(client.get("/api/assistant/changes").json()) == 1


def _post(client, **body):
    return client.post("/api/assistant/turns", json=body)


def test_schema_version_conflict_only_for_int_mismatch(client, app, monkeypatch):
    fix_clock(monkeypatch)
    campus(app)
    j = _post(client, utterance="x", form={}).json()  # v 없음 — 보통의 오류 턴
    assert j["kind"] == "error" and j["message"].startswith("요청을 이해하지 못했습니다")
    r = _post(client, utterance="x", form={"v": 2, "intent": "cancel", "target": {}, "set": {}})
    assert r.status_code == 409 and r.json() == {"detail": "schema_version"}
    r = _post(client, utterance="x", form={"v": True, "intent": "cancel", "target": {}, "set": {}})
    assert r.status_code == 200 and r.json()["kind"] == "error"
    r = _post(client, utterance="x", form={"v": "1", "intent": "cancel", "target": {}, "set": {}})
    assert r.status_code == 200 and r.json()["kind"] == "error"


def test_input_bounds(client):
    assert _post(client, utterance="   ", form=form("cancel")).status_code == 422
    assert _post(client, utterance="", form=form("cancel")).status_code == 422
    big = form("event.add", set_={"subject": "가" * 5000})
    assert _post(client, utterance="x", form=big).status_code == 422
    ok = _post(client, utterance="  취소  ", form=form("cancel"))
    assert ok.status_code == 200


def _q(j) -> str:
    """next_prefix 의 '질문:' 줄."""
    [line] = [x for x in j["next_prefix"].split(chr(10)) if x.startswith("질문: ")]
    return line[len("질문: ") :]


def _ev(**set_):
    return form("event.add", set_={"rooms": ["공학관 803"], "type": "특강", **set_})


def test_prefix_question_is_always_the_rules_text(client, app, monkeypatch):
    fix_clock(monkeypatch)
    campus(app)
    # 칸 묻기 — rules.question
    j = turn(client, "x", _ev(when="이번주 금요일", time="15시~18시"))
    assert j["kind"] == "ask" and _q(j) == rules.question("event.add", "set.subject", "특강")
    # 날짜를 못 풀면 — 설명은 message, 질문 줄은 rules
    j = turn(client, "x", _ev(when="블라블라", time="15시~18시", subject="세미나"))
    assert j["message"].startswith("날짜를") and _q(j) == rules.question("event.add", "set.when")
    # 끝나는 시각 없음
    j = turn(client, "x", _ev(when="이번주 금요일", time="15시", subject="세미나"))
    assert j["message"].startswith("끝나는 시각도")
    assert _q(j) == rules.question("event.add", "set.time")
    # 강의실 못 찾음
    f = form(
        "event.add",
        set_={
            "rooms": ["999"],
            "when": "이번주 금요일",
            "time": "15시~18시",
            "type": "특강",
            "subject": "세",
        },
    )
    j = turn(client, "x", f)
    assert j["message"].startswith("'999' 강의실을 찾지 못했습니다")
    assert _q(j) == rules.question("event.add", "set.rooms")
    # 강의실이 여러 곳 — 고르기
    f = form(
        "event.add",
        set_={
            "rooms": ["803"],
            "when": "이번주 금요일",
            "time": "15시~18시",
            "type": "특강",
            "subject": "세",
        },
    )
    j = turn(client, "x", f)
    assert j["message"].startswith("'803' 강의실이 여러 곳에") and _q(j) == rules.PICK_QUESTION
    # 오류로 대화가 이어질 때 — 질문 줄은 직전 질문 그대로 (오류 문구가 아니다)
    bad = turn(client, "x", conv=j["conversation_id"], choice="room:999999")
    assert bad["kind"] == "error" and not bad["closed"] and _q(bad) == rules.PICK_QUESTION
    bad = turn(client, "x", form("unknown"), conv=j["conversation_id"])
    assert bad["kind"] == "error" and _q(bad) == rules.PICK_QUESTION


def test_prefix_question_kept_after_preview_error(client, app, monkeypatch):
    fix_clock(monkeypatch)
    campus(app)
    f = _ev(when="이번주 금요일", time="17시~18시", subject="세미나")
    j = turn(client, "x", f)
    assert j["kind"] == "preview" and _q(j) == rules.PREVIEW_QUESTION
    bad = turn(client, "x", conv=j["conversation_id"], choice="room:1")
    assert bad["kind"] == "error" and _q(bad) == rules.PREVIEW_QUESTION


def test_not_found_asks_target_and_next_fill_goes_to_target(client, app, monkeypatch):
    fix_clock(monkeypatch)
    campus(app)
    f = form(
        "event.change",
        target={"rooms": ["공학관 803"], "when": "이번주 금요일", "type": "특강"},
        set_={"time": "17시~18시"},
    )
    j = turn(client, "x", f)
    assert j["kind"] == "error" and not j["closed"] and j["message"].startswith("말씀하신 일정을")
    assert _q(j) == rules.question("event.change", "target.any")
    j = turn(
        client, "아 목요일", form("fill", set_={"when": "이번주 목요일"}), conv=j["conversation_id"]
    )
    assert "대상 날짜 이번주 목요일" in j["next_prefix"]
    assert "| 날짜 " not in j["next_prefix"]  # set.when 으로 들어가지 않았다


def test_apply_closes_conversation(client, app, monkeypatch):
    fix_clock(monkeypatch)
    campus(app)
    j = turn(client, "x", _ev(when="이번주 금요일", time="17시~18시", subject="세미나"))
    conv, pid = j["conversation_id"], j["preview"]["preview_id"]
    assert client.post(f"/api/assistant/previews/{pid}/apply").status_code == 200
    j2 = turn(client, "아 801도", form("fill", set_={"rooms": ["공학관 801"]}), conv=conv)
    assert (j2["kind"], j2["closed"]) == ("error", True) and j2["message"].startswith("대화가 만료")
    with app.state.Session() as s:
        from app.assistant.models import AssistantPreview

        assert len(s.scalars(select(AssistantPreview)).all()) == 1  # 새 미리보기를 만들지 않았다

import datetime as dt
import json

from app.assistant import prune
from app.assistant.models import AssistantConversation, AssistantPreview, AssistantTurn
from app.domain import daily
from app.domain.models import JobRun
from tests.assistant_util import UTC_NOW, fix_clock


def _seed(app):
    old, new = UTC_NOW - dt.timedelta(days=181), UTC_NOW - dt.timedelta(days=1, hours=-1)
    with app.state.Session() as s, s.begin():
        for i, t in enumerate((old, new)):
            s.add(
                AssistantTurn(
                    conversation_id=f"c{i}",
                    user_email="admin@mju.ac.kr",
                    utterance="u",
                    reply_kind="ask",
                    reply_message="m",
                    created_at=t,
                )
            )
        for i, t in enumerate((UTC_NOW - dt.timedelta(days=2), UTC_NOW)):
            s.add(
                AssistantConversation(
                    id=f"c_{i}",
                    user_email="admin@mju.ac.kr",
                    state="null",
                    created_at=t,
                    updated_at=t,
                )
            )
            s.add(
                AssistantPreview(
                    id=f"p_{i}",
                    conversation_id=f"c_{i}",
                    user_email="admin@mju.ac.kr",
                    draft="{}",
                    ops="[]",
                    room_ids="[]",
                    fingerprint="x",
                    blockers="[]",
                    summary="[]",
                    created_at=t,
                    expires_at=t,
                )
            )


def test_prune_removes_only_old_rows(app, school):
    _seed(app)
    with app.state.Session() as s, s.begin():
        assert prune.prune(s, UTC_NOW) == {"turns": 1, "conversations": 1, "previews": 1}
    with app.state.Session() as s, s.begin():
        assert prune.prune(s, UTC_NOW) == {"turns": 0, "conversations": 0, "previews": 0}


def test_daily_runs_assistant_step(app, school, monkeypatch):
    fix_clock(monkeypatch)
    _seed(app)
    with app.state.Session() as s:
        res = json.loads(s.get(JobRun, daily.run_daily(app.state.Session)).result)
    assert res["errors"] == [] and res["assistant"] == {
        "turns": 1,
        "conversations": 1,
        "previews": 1,
    }
    assert set(res["pruned"]) == {"reservations", "job_runs", "email_tokens", "rejected_signups"}

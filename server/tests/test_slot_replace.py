"""교시 묶음 수정 — POST /api/rooms/{id}/slots/replace (admin-rooms.md 「연속 교시 묶음」).

지울 교시와 새 교시를 한 트랜잭션으로 — 중간에 실패해도 반만 바뀌지 않는다."""

from __future__ import annotations

import json

from sqlalchemy import select

from app.lora_service.models import Outbox
from tests.test_domain import _setup


def _slot(day, h, m, eh, em, subject="인공지능기초 102", source=2, type_=1):
    return {
        "day": day,
        "s_h": h,
        "s_m": m,
        "e_h": eh,
        "e_m": em,
        "type": type_,
        "subject": subject,
        "professor": "정필성",
        "source": source,
    }


PERIODS = [_slot(2, h, 0, h, 50) for h in (9, 10, 11)]


def _keys(client, rid):
    return [
        (s["day"], s["s_h"], s["s_m"], s["e_h"], s["e_m"])
        for s in client.get(f"/api/rooms/{rid}/slots").json()
    ]


def _types(app, ids):
    with app.state.Session() as s:
        rows = s.scalars(select(Outbox).where(Outbox.id.in_(ids)).order_by(Outbox.id)).all()
        return [(o.type, json.loads(o.payload).get("s_h")) for o in rows]


def test_shift_group_one_hour_later(client, app, live):
    _sch, _b, r = _setup(client)
    rid = r["id"]
    for p in PERIODS:
        assert client.put(f"/api/rooms/{rid}/slots", json=p).status_code == 200
    body = {
        "remove": [{"day": 2, "s_h": h, "s_m": 0} for h in (9, 10, 11)],
        "put": [_slot(2, h, 0, h, 50) for h in (10, 11, 12)],
    }
    res = client.post(f"/api/rooms/{rid}/slots/replace", json=body)
    assert res.status_code == 200, res.text
    assert _keys(client, rid) == [(2, 10, 0, 10, 50), (2, 11, 0, 11, 50), (2, 12, 0, 12, 50)]
    kinds = _types(app, res.json()["outbox_ids"])
    # 09:00 만 지운다 — 10:00 · 11:00 은 새 값으로 다시 SET (DEL 뒤 SET 으로 깜빡이지 않게)
    assert [k for k, _ in kinds].count("SLOT_DEL") == 2  # unit 2개 방
    assert {h for k, h in kinds if k == "SLOT_DEL"} == {9}
    assert {h for k, h in kinds if k == "SLOT_SET"} == {10, 11, 12}


def test_delete_group(client, live):
    _sch, _b, r = _setup(client)
    rid = r["id"]
    for p in PERIODS:
        client.put(f"/api/rooms/{rid}/slots", json=p)
    body = {"remove": [{"day": 2, "s_h": h, "s_m": 0} for h in (9, 10, 11)], "put": []}
    assert client.post(f"/api/rooms/{rid}/slots/replace", json=body).status_code == 200
    assert _keys(client, rid) == []


def test_all_or_nothing_when_one_put_is_refused(client, live):
    """긴급(3) 교시를 수동(2)으로 덮으려 하면 409 — 앞에서 지운 교시도 되살아난다."""
    _sch, _b, r = _setup(client)
    rid = r["id"]
    client.put(f"/api/rooms/{rid}/slots", json=_slot(2, 9, 0, 9, 50))
    client.put(f"/api/rooms/{rid}/slots", json=_slot(2, 10, 0, 10, 50, source=3))
    body = {
        "remove": [{"day": 2, "s_h": 9, "s_m": 0}],
        "put": [_slot(2, 10, 0, 10, 50, subject="바뀜", source=2)],
    }
    assert client.post(f"/api/rooms/{rid}/slots/replace", json=body).status_code == 409
    assert _keys(client, rid) == [(2, 9, 0, 9, 50), (2, 10, 0, 10, 50)]


def test_rejects_overlapping_or_duplicate_puts(client, live):
    _sch, _b, r = _setup(client)
    rid = r["id"]
    url = f"/api/rooms/{rid}/slots/replace"
    overlap = {"remove": [], "put": [_slot(2, 9, 0, 10, 0), _slot(2, 9, 30, 10, 30)]}
    assert client.post(url, json=overlap).status_code == 422
    dup = {"remove": [], "put": [_slot(2, 9, 0, 9, 50), _slot(2, 9, 0, 9, 40)]}
    assert client.post(url, json=dup).status_code == 422
    too_many = {"remove": [], "put": [_slot(1, h % 24, 0, h % 24, 30) for h in range(25)]}
    assert client.post(url, json=too_many).status_code == 422
    assert _keys(client, rid) == []

"""AI 비서 테스트 도우미 — 이름이 test_ 로 시작하지 않아 pytest 가 수집하지 않는다."""

import datetime as dt

from app.auth import password
from app.auth.models import User, UserBuilding
from app.auth.scope import Scope
from app.domain import clock
from app.domain.models import Building, Reservation, Room, Slot

UTC_NOW = dt.datetime(2026, 11, 25, 1, 0)  # noqa: DTZ001 — KST 11/25(수) 10:00
NOW = dt.datetime(2026, 11, 25, 10, 0)  # noqa: DTZ001 — 같은 시각, KST naive
ALL = Scope(1, None, "admin@mju.ac.kr")


def fix_clock(monkeypatch, utc: dt.datetime = UTC_NOW) -> None:
    monkeypatch.setattr(clock, "now_utc", lambda: utc)


def campus(app) -> dict[str, int]:
    """학교 1: 공학관(E) 301·801·802·803·805, 인문관(H) 201·803. 학교 2: 타교관(Z) 803.
    공학관 803 정규 수업: 월 09:00–12:00 알고리즘(이), 금 15:00–16:15 자료구조(김)."""
    ids: dict[str, int] = {}
    with app.state.Session() as s, s.begin():
        for school_id, name, bld, rooms in (
            (1, "공학관", "E", (301, 801, 802, 803, 805)),
            (1, "인문관", "H", (201, 803)),
            (2, "타교관", "Z", (803,)),
        ):
            b = Building(school_id=school_id, name=name, bld=bld)
            s.add(b)
            s.flush()
            ids[bld] = b.id
            for n in rooms:
                r = Room(building_id=b.id, room=n, units=1)
                s.add(r)
                s.flush()
                ids[f"{bld}{n}"] = r.id
        s.add_all(
            [
                Slot(
                    room_id=ids["E803"],
                    day=1,
                    s_h=9,
                    s_m=0,
                    e_h=12,
                    e_m=0,
                    type=1,
                    subject="알고리즘",
                    professor="이",
                ),
                Slot(
                    room_id=ids["E803"],
                    day=5,
                    s_h=15,
                    s_m=0,
                    e_h=16,
                    e_m=15,
                    type=1,
                    subject="자료구조",
                    professor="김",
                ),
            ]
        )
    return ids


def resv(
    app,
    room_id,
    date,
    start,
    end,
    *,
    id_,
    type_=5,
    subject="특강",
    status="approved",
    requested_by=None,
) -> int:
    """start·end = (시, 분)."""
    with app.state.Session() as s, s.begin():
        s.add(
            Reservation(
                id=id_,
                room_id=room_id,
                date=date,
                s_h=start[0],
                s_m=start[1],
                e_h=end[0],
                e_m=end[1],
                type=type_,
                subject=subject,
                professor="",
                status=status,
                requested_by=requested_by,
                requested_at=UTC_NOW if requested_by else None,
            )
        )
    return id_


def building_admin(app, email: str, building_ids: list[int]) -> None:
    with app.state.Session() as s, s.begin():
        s.add(
            User(
                email=email,
                school_id=1,
                role="building_admin",
                status="active",
                name="건물관리",
                pw_hash=password.hash("adminpass1"),
            )
        )
        s.flush()
        s.add_all([UserBuilding(email=email, building_id=b) for b in building_ids])


def form(intent: str, target: dict | None = None, set_: dict | None = None) -> dict:
    return {"v": 1, "intent": intent, "target": target or {}, "set": set_ or {}}


def turn(client, utterance, form_=None, *, conv=None, choice=None, headers=None) -> dict:
    r = client.post(
        "/api/assistant/turns",
        json={"conversation_id": conv, "utterance": utterance, "form": form_, "choice": choice},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()

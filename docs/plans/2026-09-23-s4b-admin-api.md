# S4b — 관리자 대시보드·모니터 API 구현 계획 (plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

- 생성일시: 2026-09-23
- 기준 spec: `docs/specs/2026-09-23-s4b-admin-api-design.md`. **선행: S4a plan(`docs/plans/2026-09-23-s4a-auth.md`) 완료** — 이 plan 은 S4a 가 만든 `app.deps._DB`, `app.auth.deps.AdminUser`, `app.auth.scope.get_scoped`, conftest 의 `client`(학교 1 관리자 Bearer)·`school`·`other_admin_hdr`·`client_raw` 를 쓴다.
- 담당: wj @leemonta9482. 브랜치 `feature/s4b-admin-api`. 커밋 scope `feat(server)`. PR은 사용자 지시 시. 구현 PR 이 이슈 #36 을 닫는다.
- 개정: r2 (PR #38 리뷰 — `building_outbox` 조인 수정, 채번은 S2c 세션 기준·프로세스 락·같은 방 가드, 실패 버킷에서 취소분 제외, 테스트 날짜·키 단언 정정). **선행: S4a → S2c** (`_addr` 3-튜플·`_commit_notify`·`enqueue_*(session=)`).

**Goal:** 관리자 화면이 `GET /api/admin/summary` 1회로 경고 8종(카운트+미리보기)·총계를, `nodes`·`outbox/failed`·건물 단위 조회로 조인된 목록을 받고, 예약·시험 id 를 서버가 채번한다.

**Architecture:** `app/domain/admin.py` 가 순수 쿼리 함수(세션·school_id 를 받아 dict 목록 반환)이고 `app/domain/admin_router.py` 가 얇게 감싼다. 건물 단위 조회·채번은 `domain/router.py` 에 additive. `terminal_status`·`outbox`·`modems`·`pending_devices` 는 도메인 세션에서 ORM 읽기 조인 — `lora_service/api.py`·`hub.py` 불변.

**Tech Stack:** Python 3.12 · uv · FastAPI 0.141 · SQLAlchemy 2 · pydantic 2 · pytest · ruff

**Spec:** `docs/specs/2026-09-23-s4b-admin-api-design.md`

## Global Constraints

- 경고 판정(코드 상수): `UNSEEN_HOURS = 48`(`terminal_status` 없음 또는 `last_seen_at < now−48h`), `low_batt`·`clock_stale` 플래그, `sync_state == "resync"`, `failed` = `state='failed' and finished_at ≥ now−days`(기본 7), `pending_devices`(학교 모뎀 소속), `pending_approval`(S4a users). `modem_offline` = `modems.connected == False`.
- 기대 노드 = 학교 `rooms × units`, `terminal_status` LEFT JOIN. 없으면 상태 `null`, `sync_state="unknown"`, `warnings=["unseen"]`. `warnings` 순서 고정 `unseen, low_batt, resync, clock_stale`.
- `summary`: `preview` 기본 5·최대 20, `count` 는 전체, `items` 정렬 — 노드류 `last_seen_at` 오래된 순(None 먼저), `failed` `finished_at desc`, `pending_*` 오래된 순. `totals.nodes = Σ units`.
- `outbox/failed`: `days` 1..90, `limit` 1..500. 방 조인 실패 행 제외.
- 건물 단위 조회 4개 응답 = 기존 Out + `room_id`(+outbox 는 `building`). 정렬 `room_id, day, s_h, s_m` / `room_id, date, s_h, s_m` / `room_id, date_start` / `id desc`.
- 채번: `ResvIn.id`·`ExamIn.id` 선택. 없으면 `1..65535` 최소 빈 값(채번~커밋은 프로세스 락), 소진 409 `"id 소진 …"`. 응답 `Enqueued.id`. id 지정은 **같은 방의 기존 행만 수정**, 다른 방 행이면 409, 없는 id 면 그 id 로 생성. 쓰기는 `enqueue_*(session=s)` + `_commit_notify`.
- 실패 버킷·목록은 `last_error == "cancelled"`(관리자 취소가 모뎀에서 failed 로 돌아온 것)를 뺀다.
- 전부 `require_admin` + 학교 스코프, 타 학교 404. 마이그레이션 없음, 스키마 additive. `lora_proto/` 불변. 기존 테스트 그대로.
- uv only; ruff 100/py312; 명령은 `server/`. 커밋 `feat(server): ...`, AI 표기 없음.

---

## 파일 구조

```
server/app/schemas.py              WithRoom 3종, FailedOut, NodeOut, WarningBucket, SummaryTotals, SummaryOut, ModemBriefOut, Enqueued.id, ResvIn/ExamIn.id 선택   (T1, T2, T3)
server/app/domain/router.py        건물 단위 조회 4개, 채번                                          (T1, T2)
server/app/domain/admin.py         expected_nodes / failed_outbox / building_outbox / summary        (T1, T3, T5)
server/app/domain/admin_router.py  /api/admin/{summary,nodes,outbox/failed}                          (T4, T5)
server/app/main.py                 admin_router 등록                                                 (T4)
server/static/index.html, README.md, docs/progress.html                                             (T6)
server/tests/test_admin_building.py  T1   test_admin_ids.py  T2   test_admin_nodes.py  T3·T4   test_admin_summary.py  T5
```

공용 테스트 헬퍼(각 테스트 파일 상단에 복사 — conftest 로 올리지 않는다, 파일마다 시드가 조금씩 다름):

```python
import datetime as dt

from app.domain.models import Building, Room
from app.lora_service.models import Modem, Outbox, TerminalStatus

NOW = dt.datetime(2026, 9, 23, 12, 0, 0)


def _building(app, school_id, bld, rooms=((101, 1), (102, 2)), modem_id=None):
    """건물 1 + 방들. rooms = ((room, units), …). 반환 (building_id, {room: room_id})."""
    with app.state.Session() as s, s.begin():
        if modem_id and s.get(Modem, modem_id) is None:
            s.add(Modem(modem_id=modem_id, token_hash="x", school_id=school_id))
            s.flush()
        b = Building(school_id=school_id, name=f"{bld}동", bld=bld, modem_id=modem_id)
        s.add(b)
        s.flush()
        ids = {}
        for room, units in rooms:
            r = Room(building_id=b.id, room=room, units=units)
            s.add(r)
            s.flush()
            ids[room] = r.id
        return b.id, ids


def _status(app, bld, room, unit, **kw):
    with app.state.Session() as s, s.begin():
        s.add(TerminalStatus(bld=bld, room=room, unit=unit, **kw))


def _outbox(app, bld, room, unit=1, state="failed", finished_at=NOW, **kw):
    with app.state.Session() as s, s.begin():
        o = Outbox(bld=bld, room=room, unit=unit, type=kw.pop("type", "SLOT_SET"), payload="{}",
                   state=state, created_at=NOW, finished_at=finished_at, **kw)
        s.add(o)
        s.flush()
        return o.id
```

---

### Task 1: 건물 단위 조회 4개 (#36)

**Files:**
- Modify: `server/app/schemas.py`, `server/app/domain/router.py`
- Create: `server/app/domain/admin.py` (이 Task 에서는 `building_outbox` 만)
- Test: `server/tests/test_admin_building.py`

**Interfaces:**
- Produces: `S.SlotWithRoom`, `S.ResvWithRoom`, `S.ExamWithRoom`, `S.FailedOut(OutboxOut + room_id: int, building: str)`; `admin.building_outbox(s, building_id, state, limit) -> list[dict]`; `GET /api/buildings/{id}/{slots|reservations|exams|outbox}`.

- [ ] **Step 1: 실패 테스트**

`server/tests/test_admin_building.py` (상단에 공용 헬퍼 복사):

```python
from app.domain.models import ExamPeriod, Reservation, Slot


def _seed_rows(app, ids):
    with app.state.Session() as s, s.begin():
        s.add_all([
            Slot(room_id=ids[102], day=2, s_h=9, s_m=0, e_h=10, e_m=0, type=1, subject="b", professor=""),
            Slot(room_id=ids[101], day=1, s_h=13, s_m=0, e_h=14, e_m=0, type=1, subject="a2", professor=""),
            Slot(room_id=ids[101], day=1, s_h=9, s_m=0, e_h=10, e_m=0, type=1, subject="a1", professor=""),
            Reservation(id=5, room_id=ids[102], date=dt.date(2026, 9, 25), s_h=9, s_m=0, e_h=10, e_m=0, type=6, subject="r2", professor=""),
            Reservation(id=3, room_id=ids[101], date=dt.date(2026, 9, 24), s_h=9, s_m=0, e_h=10, e_m=0, type=6, subject="r1", professor=""),
            ExamPeriod(id=7, room_id=ids[101], date_start=dt.date(2026, 10, 19), date_end=dt.date(2026, 10, 23)),
        ])


def test_building_reads_join_room_id_and_sort(client, app, school):
    bid, ids = _building(app, 1, "E")
    _seed_rows(app, ids)
    r = client.get(f"/api/buildings/{bid}/slots")
    assert r.status_code == 200
    assert [(x["room_id"], x["day"], x["s_h"], x["subject"]) for x in r.json()] == [
        (ids[101], 1, 9, "a1"), (ids[101], 1, 13, "a2"), (ids[102], 2, 9, "b")]
    r = client.get(f"/api/buildings/{bid}/reservations")
    assert [(x["room_id"], x["id"]) for x in r.json()] == [(ids[101], 3), (ids[102], 5)]
    r = client.get(f"/api/buildings/{bid}/exams")
    assert [(x["room_id"], x["id"]) for x in r.json()] == [(ids[101], 7)]


def test_building_reads_scoped_404(client, app, school, other_admin_hdr):
    bid, _ = _building(app, 2, "F")
    for path in ("slots", "reservations", "exams", "outbox"):
        assert client.get(f"/api/buildings/{bid}/{path}").status_code == 404, path
    assert client.get(f"/api/buildings/{bid}/slots", headers=other_admin_hdr).status_code == 200


def test_building_outbox_filters_state_and_joins(client, app, school):
    bid, ids = _building(app, 1, "E")
    _building(app, 1, "G", rooms=((101, 1),))  # 같은 학교 다른 건물, 같은 호수 — 섞이면 안 됨
    a = _outbox(app, "E", 101, state="queued", finished_at=None)
    b = _outbox(app, "E", 102, state="acked")
    _outbox(app, "G", 101, state="queued", finished_at=None)
    r = client.get(f"/api/buildings/{bid}/outbox")
    assert [x["id"] for x in r.json()] == [b, a]  # id desc
    assert r.json()[0]["room_id"] == ids[102] and r.json()[0]["building"] == "E동"
    r = client.get(f"/api/buildings/{bid}/outbox?state=queued&limit=1")
    assert [x["id"] for x in r.json()] == [a]
    assert client.get(f"/api/buildings/{bid}/outbox?limit=501").status_code == 422
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_admin_building.py -q` → FAIL (404)

- [ ] **Step 3: 스키마**

`server/app/schemas.py` (`OutboxOut` 아래):

```python
class SlotWithRoom(SlotOut):
    room_id: int


class ResvWithRoom(ResvOut):
    room_id: int


class ExamWithRoom(ExamOut):
    room_id: int


class FailedOut(OutboxOut):
    """outbox + 방 조인 (S4b §2.4). 건물 단위 outbox·실패 목록·요약 미리보기가 같이 쓴다."""

    room_id: int
    building: str
```

- [ ] **Step 4: `admin.py` — `building_outbox`**

`server/app/domain/admin.py`:

```python
"""관리자 집계·조인 조회 (S4b). 세션과 school_id 를 받아 dict 목록을 돌려준다 — 라우터가 얇게 감싼다.
terminal_status·outbox·modems·pending_devices 는 여기서 ORM 읽기만 한다. lora_service.api 는 부르지 않는다."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app import schemas as S
from app.domain.models import Building, Room
from app.lora_service.models import Outbox


def _outbox_rows(s: Session, q) -> list[dict]:
    """select(Outbox, Room.id, Building.name) 결과 → FailedOut dict."""
    return [
        S.OutboxOut.model_validate(o).model_dump() | {"room_id": rid, "building": bname}
        for o, rid, bname in s.execute(q).all()
    ]


def building_outbox(
    s: Session, building_id: int, state: str | None = None, limit: int = 200
) -> list[dict]:
    q = (
        select(Outbox, Room.id, Building.name)
        .join(Building, and_(Building.bld == Outbox.bld, Building.id == building_id))
        .join(Room, and_(Room.building_id == Building.id, Room.room == Outbox.room))
        .order_by(Outbox.id.desc())
        .limit(limit)
    )
    if state is not None:
        q = q.where(Outbox.state == state)
    return _outbox_rows(s, q)
```

- [ ] **Step 5: 라우터**

`server/app/domain/router.py` `delete_building` 아래 (import 에 `from fastapi import Query`, `from app.domain import admin`):

```python
# ---- 건물 단위 조회 (S4b §2.6, 이슈 #36) — 쓰기는 /rooms/{id}/… 그대로 ----


def _rooms_of(s: Session, building_id: int, user: User):
    scope.get_scoped(s, Building, building_id, user.school_id)
    return select(Room.id).where(Room.building_id == building_id)


@router.get("/buildings/{id}/slots", response_model=list[S.SlotWithRoom])
def building_slots(id: int, user: User = AdminUser, s: Session = _DB):
    return s.scalars(
        select(Slot).where(Slot.room_id.in_(_rooms_of(s, id, user)))
        .order_by(Slot.room_id, Slot.day, Slot.s_h, Slot.s_m)
    ).all()


@router.get("/buildings/{id}/reservations", response_model=list[S.ResvWithRoom])
def building_reservations(id: int, user: User = AdminUser, s: Session = _DB):
    return s.scalars(
        select(Reservation).where(Reservation.room_id.in_(_rooms_of(s, id, user)))
        .order_by(Reservation.room_id, Reservation.date, Reservation.s_h, Reservation.s_m)
    ).all()


@router.get("/buildings/{id}/exams", response_model=list[S.ExamWithRoom])
def building_exams(id: int, user: User = AdminUser, s: Session = _DB):
    return s.scalars(
        select(ExamPeriod).where(ExamPeriod.room_id.in_(_rooms_of(s, id, user)))
        .order_by(ExamPeriod.room_id, ExamPeriod.date_start)
    ).all()


@router.get("/buildings/{id}/outbox", response_model=list[S.FailedOut])
def building_outbox(
    id: int, state: str | None = None, limit: int = Query(200, ge=1, le=500),
    user: User = AdminUser, s: Session = _DB,
):
    scope.get_scoped(s, Building, id, user.school_id)
    return admin.building_outbox(s, id, state, limit)
```

- [ ] **Step 6: 통과 확인·커밋**

Run: `uv run pytest -q` → PASS. ruff.

```bash
git add app/schemas.py app/domain/router.py app/domain/admin.py tests/test_admin_building.py
git commit -m "feat(server): 건물 단위 조회 — /buildings/{id}/slots·reservations·exams·outbox (room_id 조인, #36)"
```

---

### Task 2: 예약·시험 id 서버 채번

**Files:**
- Modify: `server/app/schemas.py` (`ResvIn.id`, `ExamIn.id`, `ResvOut.id`, `ExamOut.id`, `Enqueued.id`), `server/app/domain/router.py` (`put_resv`, `put_exam`)
- Test: `server/tests/test_admin_ids.py`

**Interfaces:**
- Produces: `router.ID_MAX = 65535`, `router._free_id(s, model) -> int`; `Enqueued.id: int | None`.

- [ ] **Step 1: 실패 테스트**

`server/tests/test_admin_ids.py` (공용 헬퍼 복사):

```python
import pytest

from app.domain import router as R

RESV = {"date": "2026-09-24", "s_h": 9, "s_m": 0, "e_h": 10, "e_m": 0, "type": 6, "subject": "r", "professor": ""}
EXAM = {"date_start": "2026-10-19", "date_end": "2026-10-23"}


def test_server_assigns_smallest_free_id(client, app, school):
    _, ids = _building(app, 1, "E")
    rid = ids[101]
    r = client.post(f"/api/rooms/{rid}/reservations", json=RESV)
    assert r.status_code == 200 and r.json()["id"] == 1 and "outbox_ids" in r.json()
    assert client.post(f"/api/rooms/{rid}/reservations", json=RESV).json()["id"] == 2
    assert client.post(f"/api/rooms/{ids[102]}/reservations", json=RESV).json()["id"] == 3  # 전역
    assert client.delete(f"/api/rooms/{rid}/reservations/1").status_code == 200
    assert client.post(f"/api/rooms/{rid}/reservations", json=RESV).json()["id"] == 1  # 빈 최소값 재사용
    # id 지정 upsert 는 기존대로
    r = client.post(f"/api/rooms/{rid}/reservations", json={**RESV, "id": 2, "subject": "edited"})
    assert r.json()["id"] == 2
    assert [x["subject"] for x in client.get(f"/api/rooms/{rid}/reservations").json() if x["id"] == 2] == ["edited"]


def test_explicit_id_must_be_same_room(client, app, school, other_admin_hdr):
    """id 지정 수정은 같은 방의 기존 행만 — 다른 방·다른 학교 행을 빼앗지 못한다 (S4a §3.3 🔴4a)."""
    _, ids = _building(app, 1, "E")
    _, other = _building(app, 2, "F", rooms=((201, 1),))
    assert client.post(f"/api/rooms/{ids[101]}/reservations", json=RESV).json()["id"] == 1
    r = client.post(f"/api/rooms/{ids[102]}/reservations", json={**RESV, "id": 1})
    assert r.status_code == 409 and "다른 방" in r.json()["detail"]
    r = client.post(f"/api/rooms/{other[201]}/reservations", json={**RESV, "id": 1}, headers=other_admin_hdr)
    assert r.status_code == 409  # 타교 관리자도 남의 행을 못 가져간다
    assert client.post(f"/api/rooms/{ids[101]}/exams", json=EXAM).json()["id"] == 1
    assert client.post(f"/api/rooms/{ids[102]}/exams", json={**EXAM, "id": 1}).status_code == 409


def test_exam_ids_same_rule(client, app, school):
    _, ids = _building(app, 1, "E")
    assert client.post(f"/api/rooms/{ids[101]}/exams", json=EXAM).json()["id"] == 1
    assert client.post(f"/api/rooms/{ids[102]}/exams", json=EXAM).json()["id"] == 2
    assert client.post(f"/api/rooms/{ids[101]}/exams", json={**EXAM, "id": 9}).json()["id"] == 9


def test_id_exhausted_409(client, app, school, monkeypatch):
    monkeypatch.setattr(R, "ID_MAX", 2)
    _, ids = _building(app, 1, "E")
    rid = ids[101]
    assert client.post(f"/api/rooms/{rid}/reservations", json=RESV).json()["id"] == 1
    assert client.post(f"/api/rooms/{rid}/reservations", json=RESV).json()["id"] == 2
    r = client.post(f"/api/rooms/{rid}/reservations", json=RESV)
    assert r.status_code == 409 and "소진" in r.json()["detail"]
    assert client.post(f"/api/rooms/{rid}/exams", json={"date_start": "2026-10-19", "date_end": "2026-10-23"}).json()["id"] == 1


def test_explicit_id_still_validated(client, app, school):
    _, ids = _building(app, 1, "E")
    assert client.post(f"/api/rooms/{ids[101]}/reservations", json={**RESV, "id": 0}).status_code == 422
    assert client.post(f"/api/rooms/{ids[101]}/reservations", json={**RESV, "id": 65536}).status_code == 422
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_admin_ids.py -q` → FAIL (422 — `id` 필수)

- [ ] **Step 3: 스키마**

`server/app/schemas.py`:

```python
class ResvIn(_Span):
    id: int | None = Field(None, ge=1, le=65535)  # 없으면 서버 채번 (S4b §2.5)
    date: dt.date


class ResvOut(ResvIn, Out):
    id: int


class ExamIn(BaseModel):
    id: int | None = Field(None, ge=1, le=65535)
    date_start: dt.date
    date_end: dt.date


class ExamOut(ExamIn, Out):
    id: int


class Enqueued(BaseModel):
    outbox_ids: list[int]
    id: int | None = None  # 예약·시험 채번 결과 (S4b §2.5)
```

- [ ] **Step 4: 라우터**

S2c 가 먼저 들어와 있다 — `_addr(s, id, user) -> (bld, room, modem_id)`, `_commit_notify(s, mid)`, `api.enqueue_*(..., session=s)`.

`server/app/domain/router.py` — 모듈 상수·헬퍼(`_addr` 아래, `import threading`):

```python
ID_MAX = 65535  # resvId/examId u16 (v2 §3). 테스트가 monkeypatch 로 낮춘다
_ID_LOCK = threading.Lock()  # 채번~커밋을 직렬화 — 단일 워커(README)라 프로세스 락으로 충돌이 없다


def _free_id(s: Session, model) -> int:
    """1..ID_MAX 중 비어 있는 최소값 (S4b §2.5). 전역 PK 라 방과 무관."""
    used = set(s.scalars(select(model.id)))
    for i in range(1, ID_MAX + 1):
        if i not in used:
            return i
    raise HTTPException(409, "id 소진 — 지난 예약·시험기간을 정리하세요")


def _existing_same_room(s: Session, model, obj_id: int, room_id: int):
    """id 지정 수정은 같은 방의 기존 행만 (S4a §3.3 🔴4a). 다른 방(=다른 학교 포함) 행이면 409.
    없는 id 지정은 그 id 로 새로 만든다 — 기존 S2 호출·테스트 호환, 탈취 위험은 기존 행에만 있다."""
    obj = s.get(model, obj_id)
    if obj is not None and obj.room_id != room_id:
        raise HTTPException(409, "id 가 다른 방의 것입니다 — 방을 옮기려면 삭제 후 다시 만드세요")
    return obj
```

`put_resv`:

```python
@router.post("/rooms/{id}/reservations", response_model=S.Enqueued)
def put_resv(id: int, body: S.ResvIn, user: User = AdminUser, s: Session = _DB):
    bld, room, mid = _addr(s, id, user)
    with _ID_LOCK:  # 확인(채번·같은 방 검사) → insert → 커밋까지 한 덩어리 (다음 요청은 커밋된 행을 본다)
        if body.id is not None:  # 없는 id 지정 생성도 동시 채번과 겹치지 않게 락 안 (r2 ⚪)
            return _write_resv(s, id, bld, room, mid, body, body.id, _existing_same_room(s, Reservation, body.id, id))
        return _write_resv(s, id, bld, room, mid, body, _free_id(s, Reservation), None)


def _write_resv(s, room_id, bld, room, mid, body: S.ResvIn, rid: int, obj: Reservation | None) -> dict:
    obj = obj or Reservation(id=rid, room_id=room_id)
    for k, v in body.model_dump(exclude={"id"}).items():
        setattr(obj, k, v)
    s.add(obj)
    today = dt.datetime.now(dt.UTC).date()  # S10 T1 이 clock.local_today() 로 바꾼다
    ids = []
    if today <= body.date <= today + dt.timedelta(days=RESV_HORIZON_DAYS):
        ids = api.enqueue_resv_set(
            bld, room, rid, body.date, (body.s_h, body.s_m), (body.e_h, body.e_m),
            body.type, body.subject, body.professor, session=s,
        )
    _commit_notify(s, mid)
    return {"outbox_ids": ids, "id": rid}
```

`put_exam`:

```python
@router.post("/rooms/{id}/exams", response_model=S.Enqueued)
def put_exam(id: int, body: S.ExamIn, user: User = AdminUser, s: Session = _DB):
    bld, room, mid = _addr(s, id, user)
    with _ID_LOCK:
        if body.id is not None:
            return _write_exam(s, id, bld, room, mid, body, body.id, _existing_same_room(s, ExamPeriod, body.id, id))
        return _write_exam(s, id, bld, room, mid, body, _free_id(s, ExamPeriod), None)


def _write_exam(s, room_id, bld, room, mid, body: S.ExamIn, eid: int, obj: ExamPeriod | None) -> dict:
    obj = obj or ExamPeriod(id=eid, room_id=room_id)
    obj.date_start, obj.date_end = body.date_start, body.date_end
    s.add(obj)
    ids = api.enqueue_exam_set(bld, room, eid, body.date_start, body.date_end, session=s)
    _commit_notify(s, mid)
    return {"outbox_ids": ids, "id": eid}
```

리뷰는 "충돌 시 1회 재채번"을 권했지만 SQLite(pysqlite) 는 SAVEPOINT 가 기본 설정으로 동작하지 않아 세션 안 재시도가 까다롭다. 단일 워커 전제에서 **채번~커밋을 프로세스 락으로 묶으면 충돌 자체가 없다** — 그쪽을 택했다(워커를 늘리면 이 락과 허브 레지스트리가 함께 깨진다 — README 의 `--workers 1` 과 같은 근거).

- [ ] **Step 5: 통과 확인·커밋**

Run: `uv run pytest -q` → PASS(기존 예약 테스트는 `id` 를 주므로 불변). ruff.

```bash
git add app/schemas.py app/domain/router.py tests/test_admin_ids.py
git commit -m "feat(server): 예약·시험 id 서버 채번 — id 생략 시 1..65535 최소 빈 값, 응답 Enqueued.id (#36)"
```

---

### Task 3: `admin.expected_nodes` / `admin.failed_outbox` (쿼리 층)

**Files:**
- Modify: `server/app/domain/admin.py`, `server/app/schemas.py` (`NodeOut`)
- Test: `server/tests/test_admin_nodes.py` (쿼리 함수 단위)

**Interfaces:**
- Produces: `admin.UNSEEN_HOURS = 48`, `admin.FAILED_DAYS_DEFAULT = 7`, `admin.WARNING_ORDER = ("unseen", "low_batt", "resync", "clock_stale")`, `admin.expected_nodes(s, school_id, building_id=None, now=None) -> list[dict]`(NodeOut 필드), `admin.failed_outbox(s, school_id, days=7, limit=None, now=None) -> list[dict]`(FailedOut).

- [ ] **Step 1: 실패 테스트**

`server/tests/test_admin_nodes.py` (공용 헬퍼 복사):

```python
from app.domain import admin


def _nodes(app, school_id=1, **kw):
    with app.state.Session() as s:
        return admin.expected_nodes(s, school_id, now=NOW, **kw)


def test_expected_nodes_left_join_and_warnings(app, school):
    bid, ids = _building(app, 1, "E", rooms=((101, 1), (102, 2)), modem_id="m1")
    _building(app, 2, "F", rooms=((101, 1),))  # 타 학교
    fresh = NOW - dt.timedelta(hours=47, minutes=59)
    stale = NOW - dt.timedelta(hours=48, seconds=1)
    _status(app, "E", 101, 1, last_seen_at=fresh, low_batt=True, sync_state="synced", batt_mv=3400)
    _status(app, "E", 102, 1, last_seen_at=stale, sync_state="resync", clock_stale=True)
    # E102 unit 2 는 보고 없음
    _status(app, "F", 101, 1, last_seen_at=fresh)
    rows = _nodes(app)
    assert [(r["bld"], r["room"], r["unit"]) for r in rows] == [("E", 101, 1), ("E", 102, 1), ("E", 102, 2)]
    a, b, c = rows
    assert a["room_id"] == ids[101] and a["building"] == "E동" and a["building_id"] == bid
    assert a["warnings"] == ["low_batt"] and a["batt_mv"] == 3400 and a["sync_state"] == "synced"
    assert b["warnings"] == ["unseen", "resync", "clock_stale"]
    assert c["warnings"] == ["unseen"] and c["sync_state"] == "unknown" and c["batt_mv"] is None
    assert c["low_batt"] is False and c["clock_stale"] is False
    assert _nodes(app, building_id=bid) == rows
    assert _nodes(app, school_id=2)[0]["bld"] == "F"


def test_failed_outbox_window_join_and_limit(app, school):
    _, ids = _building(app, 1, "E")
    _building(app, 2, "F", rooms=((101, 1),))
    recent = _outbox(app, "E", 101, finished_at=NOW - dt.timedelta(days=6, hours=23), last_error="no_ack")
    old = _outbox(app, "E", 101, finished_at=NOW - dt.timedelta(days=7, seconds=1))
    _outbox(app, "F", 101, finished_at=NOW)  # 타 학교
    _outbox(app, "E", 999, finished_at=NOW)  # 방 없음 → 제외
    _outbox(app, "E", 102, state="acked", finished_at=NOW)  # 실패 아님
    _outbox(app, "E", 102, finished_at=NOW, last_error="cancelled")  # 관리자 취소 → 제외
    newest = _outbox(app, "E", 102, finished_at=NOW)
    with app.state.Session() as s:
        rows = admin.failed_outbox(s, 1, days=7, now=NOW)
        assert [r["id"] for r in rows] == [newest, recent] and old not in [r["id"] for r in rows]
        assert rows[1]["room_id"] == ids[101] and rows[1]["building"] == "E동" and rows[1]["last_error"] == "no_ack"
        assert [r["id"] for r in admin.failed_outbox(s, 1, days=7, limit=1, now=NOW)] == [newest]
        assert admin.failed_outbox(s, 1, days=8, now=NOW)[-1]["id"] == old
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_admin_nodes.py -q` → FAIL

- [ ] **Step 3: `NodeOut`**

`server/app/schemas.py`:

```python
class NodeOut(BaseModel):
    """기대 노드(rooms × units) × terminal_status (S4b §2.2). 보고 없는 노드는 상태 null + unseen."""

    room_id: int
    building_id: int
    building: str
    bld: str
    room: int
    unit: int
    modem_id: str | None
    mac: str | None
    fw: int | None
    batt_mv: int | None
    rssi: int | None
    snr: float | None
    sched_ver: int | None
    resv_ver: int | None
    exam_ver: int | None
    ident_ver: int | None
    layout: int | None
    clock_stale: bool
    low_batt: bool
    uptime_h: int | None
    last_seen_at: dt.datetime | None
    last_ack_at: dt.datetime | None
    last_status_at: dt.datetime | None
    sync_state: str
    warnings: list[str]
```

- [ ] **Step 4: 구현**

`server/app/domain/admin.py` 에 추가 (import: `from app.db import utcnow`, `from app.lora_service.models import Outbox, TerminalStatus`):

```python
UNSEEN_HOURS = 48  # STATUS 는 일 1회 — 24 h 면 오탐 (S4b §2.1)
FAILED_DAYS_DEFAULT = 7
WARNING_ORDER = ("unseen", "low_batt", "resync", "clock_stale")
_TS_FIELDS = (
    "modem_id", "mac", "fw", "batt_mv", "rssi", "snr", "sched_ver", "resv_ver", "exam_ver",
    "ident_ver", "layout", "uptime_h", "last_seen_at", "last_ack_at", "last_status_at",
)


def expected_nodes(
    s: Session, school_id: int, building_id: int | None = None, now: dt.datetime | None = None
) -> list[dict]:
    """학교의 기대 노드(rooms × units) 에 terminal_status 를 LEFT JOIN 하고 경고를 판정한다."""
    now = now or utcnow()
    cutoff = now - dt.timedelta(hours=UNSEEN_HOURS)
    q = (
        select(Room, Building)
        .join(Building, Room.building_id == Building.id)
        .where(Building.school_id == school_id)
        .order_by(Building.bld, Room.room)
    )
    if building_id is not None:
        q = q.where(Building.id == building_id)
    pairs = s.execute(q).all()
    blds = {b.bld for _, b in pairs}
    status = {
        (t.bld, t.room, t.unit): t
        for t in s.scalars(select(TerminalStatus).where(TerminalStatus.bld.in_(blds)))
    }
    out: list[dict] = []
    for room, b in pairs:
        for unit in range(1, room.units + 1):
            t = status.get((b.bld, room.room, unit))
            unseen = t is None or t.last_seen_at is None or t.last_seen_at < cutoff
            flags = {
                "unseen": unseen,
                "low_batt": bool(t and t.low_batt),
                "resync": bool(t and t.sync_state == "resync"),
                "clock_stale": bool(t and t.clock_stale),
            }
            out.append(
                {
                    "room_id": room.id,
                    "building_id": b.id,
                    "building": b.name,
                    "bld": b.bld,
                    "room": room.room,
                    "unit": unit,
                    **{f: getattr(t, f) if t else None for f in _TS_FIELDS},
                    "clock_stale": flags["clock_stale"],
                    "low_batt": flags["low_batt"],
                    "sync_state": t.sync_state if t else "unknown",
                    "warnings": [w for w in WARNING_ORDER if flags[w]],
                }
            )
    return out


def failed_outbox(
    s: Session,
    school_id: int,
    days: int = FAILED_DAYS_DEFAULT,
    limit: int | None = None,
    now: dt.datetime | None = None,
) -> list[dict]:
    """최근 days 일 failed outbox 에 방·건물 조인. 방을 못 찾는 행(삭제된 방)은 빠진다."""
    cutoff = (now or utcnow()) - dt.timedelta(days=days)
    q = (
        select(Outbox, Room.id, Building.name)
        .join(Building, and_(Building.bld == Outbox.bld, Building.school_id == school_id))
        .join(Room, and_(Room.building_id == Building.id, Room.room == Outbox.room))
        .where(Outbox.state == "failed", Outbox.finished_at >= cutoff)
        .where((Outbox.last_error.is_(None)) | (Outbox.last_error != "cancelled"))  # 관리자 취소분은 실패가 아니다
        .order_by(Outbox.finished_at.desc(), Outbox.id.desc())
    )
    if limit is not None:
        q = q.limit(limit)
    return _outbox_rows(s, q)
```

- [ ] **Step 5: 통과 확인·커밋**

Run: `uv run pytest tests/test_admin_nodes.py -q` → PASS. ruff.

```bash
git add app/domain/admin.py app/schemas.py tests/test_admin_nodes.py
git commit -m "feat(server): admin.expected_nodes(기대 노드 × 상태, 경고 판정)·failed_outbox(7일 창, 방 조인)"
```

---

### Task 4: `/api/admin/nodes` · `/api/admin/outbox/failed`

**Files:**
- Create: `server/app/domain/admin_router.py`
- Modify: `server/app/main.py`
- Test: `server/tests/test_admin_nodes.py` (라우터 테스트 추가)

**Interfaces:**
- Produces: `admin_router.router`(prefix `/api/admin`, `dependencies=[AdminUser]`), `GET /nodes?building_id=&only=`, `GET /outbox/failed?days=&limit=`.

- [ ] **Step 1: 실패 테스트**

`server/tests/test_admin_nodes.py` 끝에:

```python
def test_nodes_endpoint_filters_and_scope(client, app, school, other_admin_hdr, monkeypatch):
    monkeypatch.setattr(admin, "utcnow", lambda: NOW)
    bid, _ = _building(app, 1, "E", rooms=((101, 1), (102, 1)))
    bid2, _ = _building(app, 1, "G", rooms=((201, 1),))
    _building(app, 2, "F", rooms=((101, 1),))
    _status(app, "E", 101, 1, last_seen_at=NOW, low_batt=True)
    _status(app, "E", 102, 1, last_seen_at=NOW)
    _status(app, "G", 201, 1, last_seen_at=NOW, sync_state="resync")
    r = client.get("/api/admin/nodes")
    assert r.status_code == 200 and [(x["bld"], x["room"]) for x in r.json()] == [("E", 101), ("E", 102), ("G", 201)]
    assert [x["room"] for x in client.get("/api/admin/nodes?only=warn").json()] == [101, 201]
    assert [x["room"] for x in client.get("/api/admin/nodes?only=low_batt").json()] == [101]
    assert [x["room"] for x in client.get(f"/api/admin/nodes?building_id={bid2}").json()] == [201]
    assert client.get("/api/admin/nodes?only=bogus").status_code == 422
    assert [x["bld"] for x in client.get("/api/admin/nodes", headers=other_admin_hdr).json()] == ["F"]
    assert client.get(f"/api/admin/nodes?building_id={bid}", headers=other_admin_hdr).status_code == 404


def test_failed_endpoint_params_and_auth(client, client_raw, app, school, monkeypatch):
    monkeypatch.setattr(admin, "utcnow", lambda: NOW)
    _building(app, 1, "E")
    a = _outbox(app, "E", 101, finished_at=NOW - dt.timedelta(days=3))
    r = client.get("/api/admin/outbox/failed")
    assert r.status_code == 200 and [x["id"] for x in r.json()] == [a] and r.json()[0]["building"] == "E동"
    assert client.get("/api/admin/outbox/failed?days=2").json() == []
    assert client.get("/api/admin/outbox/failed?days=91").status_code == 422
    assert client.get("/api/admin/outbox/failed?limit=0").status_code == 422
    assert client_raw.get("/api/admin/outbox/failed").status_code == 401
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_admin_nodes.py -k endpoint -q` → FAIL (404)

- [ ] **Step 3: 라우터**

`server/app/domain/admin_router.py`:

```python
"""관리자 요약·모니터 REST (S4b §4.1). 전부 관리자 전용 + 학교 스코프. 계산은 domain/admin.py."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query
from sqlalchemy.orm import Session

from app import schemas as S
from app.auth import scope
from app.auth.deps import AdminUser
from app.auth.models import User
from app.deps import _DB
from app.domain import admin
from app.domain.models import Building

router = APIRouter(prefix="/api/admin", dependencies=[AdminUser])

Only = Literal["warn", "unseen", "low_batt", "resync", "clock_stale"]


@router.get("/nodes", response_model=list[S.NodeOut])
def nodes(
    building_id: int | None = None, only: Only | None = None,
    user: User = AdminUser, s: Session = _DB,
):
    if building_id is not None:
        scope.get_scoped(s, Building, building_id, user.school_id)
    rows = admin.expected_nodes(s, user.school_id, building_id)
    if only == "warn":
        rows = [r for r in rows if r["warnings"]]
    elif only is not None:
        rows = [r for r in rows if only in r["warnings"]]
    return rows


@router.get("/outbox/failed", response_model=list[S.FailedOut])
def failed(
    days: int = Query(admin.FAILED_DAYS_DEFAULT, ge=1, le=90),
    limit: int = Query(100, ge=1, le=500),
    user: User = AdminUser, s: Session = _DB,
):
    return admin.failed_outbox(s, user.school_id, days, limit)
```

`server/app/main.py`: `from app.domain.admin_router import router as admin_api_router` + `app.include_router(admin_api_router)`.

- [ ] **Step 4: 통과 확인·커밋**

Run: `uv run pytest -q` → PASS. ruff.

```bash
git add app/domain/admin_router.py app/main.py tests/test_admin_nodes.py
git commit -m "feat(server): GET /api/admin/nodes(only·building_id)·/api/admin/outbox/failed(days·limit)"
```

---

### Task 5: `/api/admin/summary` — 카운트 + 미리보기

**Files:**
- Modify: `server/app/domain/admin.py`, `server/app/domain/admin_router.py`, `server/app/schemas.py`
- Test: `server/tests/test_admin_summary.py`

**Interfaces:**
- Produces: `admin.PREVIEW_DEFAULT = 5`, `admin.PREVIEW_MAX = 20`, `admin.summary(s, school_id, preview=5, now=None) -> dict`(SummaryOut); `S.WarningBucket`, `S.SummaryTotals`, `S.SummaryOut`, `S.ModemBriefOut`; `GET /api/admin/summary?preview=`.

- [ ] **Step 1: 실패 테스트**

`server/tests/test_admin_summary.py` (공용 헬퍼 복사 + `from app.auth import password`, `from app.auth.models import User`, `from app.lora_service.models import PendingDevice`):

```python
from app.domain import admin


def _seed(app):
    bid, e = _building(app, 1, "E", rooms=((101, 1), (102, 2)), modem_id="m1")
    _building(app, 1, "G", rooms=((201, 1),), modem_id="m2")
    _building(app, 2, "F", rooms=((101, 1),), modem_id="mf")
    with app.state.Session() as s, s.begin():
        s.get(Modem, "m2").connected = True
        s.get(Modem, "m1").last_seen_at = NOW - dt.timedelta(days=1)
    stale = NOW - dt.timedelta(days=3)
    _status(app, "E", 101, 1, last_seen_at=NOW, low_batt=True, batt_mv=3400)
    _status(app, "E", 102, 1, last_seen_at=stale, low_batt=True, batt_mv=3300, sync_state="resync")
    # E102/2, G201 보고 없음 → unseen 3 (E102/1 포함)
    for i in range(6):
        _outbox(app, "E", 101, finished_at=NOW - dt.timedelta(hours=i))
    with app.state.Session() as s, s.begin():
        s.add_all([
            PendingDevice(mac="aabbccddeeff", modem_id="m1", first_seen_at=NOW - dt.timedelta(hours=2), last_seen_at=NOW),
            PendingDevice(mac="112233445566", modem_id="mf", first_seen_at=NOW, last_seen_at=NOW),
            User(email="p1@mju.ac.kr", school_id=1, role="student", status="pending_approval", name="p1", student_no="1", pw_hash=password.hash("password1")),
            User(email="p2@mju.ac.kr", school_id=1, role="student", status="pending_approval", name="p2", student_no="2", pw_hash=password.hash("password1")),
            User(email="po@other.ac.kr", school_id=2, role="student", status="pending_approval", name="po", student_no="3", pw_hash=password.hash("password1")),
        ])
    return bid, e


def test_summary_counts_previews_and_totals(client, app, school, monkeypatch):
    monkeypatch.setattr(admin, "utcnow", lambda: NOW)
    _seed(app)
    r = client.get("/api/admin/summary?preview=2")
    assert r.status_code == 200
    j = r.json()
    assert j["totals"] == {"buildings": 2, "rooms": 3, "nodes": 4, "modems": 2}
    w = j["warnings"]
    assert {k: w[k]["count"] for k in (
        "modem_offline", "unseen", "low_batt", "resync", "clock_stale", "failed", "pending_devices", "pending_approval",
    )} == {  # S10 이 pending_reservations 를 더하므로 전체 키가 아니라 이 8개만 본다
        "modem_offline": 1, "unseen": 3, "low_batt": 2, "resync": 1, "clock_stale": 0,
        "failed": 6, "pending_devices": 1, "pending_approval": 2,
    }
    assert w["modem_offline"]["items"] == [{"modem_id": "m1", "last_seen_at": (NOW - dt.timedelta(days=1)).isoformat(), "buildings": ["E동"]}]
    assert [ (x["room"], x["unit"]) for x in w["unseen"]["items"] ] == [(102, 2), (201, 1)]  # None(보고 없음) 먼저, preview=2
    assert [x["room"] for x in w["low_batt"]["items"]] == [102, 101]  # 오래된 순
    assert len(w["failed"]["items"]) == 2 and w["failed"]["items"][0]["finished_at"] == NOW.isoformat()
    assert w["failed"]["items"][0]["building"] == "E동"
    assert w["pending_devices"]["items"][0]["mac"] == "aabbccddeeff"
    assert [x["email"] for x in w["pending_approval"]["items"]] == ["p1@mju.ac.kr", "p2@mju.ac.kr"]
    assert "pw_hash" not in r.text and j["as_of"] == NOW.isoformat()


def test_summary_defaults_limits_and_auth(client, client_raw, app, school, monkeypatch):
    monkeypatch.setattr(admin, "utcnow", lambda: NOW)  # 시드가 NOW 기준 — 실제 날짜가 지나도 7일 창이 같다
    _seed(app)
    j = client.get("/api/admin/summary").json()
    assert len(j["warnings"]["failed"]["items"]) == 5 and j["warnings"]["failed"]["count"] == 6
    assert client.get("/api/admin/summary?preview=21").status_code == 422
    assert client.get("/api/admin/summary?preview=0").status_code == 422
    assert client_raw.get("/api/admin/summary").status_code == 401
    # 학생(active) 토큰은 403 — pending 계정은 토큰을 못 받으므로 active 학생을 따로 만든다
    with app.state.Session() as s, s.begin():
        s.add(User(email="a@mju.ac.kr", school_id=1, role="student", status="active", name="a", student_no="9", pw_hash=password.hash("password1")))
    with app.state.Session() as s:
        from app.auth import tokens
        from app.settings import Settings

        stu = tokens.jwt_encode(Settings(), s.get(User, "a@mju.ac.kr"))
    assert client.get("/api/admin/summary", headers={"Authorization": f"Bearer {stu}"}).status_code == 403
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_admin_summary.py -q` → FAIL

- [ ] **Step 3: 스키마**

`server/app/schemas.py`:

```python
class ModemBriefOut(BaseModel):
    modem_id: str
    last_seen_at: dt.datetime | None
    buildings: list[str]


class WarningBucket(BaseModel):
    count: int
    items: list[Any]  # 버킷마다 모양이 다르다 (NodeOut / FailedOut / PendingOut / UserOut / ModemBriefOut)


class SummaryTotals(BaseModel):
    buildings: int
    rooms: int
    nodes: int
    modems: int


class SummaryOut(BaseModel):
    as_of: dt.datetime
    totals: SummaryTotals
    warnings: dict[str, WarningBucket]
```

(`from typing import Any, Literal`.)

- [ ] **Step 4: `admin.summary`**

`server/app/domain/admin.py` 에 추가 (import: `from app.auth.models import User`, `from app.lora_service.models import Modem, PendingDevice`, `from sqlalchemy import func`):

```python
PREVIEW_DEFAULT = 5
PREVIEW_MAX = 20
_MIN = dt.datetime.min


def _bucket(items: list, preview: int) -> dict:
    return {"count": len(items), "items": items[:preview]}


def summary(
    s: Session, school_id: int, preview: int = PREVIEW_DEFAULT, now: dt.datetime | None = None
) -> dict:
    """S4b §2.3 — 경고 8종 카운트 + 미리보기, 총계. 요청마다 계산(캐시 없음)."""
    now = now or utcnow()
    nodes = expected_nodes(s, school_id, now=now)
    by_seen = sorted(nodes, key=lambda n: n["last_seen_at"] or _MIN)  # 보고 없음(None) 먼저
    modems = s.scalars(select(Modem).where(Modem.school_id == school_id).order_by(Modem.modem_id)).all()
    bnames: dict[str, list[str]] = {}
    for m in modems:
        bnames[m.modem_id] = list(
            s.scalars(select(Building.name).where(Building.modem_id == m.modem_id).order_by(Building.name))
        )
    offline = [
        {"modem_id": m.modem_id, "last_seen_at": m.last_seen_at, "buildings": bnames[m.modem_id]}
        for m in modems
        if not m.connected
    ]
    failed = failed_outbox(s, school_id, FAILED_DAYS_DEFAULT, None, now)
    mids = {m.modem_id for m in modems}
    pending = [
        S.PendingOut.model_validate(p).model_dump()
        for p in s.scalars(select(PendingDevice).order_by(PendingDevice.first_seen_at))
        if p.modem_id in mids
    ]
    approvals = [
        S.UserOut.model_validate(u).model_dump()
        for u in s.scalars(
            select(User)
            .where(User.school_id == school_id, User.status == "pending_approval")
            .order_by(User.created_at)
        )
    ]
    return {
        "as_of": now,
        "totals": {
            "buildings": s.scalar(select(func.count()).select_from(Building).where(Building.school_id == school_id)),
            "rooms": len({n["room_id"] for n in nodes}),
            "nodes": len(nodes),
            "modems": len(modems),
        },
        "warnings": {
            "modem_offline": _bucket(offline, preview),
            **{w: _bucket([n for n in by_seen if w in n["warnings"]], preview) for w in WARNING_ORDER},
            "failed": _bucket(failed, preview),
            "pending_devices": _bucket(pending, preview),
            "pending_approval": _bucket(approvals, preview),
        },
    }
```

- [ ] **Step 5: 라우터**

`server/app/domain/admin_router.py` 에:

```python
@router.get("/summary", response_model=S.SummaryOut)
def summary(
    preview: int = Query(admin.PREVIEW_DEFAULT, ge=1, le=admin.PREVIEW_MAX),
    user: User = AdminUser, s: Session = _DB,
):
    return admin.summary(s, user.school_id, preview)
```

- [ ] **Step 6: 통과 확인·커밋**

Run: `uv run pytest -q` → PASS. ruff.

```bash
git add app/domain/admin.py app/domain/admin_router.py app/schemas.py tests/test_admin_summary.py
git commit -m "feat(server): GET /api/admin/summary — 경고 8종 카운트+미리보기, 총계"
```

---

### Task 6: 정적 페이지·README·진행도

**Files:**
- Modify: `server/static/index.html`, `server/README.md`, `docs/progress.html`

- [ ] **Step 1: index.html**

CSV 블록 아래 `<h2>관리자 요약</h2><pre id="summary"></pre>` 를 두고 `refresh()` 안에서 `TOKEN` 이 있을 때 `fetch('/api/admin/summary?preview=3', {headers: auth()})` → `JSON.stringify(json, null, 1)` 로 채운다.

- [ ] **Step 2: README**

"관리자 API" 절: `GET /api/admin/summary?preview=` · `/api/admin/nodes?only=&building_id=` · `/api/admin/outbox/failed?days=&limit=` · `/api/buildings/{id}/{slots|reservations|exams|outbox}` 한 줄씩 + spec 링크. 예약·시험 POST 는 `id` 생략 시 서버 채번(응답 `id`).

- [ ] **Step 3: 진행도**

`docs/progress.html` `wj-09` 행의 PR란에 `백엔드: S4b (PR #…)` — 체크는 화면 구현 후. (PR 번호는 PR 생성 후 채움.)

- [ ] **Step 4: 커밋** (저장소 루트)

```bash
git add server/static/index.html server/README.md docs/progress.html
git commit -m "docs(server): 관리자 API README·정적 페이지 요약 블록·진행도(wj-09 백엔드)"
```

---

## Self-review

- **Spec coverage:** §2.1 경고 정의·상수 → T3(`UNSEEN_HOURS`, 판정)·T5(`modem_offline`·`pending_*`). §2.2 `NodeOut`·LEFT JOIN·`unknown` → T3. §2.3 요약(안 2)·정렬·`preview` 한계 → T5. §2.4 `FailedOut`·방 조인 실패 제외 → T1(스키마)·T3(쿼리). §2.5 채번·409·`Enqueued.id` → T2. §2.6 건물 단위 4개·정렬 → T1. §3 스코프·상한 422 → T1·T4·T5 테스트. §4.1 라우터 3개 → T4·T5. §4.2 → T1·T2. §4.3 스키마 → T1·T2·T3·T5. §5 `static`·README → T6. §6 테스트 목록 전부 대응(48 h 경계 T3, 7일 경계 T3, `only`·`building_id` T4, 학생 403·무인증 401 T5, `preview=21` T5, 채번 재사용·소진 T2).
- **Placeholder scan:** 없음.
- **Type consistency:** `admin.expected_nodes(s, school_id, building_id=None, now=None)` T3 정의 = T4·T5 호출(`now` 키워드). `admin.failed_outbox(s, school_id, days, limit, now)` T3 = T4(`days, limit` 위치 인자)·T5(`FAILED_DAYS_DEFAULT, None, now`). `_outbox_rows` T1 정의 = T3 사용. `S.FailedOut` T1 = T3·T4·T5. `NodeOut.warnings: list[str]` T3 = T4 필터·T5 버킷. 테스트 헬퍼 `_building/_status/_outbox` 시그니처 파일마다 동일 사본. S4a 의존 심볼(`scope`, `AdminUser`, `_DB`, `client`·`client_raw`·`school`·`other_admin_hdr`, `User`, `password`) 는 S4a plan T5·T7 정의와 일치.

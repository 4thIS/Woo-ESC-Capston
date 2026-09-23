# S10 — 학생 API·관리자 승인·일일 작업·분석 집계 구현 계획 (plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

- 생성일시: 2026-09-23
- 기준 spec: `docs/specs/2026-09-23-s10-student-analytics-design.md`. **선행: S4a·S4b plan 완료** — `app.deps._DB`, `app.auth.deps.{AdminUser, StudentUser}`, `app.auth.scope.get_scoped`, `domain/router.py` 의 `_free_id`·`ID_MAX`, `domain/admin.py`, conftest `client`(학교 1 관리자)·`school`·`client_raw`·`other_admin_hdr` 를 쓴다.
- 담당: wj @leemonta9482. 브랜치 `feature/s10-student`. 커밋 scope `feat(server)`. PR은 사용자 지시 시. Task 1~7(학생·승인·일일 작업)과 Task 8(분석)은 PR 을 둘로 나눠도 된다.

**Goal:** 학생이 자기 학교의 지금 빈 강의실·방 주간 표를 보고 예약을 신청·취소·체크인하며, 관리자가 승인해 노드로 보내고, 04:00 일일 작업이 만료·승격·재동기·정리를 하고, 관리자가 배정률·공강·예약 통계·갱신 지연 히스토그램을 받는다.

**Architecture:** 순수 계산은 `app/domain/{clock, room_state, reserve, daily, analytics}.py`(세션·값 → 값), 라우터는 `student_router.py`(학생)·`admin_resv_router.py`(예약 승인·jobs·analytics) 두 파일. 시각은 `clock.now_utc()` 한 곳에서만 읽어 테스트가 monkeypatch 한다. `lora_service/api.py` 는 `enqueue_resv_set/resv_del/full_sync` 호출만.

**Tech Stack:** Python 3.12(`zoneinfo`) · uv · FastAPI 0.141 · SQLAlchemy 2 · Alembic · pydantic 2 · pytest · ruff

**Spec:** `docs/specs/2026-09-23-s10-student-analytics-design.md`

## Global Constraints

- `SCHOOL_TZ = Asia/Seoul`. DB naive UTC. 요일·오늘·운영 시간·창 판정은 지역 시각. `DAILY_HOUR_LOCAL = 4`.
- `room_state`: 우선순위 예약(approved) > 시험기간 > 기본. `typeToLayout` 1→1, 2→5, 3→3, 4→4, 5→6, 6→7. 수업(type 1) 슬롯 안 분<50 → 1, ≥50 → 2. 시험기간 + 슬롯 안 → 5. 슬롯 밖 → 4. 빈 = 4. `until` = 다음 변화 시각 또는 자정.
- 신청 제약: 날짜 오늘~+7(KST) 400 · 5분 단위·시작<끝 422 · 15~120분 400 · 과거 400 · 학생당 requested+미래 approved ≤ 3 → 400 · `reservable`·자기 학교 아니면 404 · 슬롯/approved·requested 예약/시험기간 겹침 409. `type=6`, `professor=""`. 승인 시 겹침 재검사 409.
- 전이: `requested → approved|rejected|cancelled|expired`, `approved → cancelled`. 학생 취소: approved 는 시작 전만(409) + `RESV_DEL`. 관리자 취소: 시작 후도 + `RESV_DEL`. 체크인 창 시작−10분 ≤ 지금 ≤ 시작+15분(409).
- 남의 예약은 `label="예약됨"`·`mine=false`·`subject` 없음.
- 일일 작업 5단계(만료·승격(중복 방지)·실패 재동기(24 h, kind 집합, CMD/SET_ROOM/TIME 제외)·정리(90일·90일·7일)·기록), 단계별 트랜잭션·오류 계속. `daily_loop` 60 s tick, 하루 1회(`job_runs`), 수동 실행은 항상.
- 분석: 운영 시간 09~21, 배정 = layout ∈ {1,2,3,5,6,7}, 휴강 3 은 `unused_min`. 예약 통계 상태별 + No-show(`approved`·`requested_by`·종료 지남·미체크인). 지연 = acked·SLOT_SET/RESV_SET·`finished_at−created_at` 초, bin `[0,10,20,30,45,60,90,120,∞)`, p50/p95/max/n/within_30s/within_90s. 기간 기본 30일·최대 90일(422).
- S4b 요약에 `pending_reservations` 버킷 추가(additive). `put_resv` 창 판정 KST.
- 마이그레이션 additive(`web_student`). `lora_service/api.py`·`hub.py`·`lora_proto/` 불변. 기존 테스트 그대로.
- uv only; ruff 100/py312; 명령은 `server/`. 커밋 `feat(server): ...`, AI 표기 없음.

---

## 파일 구조

```
server/app/domain/clock.py            SCHOOL_TZ, now_utc, to_local, to_utc, local_now, local_today, week_start   (T1)
server/app/domain/models.py           Reservation 컬럼 8개, JobRun                                                    (T1)
server/alembic/versions/web_student_<rev>.py                                                                         (T1)
server/app/domain/router.py           put_resv 창 KST                                                                (T1)
server/app/domain/room_state.py       typeToLayout, room_state(pure), load_room_inputs, state_of                     (T2)
server/app/domain/reserve.py          제약 검증·겹침·전이·RESV_DEL                                                  (T3)
server/app/domain/student_router.py   /api/student/*                                                                 (T4, T5)
server/app/domain/admin_resv_router.py /api/admin/reservations|jobs|analytics                                        (T6, T7, T8)
server/app/domain/admin.py            summary 에 pending_reservations                                                (T6)
server/app/domain/daily.py            run_daily, daily_loop                                                          (T7)
server/app/domain/analytics.py        allocation, free_slots, reservation_stats, latency, latency_samples            (T8)
server/app/schemas.py                 T1·T4·T5·T6·T7·T8 스키마
server/app/main.py                    라우터 2개, daily_loop                                                          (T4, T7)
server/tests/conftest.py              student_hdr, other_student_hdr                                                 (T3)
server/tests/test_clock_migration.py T1   test_room_state.py T2   test_reserve.py T3   test_student_rooms.py T4
server/tests/test_student_resv.py T5   test_admin_resv.py T6   test_daily.py T7   test_analytics.py T8
```

공용 테스트 헬퍼(파일마다 상단에 복사):

```python
import datetime as dt

from app.domain import clock
from app.domain.models import Building, ExamPeriod, Reservation, Room, Slot

UTC_NOW = dt.datetime(2026, 9, 23, 1, 30, 0)  # = KST 2026-09-23 10:30 (수요일, day=3)


def _fix_clock(monkeypatch, utc=UTC_NOW):
    monkeypatch.setattr(clock, "now_utc", lambda: utc)


def _building(app, school_id, bld, rooms=((101, 1), (102, 1)), reservable=True):
    with app.state.Session() as s, s.begin():
        b = Building(school_id=school_id, name=f"{bld}동", bld=bld)
        s.add(b)
        s.flush()
        ids = {}
        for room, units in rooms:
            r = Room(building_id=b.id, room=room, units=units, reservable=reservable)
            s.add(r)
            s.flush()
            ids[room] = r.id
        return b.id, ids


def _slot(app, room_id, day, s_h, s_m, e_h, e_m, type_=1, subject="수업"):
    with app.state.Session() as s, s.begin():
        s.add(Slot(room_id=room_id, day=day, s_h=s_h, s_m=s_m, e_h=e_h, e_m=e_m, type=type_,
                   subject=subject, professor=""))


def _resv(app, room_id, date, s_h, s_m, e_h, e_m, id_=None, status="approved", requested_by=None, **kw):
    with app.state.Session() as s, s.begin():
        r = Reservation(id=id_ or (s.query(Reservation).count() + 1), room_id=room_id, date=date,
                        s_h=s_h, s_m=s_m, e_h=e_h, e_m=e_m, type=kw.pop("type_", 6),
                        subject=kw.pop("subject", "대여"), professor="", status=status,
                        requested_by=requested_by, **kw)
        s.add(r)
        s.flush()
        return r.id


def _exam(app, room_id, id_, d1, d2):
    with app.state.Session() as s, s.begin():
        s.add(ExamPeriod(id=id_, room_id=room_id, date_start=d1, date_end=d2))
```

---

### Task 1: `clock.py` · 마이그레이션 `web_student` · `put_resv` KST

**Files:**
- Create: `server/app/domain/clock.py`, `server/alembic/versions/web_student_<rev>.py`
- Modify: `server/app/domain/models.py`, `server/app/domain/router.py`(`put_resv`), `server/app/schemas.py`
- Test: `server/tests/test_clock_migration.py`

**Interfaces:**
- Produces: `clock.SCHOOL_TZ`, `clock.now_utc() -> datetime`(naive UTC; 테스트가 monkeypatch), `clock.to_local(naive_utc) -> datetime`(naive 지역), `clock.to_utc(naive_local) -> datetime`, `clock.local_now()`, `clock.local_today() -> date`, `clock.week_start(date) -> date`(월요일), `clock.local_dt(date, h, m) -> datetime`. `Reservation.{status, requested_by, requested_at, decided_at, decided_by, reject_reason, checked_in_at, cancelled_at}`, `JobRun(id, name, ran_at, result)`. `S.ResvOut` 에 `status` 노출.

- [ ] **Step 1: 실패 테스트**

`server/tests/test_clock_migration.py`:

```python
import datetime as dt

from sqlalchemy import create_engine, inspect

from app.domain import clock
from tests.test_migrations import _upgrade


def test_clock_conversions():
    u = dt.datetime(2026, 9, 22, 16, 30)  # UTC 16:30 = KST 23 일 01:30
    l = clock.to_local(u)
    assert l == dt.datetime(2026, 9, 23, 1, 30) and l.tzinfo is None
    assert clock.to_utc(l) == u
    assert clock.week_start(dt.date(2026, 9, 23)) == dt.date(2026, 9, 21)  # 수 → 월
    assert clock.week_start(dt.date(2026, 9, 21)) == dt.date(2026, 9, 21)
    assert clock.local_dt(dt.date(2026, 9, 23), 9, 5) == dt.datetime(2026, 9, 23, 9, 5)


def test_local_today_uses_now_utc(monkeypatch):
    monkeypatch.setattr(clock, "now_utc", lambda: dt.datetime(2026, 9, 22, 16, 30))
    assert clock.local_today() == dt.date(2026, 9, 23)
    assert clock.local_now() == dt.datetime(2026, 9, 23, 1, 30)


def test_web_student_migration(tmp_path):
    db = tmp_path / "s.db"
    names = _upgrade(db)
    assert "job_runs" in names
    cols = {c["name"] for c in inspect(create_engine(f"sqlite:///{db}")).get_columns("reservations")}
    assert {"status", "requested_by", "requested_at", "decided_at", "decided_by", "reject_reason",
            "checked_in_at", "cancelled_at"} <= cols


def test_put_resv_window_is_local_date(client, app, school, monkeypatch):
    """UTC 22 일 16:30 = KST 23 일 01:30. KST 30 일은 창 안(+7), UTC 기준이면 +8 로 창 밖이 됐을 것."""
    monkeypatch.setattr(clock, "now_utc", lambda: dt.datetime(2026, 9, 22, 16, 30))
    from app.domain.models import Building, Room

    with app.state.Session() as s, s.begin():
        b = Building(school_id=1, name="E동", bld="E")
        s.add(b)
        s.flush()
        r = Room(building_id=b.id, room=101, units=1)
        s.add(r)
        s.flush()
        rid = r.id
    body = {"date": "2026-09-30", "s_h": 9, "s_m": 0, "e_h": 10, "e_m": 0, "type": 6, "subject": "r", "professor": ""}
    res = client.post(f"/api/rooms/{rid}/reservations", json=body)
    assert res.status_code == 200 and res.json()["outbox_ids"]  # E 동은 모뎀 없음 → api.enqueue 는 modem_id None 이어도 행 생성
    assert client.post(f"/api/rooms/{rid}/reservations", json={**body, "date": "2026-10-01"}).json()["outbox_ids"] == []
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_clock_migration.py -q` → FAIL

- [ ] **Step 3: `clock.py`**

```python
"""학교 시간대 (S10 §2.2). DB 는 naive UTC, 판정은 KST. now_utc 만 테스트가 monkeypatch 한다."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from app.db import utcnow

SCHOOL_TZ = ZoneInfo("Asia/Seoul")
DAILY_HOUR_LOCAL = 4


def now_utc() -> dt.datetime:
    return utcnow()


def to_local(u: dt.datetime) -> dt.datetime:
    return u.replace(tzinfo=dt.UTC).astimezone(SCHOOL_TZ).replace(tzinfo=None)


def to_utc(local: dt.datetime) -> dt.datetime:
    return local.replace(tzinfo=SCHOOL_TZ).astimezone(dt.UTC).replace(tzinfo=None)


def local_now() -> dt.datetime:
    return to_local(now_utc())


def local_today() -> dt.date:
    return local_now().date()


def week_start(d: dt.date) -> dt.date:
    return d - dt.timedelta(days=d.weekday())


def local_dt(d: dt.date, h: int, m: int) -> dt.datetime:
    return dt.datetime(d.year, d.month, d.day, h, m)
```

- [ ] **Step 4: 모델·마이그레이션**

`server/app/domain/models.py` `Reservation` 에 (import `from app.db import Base, utcnow`, `Index`):

```python
    # ---- S10 §2.1 학생 신청 ----
    status: Mapped[str] = mapped_column(String, default="approved", server_default="approved")
    requested_by: Mapped[str | None] = mapped_column(ForeignKey("users.email"))
    requested_at: Mapped[dt.datetime | None]
    decided_at: Mapped[dt.datetime | None]
    decided_by: Mapped[str | None] = mapped_column(String)
    reject_reason: Mapped[str | None] = mapped_column(String)
    checked_in_at: Mapped[dt.datetime | None]
    cancelled_at: Mapped[dt.datetime | None]
    __table_args__ = (
        CheckConstraint("id BETWEEN 1 AND 65535"),
        CheckConstraint("status IN ('requested','approved','rejected','cancelled','expired')"),
        Index("ix_resv_room_date", "room_id", "date"),
        Index("ix_resv_requester", "requested_by", "status"),
    )
```

새 모델:

```python
class JobRun(Base):
    __tablename__ = "job_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    ran_at: Mapped[dt.datetime] = mapped_column(default=utcnow)
    result: Mapped[str] = mapped_column(Text)  # JSON
    __table_args__ = (Index("ix_job_runs_name", "name", "ran_at"),)
```

Run: `uv run alembic revision -m "web_student"` → `down_revision` = web_auth rev. `upgrade`: `op.create_table("job_runs", …)` + `op.create_index`, `with op.batch_alter_table("reservations") as b:` 8 컬럼 `add_column`(`status` 는 `nullable=False, server_default="approved"`), `b.create_check_constraint("ck_resv_status", "status IN (...)")`, `b.create_foreign_key("fk_resv_requester", "users", ["requested_by"], ["email"])`, `b.create_index("ix_resv_room_date", ["room_id", "date"])`, `b.create_index("ix_resv_requester", ["requested_by", "status"])`. `downgrade` 역순. (`env.py` 의 `PRAGMA foreign_keys=OFF` 는 S4a 에서 넣음.)

- [ ] **Step 5: `put_resv` KST + `ResvOut.status`**

`server/app/domain/router.py` `put_resv`: `today = dt.datetime.now(dt.UTC).date()` → `today = clock.local_today()` (`from app.domain import clock`). 관리자 생성은 `obj.status = "approved"` 가 기본값이라 그대로.
`server/app/schemas.py` `ResvOut` 에 `status: str = "approved"` 추가.

- [ ] **Step 6: 통과·커밋**

Run: `uv run pytest -q` → PASS. ruff.

```bash
git add app/domain/clock.py app/domain/models.py app/domain/router.py app/schemas.py alembic/versions tests/test_clock_migration.py
git commit -m "feat(server): 학교 시간대 clock, reservations 신청 컬럼·job_runs 마이그레이션, put_resv 창 KST 판정"
```

---

### Task 2: `room_state.py` — v2 §5.3 서버판 + 벡터 8개

**Files:**
- Create: `server/app/domain/room_state.py`
- Test: `server/tests/test_room_state.py`

**Interfaces:**
- Produces: `TYPE_TO_LAYOUT = {1: 1, 2: 5, 3: 3, 4: 4, 5: 6, 6: 7}`, `FREE = 4`; `Span(s: int, e: int, type: int, label: str, mine: bool=False)`(분 단위 0..1440); `room_state(slots: list[Span], resvs: list[Span], in_exam: bool, at_min: int) -> tuple[int, int | None]`(layout, until_min); `load_inputs(s, room_id, date, viewer_email=None) -> tuple[list[Span], list[Span], bool]`; `state_of(s, room_id, at_local) -> tuple[int, int | None]`; `fmt_hhmm(m: int | None) -> str | None`.

- [ ] **Step 1: 실패 테스트**

`server/tests/test_room_state.py`:

```python
import datetime as dt

import pytest

from app.domain import room_state as RS
from app.domain.room_state import Span

M = lambda h, m=0: h * 60 + m  # noqa: E731
SLOTS = [Span(M(9), M(10, 50), 1, "수업"), Span(M(11), M(12), 3, "휴강"), Span(M(13), M(14), 5, "특강"),
         Span(M(15), M(16), 6, "대여"), Span(M(16), M(17), 2, "시험")]


@pytest.mark.parametrize(
    "resvs,in_exam,at,expect",
    [
        ([Span(M(9), M(10), 6, "r")], False, M(9, 30), (7, M(10))),      # 1 예약 우선(대여중), 끝 10:00
        ([], True, M(9, 30), (5, M(10, 50))),                             # 2 시험기간 + 슬롯 안 → 시험중
        ([], False, M(9, 30), (1, M(9, 50))),                             # 3 수업 분<50 → 수업중, 50분에 바뀜
        ([], False, M(9, 50), (2, M(10))),                                # 4 분≥50 → 쉬는시간, 정각에 다시 수업
        ([], False, M(11, 30), (3, M(12))),                               # 5 휴강
        ([], False, M(13, 30), (6, M(14))),                               # 6 특강
        ([], False, M(12, 30), (4, M(13))),                               # 7 슬롯 밖 → 빈, 다음 슬롯 13:00
        ([], False, M(23, 30), (4, None)),                                # 8 자정까지 빈 → until None
    ],
)
def test_room_state_vectors(resvs, in_exam, at, expect):
    assert RS.room_state(SLOTS, resvs, in_exam, at) == expect


def test_room_state_exam_only_during_slots_and_resv_beats_exam():
    assert RS.room_state(SLOTS, [], True, M(12, 30)) == (4, M(13))  # 시험기간이라도 슬롯 밖은 빈
    assert RS.room_state(SLOTS, [Span(M(12), M(13), 6, "r")], True, M(12, 30)) == (7, M(13))
    assert RS.room_state([], [], False, M(10)) == (4, None)
    assert RS.room_state(SLOTS, [Span(M(10, 50), M(11, 30), 6, "r")], False, M(9, 55)) == (2, M(10))  # 쉬는시간 → 정각 수업


def test_type_map_and_fmt():
    assert RS.TYPE_TO_LAYOUT == {1: 1, 2: 5, 3: 3, 4: 4, 5: 6, 6: 7} and RS.FREE == 4
    assert RS.fmt_hhmm(M(9, 5)) == "09:05" and RS.fmt_hhmm(None) is None


def test_load_inputs_and_state_of(app, school):
    _, ids = _building(app, 1, "E")
    rid = ids[101]
    _slot(app, rid, 3, 9, 0, 10, 50)                       # 수요일
    _resv(app, rid, dt.date(2026, 9, 23), 13, 0, 14, 0, id_=1, requested_by="s@mju.ac.kr", subject="스터디")
    _resv(app, rid, dt.date(2026, 9, 23), 15, 0, 16, 0, id_=2, status="requested")  # 신청 중은 제외
    _exam(app, rid, 1, dt.date(2026, 9, 22), dt.date(2026, 9, 24))
    with app.state.Session() as s:
        slots, resvs, in_exam = RS.load_inputs(s, rid, dt.date(2026, 9, 23), viewer_email="s@mju.ac.kr")
        assert [(x.s, x.e, x.type) for x in slots] == [(M(9), M(10, 50), 1)]
        assert [(x.s, x.e, x.label, x.mine) for x in resvs] == [(M(13), M(14), "스터디", True)]
        assert in_exam is True
        assert RS.load_inputs(s, rid, dt.date(2026, 9, 23), viewer_email="other@mju.ac.kr")[1][0].label == "예약됨"
        assert RS.state_of(s, rid, dt.datetime(2026, 9, 23, 9, 30)) == (5, M(10, 50))  # 시험기간
        assert RS.state_of(s, rid, dt.datetime(2026, 9, 25, 9, 30)) == (4, None)       # 금요일 슬롯 없음
```

- [ ] **Step 2: 실패 확인** → `ModuleNotFoundError`

- [ ] **Step 3: 구현**

```python
"""강의실 상태 판정 — v2 §5.3 determineLayout·§5.4 nextChangeAt 의 서버판 (S10 §2.3).
입력은 분 단위 구간 목록이라 펌웨어와 같은 벡터로 검증한다."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import ExamPeriod, Reservation, Slot

TYPE_TO_LAYOUT = {1: 1, 2: 5, 3: 3, 4: 4, 5: 6, 6: 7}
FREE = 4
DAY_MIN = 24 * 60


@dataclass(frozen=True)
class Span:
    s: int  # 시작 분 (0..1439)
    e: int  # 끝 분 (배타)
    type: int
    label: str
    mine: bool = False
    id: int | None = None


def _inside(spans: list[Span], at: int) -> Span | None:
    return next((x for x in spans if x.s <= at < x.e), None)


def _next_start(spans: list[Span], at: int) -> int | None:
    starts = [x.s for x in spans if x.s > at]
    return min(starts) if starts else None


def room_state(slots: list[Span], resvs: list[Span], in_exam: bool, at_min: int) -> tuple[int, int | None]:
    """(layout, until_min). until 은 다음 상태 변화 분; 자정까지 그대로면 None."""
    nxt = min((x for x in (_next_start(slots, at_min), _next_start(resvs, at_min)) if x is not None), default=None)
    r = _inside(resvs, at_min)
    if r is not None:
        return TYPE_TO_LAYOUT[r.type], r.e
    sl = _inside(slots, at_min)
    if sl is None:
        return FREE, nxt
    end = sl.e if nxt is None else min(sl.e, nxt)  # 슬롯 도중 예약이 시작될 수 있다
    if in_exam:
        return 5, end
    if sl.type == 1:
        minute = at_min % 60
        if minute < 50:
            return 1, min(end, at_min - minute + 50)
        return 2, min(end, at_min - minute + 60)
    return TYPE_TO_LAYOUT[sl.type], end


def load_inputs(
    s: Session, room_id: int, date: dt.date, viewer_email: str | None = None
) -> tuple[list[Span], list[Span], bool]:
    """그 날짜의 정규 슬롯(요일)·승인 예약·시험기간 여부. 남의 예약은 label '예약됨'."""
    day = date.isoweekday()
    slots = [
        Span(x.s_h * 60 + x.s_m, x.e_h * 60 + x.e_m, x.type, x.subject)
        for x in s.scalars(select(Slot).where(Slot.room_id == room_id, Slot.day == day).order_by(Slot.s_h, Slot.s_m))
    ]
    resvs = []
    for r in s.scalars(
        select(Reservation)
        .where(Reservation.room_id == room_id, Reservation.date == date, Reservation.status == "approved")
        .order_by(Reservation.s_h, Reservation.s_m)
    ):
        mine = r.requested_by is not None and r.requested_by == viewer_email
        public = r.requested_by is None or mine
        resvs.append(Span(r.s_h * 60 + r.s_m, r.e_h * 60 + r.e_m, r.type, r.subject if public else "예약됨", mine, r.id))
    in_exam = s.scalar(
        select(ExamPeriod.id).where(
            ExamPeriod.room_id == room_id, ExamPeriod.date_start <= date, ExamPeriod.date_end >= date
        ).limit(1)
    ) is not None
    return slots, resvs, in_exam


def state_of(s: Session, room_id: int, at_local: dt.datetime) -> tuple[int, int | None]:
    slots, resvs, in_exam = load_inputs(s, room_id, at_local.date())
    return room_state(slots, resvs, in_exam, at_local.hour * 60 + at_local.minute)


def fmt_hhmm(m: int | None) -> str | None:
    return None if m is None else f"{m // 60:02d}:{m % 60:02d}"
```

벡터 3·4 검산: 09:30 수업 → until 09:50; 09:50 → 쉬는시간 until 10:00 이지만 슬롯 끝 10:50 보다 작으므로 10:00. 벡터 2: 시험기간·슬롯 안 → 5, until 10:50(nxt 11:00 보다 작음). 벡터 8: 23:30 슬롯 밖, 다음 시작 없음 → None.

- [ ] **Step 4: 통과·커밋**

```bash
git add app/domain/room_state.py tests/test_room_state.py
git commit -m "feat(server): room_state — v2 §5.3 determineLayout 서버판 + until, 벡터 8개"
```

---

### Task 3: `reserve.py` — 제약 검증·겹침·전이 + conftest 학생 픽스처

**Files:**
- Create: `server/app/domain/reserve.py`
- Modify: `server/app/schemas.py`(`StudentResvIn`), `server/tests/conftest.py`
- Test: `server/tests/test_reserve.py`

**Interfaces:**
- Produces: `reserve.MAX_ACTIVE = 3`, `MIN_MIN = 15`, `MAX_MIN = 120`, `CHECKIN_BEFORE = 10`, `CHECKIN_AFTER = 15`; `reserve.overlaps(s, room_id, date, s_min, e_min, exclude_id=None) -> bool`; `reserve.validate_request(s, user, room, body: S.StudentResvIn, now_local) -> None`(HTTPException 400/409); `reserve.start_local(r) -> datetime`, `reserve.end_local(r)`; `reserve.cancel(s, r, by_admin: bool, now_local) -> list[int]`(outbox ids; 전이 + 필요시 `RESV_DEL`); `reserve.checkin(s, r, now_local)`; `reserve.approve(s, r, admin_email, now_local) -> list[int]`(겹침 재검사 + 창 안이면 `RESV_SET`); `reserve.reject(s, r, admin_email, reason, now_local)`. conftest: `student_hdr`(s1@mju.ac.kr, active, 학교 1), `other_student_hdr`(s2@mju.ac.kr), `student_hdr_school2`.

- [ ] **Step 1: conftest**

`server/tests/conftest.py` `school` 픽스처의 `add_all` 에 학생 3명 추가:

```python
            User(email="s1@mju.ac.kr", school_id=1, role="student", status="active", name="학생1", student_no="1", pw_hash=password.hash("password1")),
            User(email="s2@mju.ac.kr", school_id=1, role="student", status="active", name="학생2", student_no="2", pw_hash=password.hash("password1")),
            User(email="s3@other.ac.kr", school_id=2, role="student", status="active", name="타교생", student_no="3", pw_hash=password.hash("password1")),
```

픽스처:

```python
@pytest.fixture
def student_hdr(app, school):
    return _hdr(app, "s1@mju.ac.kr")


@pytest.fixture
def other_student_hdr(app, school):
    return _hdr(app, "s2@mju.ac.kr")


@pytest.fixture
def student_hdr_school2(app, school):
    return _hdr(app, "s3@other.ac.kr")
```

(S4a·S4b 테스트 중 `users` 를 세는 것이 있으면 — `test_auth_admin_cli.py::test_list_is_school_scoped_and_filterable` 는 자체 `seed` 라 무관 — 수정 없음.)

- [ ] **Step 2: 실패 테스트**

`server/tests/test_reserve.py` (공용 헬퍼 복사 + `from fastapi import HTTPException`, `from app import schemas as S`, `from app.auth.models import User`, `from app.domain import reserve`, `from app.domain.models import Room`, `from app.lora_service.models import Outbox`, `from sqlalchemy import select`):

```python
def _body(date="2026-09-24", s_h=13, s_m=0, e_h=14, e_m=0, subject="스터디"):
    return S.StudentResvIn(date=dt.date.fromisoformat(date), s_h=s_h, s_m=s_m, e_h=e_h, e_m=e_m, subject=subject)


def _check(app, rid, body, email="s1@mju.ac.kr"):
    with app.state.Session() as s:
        user, room = s.get(User, email), s.get(Room, rid)
        try:
            reserve.validate_request(s, user, room, body, clock.local_now())
            return 200
        except HTTPException as e:
            return e.status_code


def test_constraints(app, school, monkeypatch):
    _fix_clock(monkeypatch)  # KST 9/23 10:30
    _, ids = _building(app, 1, "E")
    rid = ids[101]
    assert _check(app, rid, _body()) == 200
    assert _check(app, rid, _body(date="2026-09-22")) == 400          # 과거 날짜
    assert _check(app, rid, _body(date="2026-10-01")) == 400          # +8
    assert _check(app, rid, _body(date="2026-09-30")) == 200          # +7
    assert _check(app, rid, _body(date="2026-09-23", s_h=10, s_m=0, e_h=11)) == 400  # 시작 지남
    assert _check(app, rid, _body(date="2026-09-23", s_h=10, s_m=35, e_h=11)) == 200
    assert _check(app, rid, _body(s_h=13, s_m=0, e_h=13, e_m=10)) == 400  # 10 분
    assert _check(app, rid, _body(s_h=13, s_m=0, e_h=15, e_m=30)) == 400  # 150 분
    _slot(app, rid, 4, 14, 0, 15, 0)                                     # 목 14~15 정규
    assert _check(app, rid, _body(s_h=13, s_m=30, e_h=14, e_m=30)) == 409  # 슬롯 겹침
    _exam(app, rid, 1, dt.date(2026, 9, 24), dt.date(2026, 9, 24))
    assert _check(app, rid, _body(s_h=15, s_m=0, e_h=16, e_m=0)) == 200   # 시험기간이라도 슬롯 밖은 OK
    _resv(app, rid, dt.date(2026, 9, 24), 16, 0, 17, 0, id_=1, status="requested", requested_by="s2@mju.ac.kr")
    assert _check(app, rid, _body(s_h=16, s_m=30, e_h=17, e_m=30)) == 409  # requested 도 겹침(선착순)
    for i, d in enumerate(("2026-09-25", "2026-09-26", "2026-09-27"), start=2):
        _resv(app, rid, dt.date.fromisoformat(d), 9, 0, 10, 0, id_=i, status="approved" if i == 2 else "requested", requested_by="s1@mju.ac.kr")
    assert _check(app, rid, _body(date="2026-09-28")) == 400          # 4 건째
    assert _check(app, rid, _body(date="2026-09-28"), email="s2@mju.ac.kr") == 200


def test_transitions(app, school, monkeypatch):
    _fix_clock(monkeypatch)
    _, ids = _building(app, 1, "E")
    rid = ids[101]
    a = _resv(app, rid, dt.date(2026, 9, 24), 13, 0, 14, 0, id_=1, status="requested", requested_by="s1@mju.ac.kr", requested_at=UTC_NOW)
    b = _resv(app, rid, dt.date(2026, 9, 23), 9, 0, 10, 0, id_=2, status="approved", requested_by="s1@mju.ac.kr")  # 이미 시작
    with app.state.Session() as s, s.begin():
        r = s.get(Reservation, a)
        reserve.cancel(s, r, by_admin=False, now_local=clock.local_now())
        assert r.status == "cancelled" and r.cancelled_at is not None
        r2 = s.get(Reservation, b)
        with pytest.raises(HTTPException) as e:
            reserve.cancel(s, r2, by_admin=False, now_local=clock.local_now())
        assert e.value.status_code == 409
        with pytest.raises(HTTPException):
            reserve.checkin(s, r2, clock.local_now())  # 09:00 시작, 지금 10:30 → 창 밖
        reserve.checkin(s, r2, dt.datetime(2026, 9, 23, 9, 14))
        assert r2.checked_in_at is not None
        with pytest.raises(HTTPException):
            reserve.checkin(s, r2, dt.datetime(2026, 9, 23, 9, 14))  # 재체크인


def test_approve_reject_enqueue(db, hub, app, school, monkeypatch):
    """approve 는 창 안이면 RESV_SET(유닛 수만큼), 창 밖이면 없음. 겹침 재검사 409."""
    _fix_clock(monkeypatch)
    _, ids = _building(app, 1, "E", rooms=((301, 2),))
    rid = ids[301]
    a = _resv(app, rid, dt.date(2026, 9, 24), 13, 0, 14, 0, id_=1, status="requested", requested_by="s1@mju.ac.kr")
    far = _resv(app, rid, dt.date(2026, 10, 15), 13, 0, 14, 0, id_=2, status="requested", requested_by="s1@mju.ac.kr")
    with app.state.Session() as s, s.begin():
        ids_ = reserve.approve(s, s.get(Reservation, a), "admin@mju.ac.kr", clock.local_now())
        assert len(ids_) == 2 and s.get(Reservation, a).status == "approved"
        assert reserve.approve(s, s.get(Reservation, far), "admin@mju.ac.kr", clock.local_now()) == []
    _resv(app, rid, dt.date(2026, 9, 24), 13, 30, 14, 30, id_=3, status="requested", requested_by="s2@mju.ac.kr")
    with app.state.Session() as s, s.begin():
        with pytest.raises(HTTPException) as e:
            reserve.approve(s, s.get(Reservation, 3), "admin@mju.ac.kr", clock.local_now())
        assert e.value.status_code == 409
        r = s.get(Reservation, 3)
        reserve.reject(s, r, "admin@mju.ac.kr", "겹침", clock.local_now())
        assert r.status == "rejected" and r.reject_reason == "겹침"
        # 관리자 취소는 RESV_DEL
        n = len(reserve.cancel(s, s.get(Reservation, a), by_admin=True, now_local=clock.local_now()))
        assert n == 2
    with db() as s:
        assert [o.type for o in s.scalars(select(Outbox).order_by(Outbox.id))] == ["RESV_SET"] * 2 + ["RESV_DEL"] * 2
```

`db` 픽스처(conftest)는 `FakeTopo` 에 `("E", 301)` units=2 modem "m1" 이 있으므로 `api.enqueue_*` 가 동작한다 — `_building` 이 만드는 방 번호를 301 로 맞춘 이유.

- [ ] **Step 3: 실패 확인** → `ModuleNotFoundError`

- [ ] **Step 4: 스키마**

`server/app/schemas.py`:

```python
class StudentResvIn(BaseModel):
    date: dt.date
    s_h: int = Field(ge=0, le=23)
    s_m: int = Field(ge=0, le=59, multiple_of=5)
    e_h: int = Field(ge=0, le=23)
    e_m: int = Field(ge=0, le=59, multiple_of=5)
    subject: str = Field(min_length=1)

    @field_validator("subject")
    @classmethod
    def _subj(cls, v: str) -> str:
        return _bytes_max(v, P.SUBJ_MAX, "subject")

    @model_validator(mode="after")
    def _order(self):
        if (self.s_h, self.s_m) >= (self.e_h, self.e_m):
            raise ValueError("시작 < 끝")
        return self
```

(`from pydantic import model_validator`.)

- [ ] **Step 5: 구현**

`server/app/domain/reserve.py`:

```python
"""학생 예약 제약·전이 (S10 §2.4·§4). 라우터(학생·관리자)가 공유. outbox 는 approve/cancel 에서만."""

from __future__ import annotations

import datetime as dt

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import schemas as S
from app.auth.models import User
from app.domain import clock
from app.domain.models import Building, ExamPeriod, Reservation, Room, Slot
from app.domain.topology import RESV_HORIZON_DAYS
from app.lora_service import api

MAX_ACTIVE = 3
MIN_MIN, MAX_MIN = 15, 120
CHECKIN_BEFORE, CHECKIN_AFTER = 10, 15  # 분
STUDENT_TYPE = 6  # 대여


def start_local(r: Reservation) -> dt.datetime:
    return clock.local_dt(r.date, r.s_h, r.s_m)


def end_local(r: Reservation) -> dt.datetime:
    return clock.local_dt(r.date, r.e_h, r.e_m)


def _addr(s: Session, r: Reservation) -> tuple[str, int]:
    room = s.get(Room, r.room_id)
    return s.get(Building, room.building_id).bld, room.room


def overlaps(s: Session, room_id: int, date: dt.date, s_min: int, e_min: int, exclude_id: int | None = None) -> bool:
    """정규 슬롯(그 요일, type 무관)·approved/requested 예약·시험기간(그 날짜 슬롯)과 1분이라도 겹치면 True."""
    day = date.isoweekday()
    for x in s.scalars(select(Slot).where(Slot.room_id == room_id, Slot.day == day)):
        if x.s_h * 60 + x.s_m < e_min and s_min < x.e_h * 60 + x.e_m:
            return True  # 시험기간은 슬롯이 있을 때만 의미 — 슬롯 겹침에 이미 포함
    q = select(Reservation).where(
        Reservation.room_id == room_id,
        Reservation.date == date,
        Reservation.status.in_(("approved", "requested")),
    )
    if exclude_id is not None:
        q = q.where(Reservation.id != exclude_id)
    return any(x.s_h * 60 + x.s_m < e_min and s_min < x.e_h * 60 + x.e_m for x in s.scalars(q))


def validate_request(s: Session, user: User, room: Room, body: S.StudentResvIn, now_local: dt.datetime) -> None:
    today = now_local.date()
    if not (today <= body.date <= today + dt.timedelta(days=RESV_HORIZON_DAYS)):
        raise HTTPException(400, f"오늘부터 {RESV_HORIZON_DAYS}일 안에만 신청할 수 있습니다")
    s_min, e_min = body.s_h * 60 + body.s_m, body.e_h * 60 + body.e_m
    if not (MIN_MIN <= e_min - s_min <= MAX_MIN):
        raise HTTPException(400, f"{MIN_MIN}분 이상 {MAX_MIN}분 이하로 신청하세요")
    if clock.local_dt(body.date, body.s_h, body.s_m) <= now_local:
        raise HTTPException(400, "이미 지난 시간입니다")
    active = s.scalar(
        select(func.count()).select_from(Reservation).where(
            Reservation.requested_by == user.email,
            (Reservation.status == "requested")
            | ((Reservation.status == "approved") & (Reservation.date >= today)),
        )
    )
    if active >= MAX_ACTIVE:
        raise HTTPException(400, f"진행 중인 신청은 {MAX_ACTIVE}건까지입니다")
    if overlaps(s, room.id, body.date, s_min, e_min):
        raise HTTPException(409, "그 시간에는 이미 수업·예약이 있습니다")


def _require(r: Reservation, *states: str) -> None:
    if r.status not in states:
        raise HTTPException(409, f"{r.status} 상태에서는 불가")


def approve(s: Session, r: Reservation, admin_email: str, now_local: dt.datetime) -> list[int]:
    _require(r, "requested")
    if overlaps(s, r.room_id, r.date, r.s_h * 60 + r.s_m, r.e_h * 60 + r.e_m, exclude_id=r.id):
        raise HTTPException(409, "그 시간에 다른 예약·수업이 생겼습니다")
    r.status, r.decided_at, r.decided_by = "approved", clock.to_utc(now_local), admin_email
    s.flush()
    today = now_local.date()
    if today <= r.date <= today + dt.timedelta(days=RESV_HORIZON_DAYS):
        bld, room = _addr(s, r)
        return api.enqueue_resv_set(bld, room, r.id, r.date, (r.s_h, r.s_m), (r.e_h, r.e_m), r.type, r.subject, r.professor)
    return []  # 창 밖 — 일일 작업이 승격 (S10 §2.5)


def reject(s: Session, r: Reservation, admin_email: str, reason: str, now_local: dt.datetime) -> None:
    _require(r, "requested")
    r.status, r.decided_at, r.decided_by, r.reject_reason = "rejected", clock.to_utc(now_local), admin_email, reason


def cancel(s: Session, r: Reservation, *, by_admin: bool, now_local: dt.datetime) -> list[int]:
    _require(r, "requested", "approved")
    was_approved = r.status == "approved"
    if was_approved and not by_admin and start_local(r) <= now_local:
        raise HTTPException(409, "시작된 예약은 취소할 수 없습니다")
    r.status, r.cancelled_at = "cancelled", clock.to_utc(now_local)
    s.flush()
    if was_approved:
        bld, room = _addr(s, r)
        return api.enqueue_resv_del(bld, room, r.id)
    return []


def checkin(s: Session, r: Reservation, now_local: dt.datetime) -> None:
    _require(r, "approved")
    if r.checked_in_at is not None:
        raise HTTPException(409, "이미 체크인했습니다")
    st = start_local(r)
    if not (st - dt.timedelta(minutes=CHECKIN_BEFORE) <= now_local <= st + dt.timedelta(minutes=CHECKIN_AFTER)):
        raise HTTPException(409, f"체크인은 시작 {CHECKIN_BEFORE}분 전부터 {CHECKIN_AFTER}분 후까지입니다")
    r.checked_in_at = clock.to_utc(now_local)
```

`approve`·`cancel` 은 도메인 세션에서 `flush` 뒤 `api.enqueue_*`(자체 세션) 를 부른다 — S2 "enqueue 먼저" 규칙과 반대지만, 여기서는 도메인 write 가 UPDATE 한 행뿐이고 호출자가 곧 commit 하므로 WAL 락 대기는 ms. (#9 원자화가 들어오면 `session=s` 로 바꾼다.)

- [ ] **Step 6: 통과·커밋**

```bash
git add app/domain/reserve.py app/schemas.py tests/conftest.py tests/test_reserve.py
git commit -m "feat(server): reserve — 학생 신청 제약·겹침·승인/거절/취소/체크인 전이, 학생 테스트 픽스처"
```

---

### Task 4: 학생 조회 — `/api/student/rooms/free`, `/rooms`, `/rooms/{id}/week`

**Files:**
- Create: `server/app/domain/student_router.py`
- Modify: `server/app/schemas.py`, `server/app/main.py`
- Test: `server/tests/test_student_rooms.py`

**Interfaces:**
- Produces: `student_router.router`(prefix `/api/student`, `dependencies=[StudentUser]`); `S.RoomStateOut(room_id, building_id, building, bld, room, layout, until)`, `S.FreeRoomOut(RoomStateOut 와 동일 필드, `free_until`)`, `S.ResvPublicOut(id, date, s_h, s_m, e_h, e_m, mine, label)`, `S.WeekOut(room, week_start, slots, reservations, exams)`; `student_router._student_room(s, user, room_id) -> Room`(404).

- [ ] **Step 1: 실패 테스트**

`server/tests/test_student_rooms.py` (공용 헬퍼 복사):

```python
def test_free_rooms_now_and_at(client, app, school, student_hdr, monkeypatch):
    _fix_clock(monkeypatch)  # KST 수 10:30
    _, ids = _building(app, 1, "E", rooms=((101, 1), (102, 1), (103, 1)))
    _building(app, 1, "G", rooms=((201, 1),), reservable=False)   # 예약 불가 방 제외
    _building(app, 2, "F", rooms=((101, 1),))                      # 타교 제외
    _slot(app, ids[101], 3, 9, 0, 10, 50)                          # 101 수업 중
    _resv(app, ids[102], dt.date(2026, 9, 23), 10, 0, 11, 0, id_=1)  # 102 대여 중
    _slot(app, ids[103], 3, 13, 0, 14, 0)                          # 103 비어 있음, 13:00 까지
    r = client.get("/api/student/rooms/free", headers=student_hdr)
    assert r.status_code == 200
    assert [(x["room"], x["layout"], x["free_until"]) for x in r.json()] == [(103, 4, "13:00")]
    r = client.get("/api/student/rooms/free?at=2026-09-23T11:00:00", headers=student_hdr)
    assert [x["room"] for x in r.json()] == [101, 102, 103]
    assert client.get("/api/student/rooms/free").status_code == 401
    assert client.get("/api/student/rooms/free", headers=client.headers).status_code == 403  # 관리자


def test_rooms_with_state(client, app, school, student_hdr, monkeypatch):
    _fix_clock(monkeypatch)
    bid, ids = _building(app, 1, "E", rooms=((101, 1), (102, 1)))
    _slot(app, ids[101], 3, 9, 0, 10, 50)
    r = client.get(f"/api/student/rooms?building_id={bid}", headers=student_hdr)
    assert [(x["room"], x["layout"], x["until"]) for x in r.json()] == [(101, 1, "10:50"), (102, 4, None)]
    assert r.json()[0]["building"] == "E동" and r.json()[0]["bld"] == "E"


def test_week_hides_others_and_scopes(client, app, school, student_hdr, other_student_hdr, student_hdr_school2, monkeypatch):
    _fix_clock(monkeypatch)
    _, ids = _building(app, 1, "E")
    rid = ids[101]
    _slot(app, rid, 1, 9, 0, 10, 0)
    _resv(app, rid, dt.date(2026, 9, 24), 13, 0, 14, 0, id_=1, requested_by="s1@mju.ac.kr", subject="스터디")
    _resv(app, rid, dt.date(2026, 9, 25), 13, 0, 14, 0, id_=2, subject="관리자예약")
    _resv(app, rid, dt.date(2026, 9, 30), 13, 0, 14, 0, id_=3)      # 다음 주 → 제외
    _resv(app, rid, dt.date(2026, 9, 26), 9, 0, 10, 0, id_=4, status="requested", requested_by="s1@mju.ac.kr")  # 신청 중 → 제외
    _exam(app, rid, 1, dt.date(2026, 9, 21), dt.date(2026, 9, 22))
    r = client.get(f"/api/student/rooms/{rid}/week", headers=student_hdr)
    j = r.json()
    assert r.status_code == 200 and j["week_start"] == "2026-09-21" and j["room"]["room"] == 101
    assert [x["day"] for x in j["slots"]] == [1]
    assert [(x["id"], x["mine"], x["label"]) for x in j["reservations"]] == [(1, True, "스터디"), (2, False, "관리자예약")]
    assert [x["id"] for x in j["exams"]] == [1]
    j2 = client.get(f"/api/student/rooms/{rid}/week", headers=other_student_hdr).json()
    assert [(x["id"], x["mine"], x["label"]) for x in j2["reservations"]] == [(1, False, "예약됨"), (2, False, "관리자예약")]
    assert client.get(f"/api/student/rooms/{rid}/week?date=2026-09-30", headers=student_hdr).json()["reservations"][0]["id"] == 3
    assert client.get(f"/api/student/rooms/{rid}/week", headers=student_hdr_school2).status_code == 404
    assert client.get("/api/student/rooms/999/week", headers=student_hdr).status_code == 404
```

- [ ] **Step 2: 실패 확인** → 404

- [ ] **Step 3: 스키마**

```python
class RoomStateOut(BaseModel):
    room_id: int
    building_id: int
    building: str
    bld: str
    room: int
    layout: int
    until: str | None


class FreeRoomOut(BaseModel):
    room_id: int
    building_id: int
    building: str
    bld: str
    room: int
    layout: int
    free_until: str | None


class ResvPublicOut(BaseModel):
    id: int
    date: dt.date
    s_h: int
    s_m: int
    e_h: int
    e_m: int
    mine: bool
    label: str


class WeekOut(BaseModel):
    room: RoomStateOut
    week_start: dt.date
    slots: list[SlotOut]
    reservations: list[ResvPublicOut]
    exams: list[ExamOut]
```

- [ ] **Step 4: 라우터**

`server/app/domain/student_router.py`:

```python
"""학생 API (S10 §4.1). require_student + 자기 학교 reservable 방. outbox 는 취소(T5)에서만."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas as S
from app.auth.deps import StudentUser
from app.auth.models import User
from app.deps import _DB
from app.domain import clock, room_state
from app.domain.models import Building, ExamPeriod, Reservation, Room, Slot

router = APIRouter(prefix="/api/student", dependencies=[StudentUser])


def _rooms_q(user: User, building_id: int | None):
    q = (
        select(Room, Building)
        .join(Building, Room.building_id == Building.id)
        .where(Building.school_id == user.school_id, Room.reservable.is_(True))
        .order_by(Building.bld, Room.room)
    )
    return q if building_id is None else q.where(Building.id == building_id)


def _student_room(s: Session, user: User, room_id: int) -> tuple[Room, Building]:
    room = s.get(Room, room_id)
    b = s.get(Building, room.building_id) if room else None
    if room is None or b.school_id != user.school_id or not room.reservable:
        raise HTTPException(404, f"rooms {room_id} 없음")
    return room, b


def _state_out(s: Session, room: Room, b: Building, at: dt.datetime) -> dict:
    layout, until = room_state.state_of(s, room.id, at)
    return {
        "room_id": room.id, "building_id": b.id, "building": b.name, "bld": b.bld, "room": room.room,
        "layout": layout, "until": room_state.fmt_hhmm(until),
    }


@router.get("/rooms/free", response_model=list[S.FreeRoomOut])
def free_rooms(at: dt.datetime | None = None, building_id: int | None = None, user: User = StudentUser, s: Session = _DB):
    at_local = at or clock.local_now()
    out = []
    for room, b in s.execute(_rooms_q(user, building_id)).all():
        st = _state_out(s, room, b, at_local)
        if st["layout"] == room_state.FREE:
            out.append({**st, "free_until": st.pop("until")})
    return out


@router.get("/rooms", response_model=list[S.RoomStateOut])
def rooms(building_id: int | None = None, user: User = StudentUser, s: Session = _DB):
    now = clock.local_now()
    return [_state_out(s, room, b, now) for room, b in s.execute(_rooms_q(user, building_id)).all()]


@router.get("/rooms/{id}/week", response_model=S.WeekOut)
def week(id: int, date: dt.date | None = None, user: User = StudentUser, s: Session = _DB):
    room, b = _student_room(s, user, id)
    start = clock.week_start(date or clock.local_today())
    end = start + dt.timedelta(days=6)
    resvs = []
    for r in s.scalars(
        select(Reservation)
        .where(Reservation.room_id == id, Reservation.status == "approved", Reservation.date.between(start, end))
        .order_by(Reservation.date, Reservation.s_h, Reservation.s_m)
    ):
        mine = r.requested_by is not None and r.requested_by == user.email
        resvs.append({
            "id": r.id, "date": r.date, "s_h": r.s_h, "s_m": r.s_m, "e_h": r.e_h, "e_m": r.e_m,
            "mine": mine, "label": r.subject if (mine or r.requested_by is None) else "예약됨",
        })
    return {
        "room": _state_out(s, room, b, clock.local_now()),
        "week_start": start,
        "slots": s.scalars(select(Slot).where(Slot.room_id == id).order_by(Slot.day, Slot.s_h, Slot.s_m)).all(),
        "reservations": resvs,
        "exams": s.scalars(
            select(ExamPeriod).where(ExamPeriod.room_id == id, ExamPeriod.date_start <= end, ExamPeriod.date_end >= start)
            .order_by(ExamPeriod.date_start)
        ).all(),
    }
```

`server/app/main.py`: `from app.domain.student_router import router as student_router` + `app.include_router(student_router)`.

- [ ] **Step 5: 통과·커밋**

```bash
git add app/domain/student_router.py app/schemas.py app/main.py tests/test_student_rooms.py
git commit -m "feat(server): 학생 API — 지금 빈 강의실·방 상태·주간 표(남의 예약은 '예약됨')"
```

---

### Task 5: 학생 예약 — 신청·내 목록·취소·체크인

**Files:**
- Modify: `server/app/domain/student_router.py`, `server/app/schemas.py`(`ResvMineOut`)
- Test: `server/tests/test_student_resv.py`

**Interfaces:**
- Produces: `S.ResvMineOut(ResvOut + status, requested_at, decided_at, reject_reason, checked_in_at, cancelled_at, room_id, building, room)`; `POST /api/student/rooms/{id}/reservations`(201), `GET /api/student/me/reservations?status=`, `POST /api/student/me/reservations/{id}/{cancel|checkin}`; `student_router._mine_out(s, r) -> dict`.

- [ ] **Step 1: 실패 테스트**

`server/tests/test_student_resv.py` (공용 헬퍼 복사 + `from app.lora_service.models import Outbox`, `from sqlalchemy import select`):

```python
BODY = {"date": "2026-09-24", "s_h": 13, "s_m": 0, "e_h": 14, "e_m": 0, "subject": "스터디"}


def test_request_list_cancel(client, app, school, student_hdr, other_student_hdr, monkeypatch):
    _fix_clock(monkeypatch)
    _, ids = _building(app, 1, "E")
    rid = ids[101]
    r = client.post(f"/api/student/rooms/{rid}/reservations", json=BODY, headers=student_hdr)
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["status"] == "requested" and j["id"] == 1 and j["type"] == 6 and j["room"] == 101 and j["building"] == "E동"
    assert client.post(f"/api/student/rooms/{rid}/reservations", json=BODY, headers=other_student_hdr).status_code == 409  # 선착순
    assert client.post(f"/api/student/rooms/{rid}/reservations", json={**BODY, "e_m": 3}, headers=student_hdr).status_code == 422
    assert client.post(f"/api/student/rooms/{rid}/reservations", json={**BODY, "date": "2026-10-05"}, headers=student_hdr).status_code == 400
    assert client.post("/api/student/rooms/999/reservations", json=BODY, headers=student_hdr).status_code == 404
    mine = client.get("/api/student/me/reservations", headers=student_hdr).json()
    assert [x["id"] for x in mine] == [1] and "requested_at" in mine[0]
    assert client.get("/api/student/me/reservations", headers=other_student_hdr).json() == []
    assert client.post("/api/student/me/reservations/1/cancel", headers=other_student_hdr).status_code == 404
    r = client.post("/api/student/me/reservations/1/cancel", headers=student_hdr)
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert client.get("/api/student/me/reservations", headers=student_hdr).json() == []          # 기본 진행 중만
    assert [x["id"] for x in client.get("/api/student/me/reservations?status=cancelled", headers=student_hdr).json()] == [1]
    assert client.post("/api/student/me/reservations/1/cancel", headers=student_hdr).status_code == 409


def test_cancel_approved_sends_resv_del_and_checkin_window(client, live, app, school, student_hdr, monkeypatch):
    _fix_clock(monkeypatch)
    _, ids = _building(app, 1, "E", rooms=((301, 2),))
    rid = ids[301]
    a = _resv(app, rid, dt.date(2026, 9, 24), 13, 0, 14, 0, id_=1, status="approved", requested_by="s1@mju.ac.kr")
    b = _resv(app, rid, dt.date(2026, 9, 23), 10, 25, 11, 0, id_=2, status="approved", requested_by="s1@mju.ac.kr")  # 시작 5분 전
    r = client.post(f"/api/student/me/reservations/{b}/checkin", headers=student_hdr)
    assert r.status_code == 200 and r.json()["checked_in_at"]
    assert client.post(f"/api/student/me/reservations/{a}/checkin", headers=student_hdr).status_code == 409  # 내일
    assert client.post(f"/api/student/me/reservations/{b}/cancel", headers=student_hdr).status_code == 409  # 10:25 시작, 지금 10:30 → 이미 시작
    r = client.post(f"/api/student/me/reservations/{a}/cancel", headers=student_hdr)
    assert r.status_code == 200
    with live() as s:
        assert [o.type for o in s.scalars(select(Outbox))] == ["RESV_DEL", "RESV_DEL"]  # 유닛 2
```

`live` 픽스처가 `FakeTopo("E", 301, units=2, "m1")` 를 준다.

- [ ] **Step 2: 실패 확인** → 404/405

- [ ] **Step 3: 스키마**

```python
class ResvMineOut(ResvOut):
    requested_at: dt.datetime | None
    decided_at: dt.datetime | None
    reject_reason: str | None
    checked_in_at: dt.datetime | None
    cancelled_at: dt.datetime | None
    room_id: int
    building: str
    room: int
```

- [ ] **Step 4: 라우터**

`student_router.py` 에 (import `from app.domain import reserve`, `from app.domain.router import _free_id`):

```python
def _mine_out(s: Session, r: Reservation) -> dict:
    room = s.get(Room, r.room_id)
    b = s.get(Building, room.building_id)
    return {**S.ResvOut.model_validate(r).model_dump(), "requested_at": r.requested_at, "decided_at": r.decided_at,
            "reject_reason": r.reject_reason, "checked_in_at": r.checked_in_at, "cancelled_at": r.cancelled_at,
            "room_id": room.id, "building": b.name, "room": room.room}


def _my_resv(s: Session, user: User, id: int) -> Reservation:
    r = s.get(Reservation, id)
    if r is None or r.requested_by != user.email:
        raise HTTPException(404, "예약 없음")
    return r


@router.post("/rooms/{id}/reservations", response_model=S.ResvMineOut, status_code=201)
def request_resv(id: int, body: S.StudentResvIn, user: User = StudentUser, s: Session = _DB):
    room, _ = _student_room(s, user, id)
    now = clock.local_now()
    reserve.validate_request(s, user, room, body, now)
    r = Reservation(
        id=_free_id(s, Reservation), room_id=id, date=body.date, s_h=body.s_h, s_m=body.s_m, e_h=body.e_h, e_m=body.e_m,
        type=reserve.STUDENT_TYPE, subject=body.subject, professor="", status="requested",
        requested_by=user.email, requested_at=clock.to_utc(now),
    )
    s.add(r)
    s.flush()
    return _mine_out(s, r)


@router.get("/me/reservations", response_model=list[S.ResvMineOut])
def my_reservations(status: str | None = None, user: User = StudentUser, s: Session = _DB):
    states = status.split(",") if status else ["requested", "approved"]
    q = (select(Reservation).where(Reservation.requested_by == user.email, Reservation.status.in_(states))
         .order_by(Reservation.date, Reservation.s_h, Reservation.s_m))
    return [_mine_out(s, r) for r in s.scalars(q)]


@router.post("/me/reservations/{id}/cancel", response_model=S.ResvMineOut)
def cancel_resv(id: int, user: User = StudentUser, s: Session = _DB):
    r = _my_resv(s, user, id)
    reserve.cancel(s, r, by_admin=False, now_local=clock.local_now())
    return _mine_out(s, r)


@router.post("/me/reservations/{id}/checkin", response_model=S.ResvMineOut)
def checkin_resv(id: int, user: User = StudentUser, s: Session = _DB):
    r = _my_resv(s, user, id)
    reserve.checkin(s, r, clock.local_now())
    return _mine_out(s, r)
```

- [ ] **Step 5: 통과·커밋**

```bash
git add app/domain/student_router.py app/schemas.py tests/test_student_resv.py
git commit -m "feat(server): 학생 예약 — 신청(제약·선착순)·내 목록·취소(RESV_DEL)·체크인"
```

---

### Task 6: 관리자 예약 승인 + 요약 `pending_reservations`

**Files:**
- Create: `server/app/domain/admin_resv_router.py`
- Modify: `server/app/domain/admin.py`, `server/app/schemas.py`(`RequesterOut`, `ResvAdminOut`, `RejectIn` 재사용), `server/app/main.py`
- Test: `server/tests/test_admin_resv.py`

**Interfaces:**
- Produces: `admin_resv_router.router`(prefix `/api/admin`, `dependencies=[AdminUser]`); `GET /reservations?status=&building_id=&date_from=&date_to=`, `POST /reservations/{id}/{approve|reject|cancel}`; `admin.pending_reservations(s, school_id) -> list[dict]`(ResvAdminOut, 오래된 순); `S.ResvAdminOut(ResvMineOut + requester: RequesterOut | None)`.

- [ ] **Step 1: 실패 테스트**

`server/tests/test_admin_resv.py` (공용 헬퍼 복사 + `from sqlalchemy import select`, `from app.lora_service.models import Outbox`):

```python
def test_list_scope_and_filters(client, app, school, other_admin_hdr, monkeypatch):
    _fix_clock(monkeypatch)
    bid, ids = _building(app, 1, "E")
    _, ids2 = _building(app, 2, "F")
    _resv(app, ids[101], dt.date(2026, 9, 24), 13, 0, 14, 0, id_=1, status="requested", requested_by="s1@mju.ac.kr", requested_at=UTC_NOW)
    _resv(app, ids[101], dt.date(2026, 9, 25), 13, 0, 14, 0, id_=2, status="approved")
    _resv(app, ids2[101], dt.date(2026, 9, 24), 13, 0, 14, 0, id_=3, status="requested", requested_by="s3@other.ac.kr")
    r = client.get("/api/admin/reservations")
    assert r.status_code == 200 and [x["id"] for x in r.json()] == [1]
    assert r.json()[0]["requester"] == {"email": "s1@mju.ac.kr", "name": "학생1", "student_no": "1"}
    assert [x["id"] for x in client.get("/api/admin/reservations?status=approved").json()] == [2]
    assert client.get("/api/admin/reservations?status=approved").json()[0]["requester"] is None
    assert [x["id"] for x in client.get(f"/api/admin/reservations?status=requested,approved&building_id={bid}").json()] == [1, 2]
    assert client.get("/api/admin/reservations?status=approved&date_from=2026-09-25&date_to=2026-09-25").json()[0]["id"] == 2
    assert [x["id"] for x in client.get("/api/admin/reservations", headers=other_admin_hdr).json()] == [3]
    assert client.get("/api/admin/reservations", headers=client.headers | {"Authorization": other_admin_hdr["Authorization"]}).status_code == 200


def test_approve_reject_cancel_and_summary_bucket(client, live, app, school, monkeypatch):
    _fix_clock(monkeypatch)
    _, ids = _building(app, 1, "E", rooms=((301, 2),))
    rid = ids[301]
    _resv(app, rid, dt.date(2026, 9, 24), 13, 0, 14, 0, id_=1, status="requested", requested_by="s1@mju.ac.kr", requested_at=UTC_NOW)
    _resv(app, rid, dt.date(2026, 9, 24), 15, 0, 16, 0, id_=2, status="requested", requested_by="s2@mju.ac.kr", requested_at=UTC_NOW)
    j = client.get("/api/admin/summary").json()
    assert j["warnings"]["pending_reservations"]["count"] == 2 and j["warnings"]["pending_reservations"]["items"][0]["id"] == 1
    r = client.post("/api/admin/reservations/1/approve")
    assert r.status_code == 200 and r.json()["status"] == "approved" and r.json()["decided_at"]
    assert client.post("/api/admin/reservations/1/approve").status_code == 409
    r = client.post("/api/admin/reservations/2/reject", json={"reason": "사유"})
    assert r.json()["status"] == "rejected" and r.json()["reject_reason"] == "사유"
    r = client.post("/api/admin/reservations/1/cancel")
    assert r.json()["status"] == "cancelled"
    assert client.post("/api/admin/reservations/999/approve").status_code == 404
    with live() as s:
        assert [o.type for o in s.scalars(select(Outbox).order_by(Outbox.id))] == ["RESV_SET", "RESV_SET", "RESV_DEL", "RESV_DEL"]
    assert client.get("/api/admin/summary").json()["warnings"]["pending_reservations"]["count"] == 0
```

- [ ] **Step 2: 실패 확인** → 404

- [ ] **Step 3: 스키마·admin.py**

```python
class RequesterOut(BaseModel):
    email: str
    name: str
    student_no: str | None


class ResvAdminOut(ResvMineOut):
    requester: RequesterOut | None
```

`server/app/domain/admin.py`:

```python
def resv_admin_out(s: Session, r: Reservation) -> dict:
    from app.domain.student_router import _mine_out  # 순환 회피용 지연 import

    u = s.get(User, r.requested_by) if r.requested_by else None
    return {**_mine_out(s, r), "requester": {"email": u.email, "name": u.name, "student_no": u.student_no} if u else None}


def pending_reservations(s: Session, school_id: int) -> list[dict]:
    q = (
        select(Reservation)
        .join(Room, Room.id == Reservation.room_id).join(Building, Building.id == Room.building_id)
        .where(Building.school_id == school_id, Reservation.status == "requested")
        .order_by(Reservation.requested_at)
    )
    return [resv_admin_out(s, r) for r in s.scalars(q)]
```

`summary()` 의 `warnings` 에 `"pending_reservations": _bucket(pending_reservations(s, school_id), preview)` 추가. (`_mine_out` 을 `admin.py` 로 옮기는 편이 순환이 없어 낫다 — 옮기면 `student_router` 가 `admin._mine_out` 을 import. 구현자 선택, 어느 쪽이든 지연 import 없이 되면 그쪽.)

- [ ] **Step 4: 라우터**

`server/app/domain/admin_resv_router.py`:

```python
"""관리자 예약 승인·일일 작업·분석 (S10 §4.2·§4.3). 전부 관리자 + 학교 스코프."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas as S
from app.auth.deps import AdminUser
from app.auth.models import User
from app.deps import _DB
from app.domain import admin, clock, reserve
from app.domain.models import Building, Reservation, Room

router = APIRouter(prefix="/api/admin", dependencies=[AdminUser])


def _scoped_resv(s: Session, user: User, id: int) -> Reservation:
    r = s.get(Reservation, id)
    if r is None or s.get(Building, s.get(Room, r.room_id).building_id).school_id != user.school_id:
        raise HTTPException(404, "예약 없음")
    return r


@router.get("/reservations", response_model=list[S.ResvAdminOut])
def list_reservations(
    status: str = "requested", building_id: int | None = None,
    date_from: dt.date | None = None, date_to: dt.date | None = None,
    user: User = AdminUser, s: Session = _DB,
):
    q = (
        select(Reservation).join(Room, Room.id == Reservation.room_id).join(Building, Building.id == Room.building_id)
        .where(Building.school_id == user.school_id, Reservation.status.in_(status.split(",")))
        .order_by(Reservation.requested_at, Reservation.date, Reservation.s_h)
    )
    if building_id is not None:
        q = q.where(Building.id == building_id)
    if date_from is not None:
        q = q.where(Reservation.date >= date_from)
    if date_to is not None:
        q = q.where(Reservation.date <= date_to)
    return [admin.resv_admin_out(s, r) for r in s.scalars(q)]


@router.post("/reservations/{id}/approve", response_model=S.ResvAdminOut)
def approve(id: int, user: User = AdminUser, s: Session = _DB):
    r = _scoped_resv(s, user, id)
    reserve.approve(s, r, user.email, clock.local_now())
    return admin.resv_admin_out(s, r)


@router.post("/reservations/{id}/reject", response_model=S.ResvAdminOut)
def reject(id: int, body: S.RejectIn, user: User = AdminUser, s: Session = _DB):
    r = _scoped_resv(s, user, id)
    reserve.reject(s, r, user.email, body.reason, clock.local_now())
    return admin.resv_admin_out(s, r)


@router.post("/reservations/{id}/cancel", response_model=S.ResvAdminOut)
def cancel(id: int, user: User = AdminUser, s: Session = _DB):
    r = _scoped_resv(s, user, id)
    reserve.cancel(s, r, by_admin=True, now_local=clock.local_now())
    return admin.resv_admin_out(s, r)
```

`server/app/main.py`: `from app.domain.admin_resv_router import router as admin_resv_router` + include.

- [ ] **Step 5: 통과·커밋**

```bash
git add app/domain/admin_resv_router.py app/domain/admin.py app/schemas.py app/main.py tests/test_admin_resv.py
git commit -m "feat(server): 관리자 예약 승인·거절·취소(RESV_SET/DEL), 요약 pending_reservations 버킷"
```

---

### Task 7: 04:00 일일 작업 — `daily.py` · `daily_loop` · jobs API

**Files:**
- Create: `server/app/domain/daily.py`
- Modify: `server/app/domain/admin_resv_router.py`, `server/app/schemas.py`(`JobRunOut`), `server/app/main.py`
- Test: `server/tests/test_daily.py`

**Interfaces:**
- Produces: `daily.run_daily(Session, now_utc=None) -> dict`(result), `daily.already_ran_today(s, now_local) -> bool`, `daily.daily_loop(Session, interval_s=60.0)`(coroutine); `POST /api/admin/jobs/daily`, `GET /api/admin/jobs?name=daily&limit=30`; `S.JobRunOut(id, name, ran_at, result: dict)`.

- [ ] **Step 1: 실패 테스트**

`server/tests/test_daily.py` (공용 헬퍼 복사 + `import json`, `from app.auth.models import EmailToken`, `from app.domain import daily`, `from app.domain.models import JobRun`, `from app.lora_service.models import Outbox`, `from sqlalchemy import select`):

```python
def _outbox(app, bld, room, type_, state, finished_at, payload="{}"):
    with app.state.Session() as s, s.begin():
        o = Outbox(bld=bld, room=room, unit=1, type=type_, payload=payload, state=state, created_at=UTC_NOW,
                   finished_at=finished_at, modem_id="m1")
        s.add(o)
        s.flush()
        return o.id


def test_run_daily_five_steps(db, hub, app, school, monkeypatch):
    _fix_clock(monkeypatch)  # KST 9/23 10:30
    _, ids = _building(app, 1, "E", rooms=((301, 2), (302, 1)))
    r301, r302 = ids[301], ids[302]
    # 1 만료: 신청인데 시작 지남
    _resv(app, r301, dt.date(2026, 9, 23), 9, 0, 10, 0, id_=1, status="requested", requested_by="s1@mju.ac.kr")
    # 2 승격: 승인·창 안(9/30)·outbox 없음 → RESV_SET. 이미 queued 인 것(9/24 id 3)은 건너뜀
    _resv(app, r301, dt.date(2026, 9, 30), 13, 0, 14, 0, id_=2, status="approved")
    _resv(app, r301, dt.date(2026, 9, 24), 13, 0, 14, 0, id_=3, status="approved")
    _outbox(app, "E", 301, "RESV_SET", "queued", None, payload=json.dumps({"resv_id": 3}))
    _resv(app, r301, dt.date(2026, 10, 5), 13, 0, 14, 0, id_=4, status="approved")  # 창 밖 → 없음
    # 3 재동기: 24 h 안 failed SLOT_SET(302) + failed CMD(무시) + 25 h 전 failed(무시)
    _outbox(app, "E", 302, "SLOT_SET", "failed", UTC_NOW - dt.timedelta(hours=1))
    _outbox(app, "E", 302, "CMD", "failed", UTC_NOW - dt.timedelta(hours=1))
    _outbox(app, "E", 301, "EXAM_SET", "failed", UTC_NOW - dt.timedelta(hours=25))
    # 4 정리: 91 일 전 예약, 91 일 전 job_run, 8 일 지난 토큰
    _resv(app, r302, dt.date(2026, 6, 20), 9, 0, 10, 0, id_=5, status="approved")
    with app.state.Session() as s, s.begin():
        s.add(JobRun(name="daily", ran_at=UTC_NOW - dt.timedelta(days=91), result="{}"))
        s.add(EmailToken(token_hash="x", email="s1@mju.ac.kr", purpose="verify", expires_at=UTC_NOW - dt.timedelta(days=8)))
        s.add(EmailToken(token_hash="y", email="s1@mju.ac.kr", purpose="verify", expires_at=UTC_NOW - dt.timedelta(days=6)))
    res = daily.run_daily(app.state.Session)
    assert res["expired"] == 1 and res["promoted"] == 1 and res["resynced"] == [["E", 302, ["schedule"]]]
    assert res["pruned"] == {"reservations": 1, "job_runs": 1, "email_tokens": 1} and res["errors"] == []
    with app.state.Session() as s:
        assert s.get(Reservation, 1).status == "expired" and s.get(Reservation, 5) is None
        types = [(o.bld, o.room, o.type) for o in s.scalars(select(Outbox).where(Outbox.state == "queued").order_by(Outbox.id))]
        assert types.count(("E", 301, "RESV_SET")) == 3  # 기존 1 + 승격 2(유닛 2)
        assert ("E", 302, "FILE") in types
        assert s.scalar(select(EmailToken.token_hash).where(EmailToken.token_hash == "y")) == "y"
        runs = s.scalars(select(JobRun).order_by(JobRun.id)).all()
        assert len(runs) == 1 and json.loads(runs[0].result)["promoted"] == 1


def test_step_failure_continues(db, hub, app, school, monkeypatch):
    _fix_clock(monkeypatch)
    monkeypatch.setattr(daily, "_promote", lambda s, now_local: (_ for _ in ()).throw(RuntimeError("boom")))
    res = daily.run_daily(app.state.Session)
    assert res["promoted"] == 0 and res["errors"] == ["promote: boom"] and "pruned" in res


def test_already_ran_today_and_loop_tick(db, hub, app, school, monkeypatch):
    with app.state.Session() as s:
        assert daily.already_ran_today(s, dt.datetime(2026, 9, 23, 10, 0)) is False
    _fix_clock(monkeypatch, dt.datetime(2026, 9, 22, 18, 59))  # KST 03:59 → 안 돎
    assert daily.tick(app.state.Session) is False
    _fix_clock(monkeypatch, dt.datetime(2026, 9, 22, 19, 0))   # KST 04:00 → 돎
    assert daily.tick(app.state.Session) is True
    assert daily.tick(app.state.Session) is False               # 같은 날 두 번 안 돎
    _fix_clock(monkeypatch, dt.datetime(2026, 9, 23, 5, 0))    # KST 14:00, 오늘 이미 돌았음
    assert daily.tick(app.state.Session) is False


def test_jobs_endpoints(client, live, app, school, monkeypatch):
    _fix_clock(monkeypatch)
    r = client.post("/api/admin/jobs/daily")
    assert r.status_code == 200 and r.json()["name"] == "daily" and r.json()["result"]["errors"] == []
    r = client.post("/api/admin/jobs/daily")  # 수동은 항상 돎
    assert r.status_code == 200
    assert len(client.get("/api/admin/jobs?name=daily").json()) == 2
    assert client.get("/api/admin/jobs?name=daily&limit=1").json()[0]["id"] == r.json()["id"]
```

- [ ] **Step 2: 실패 확인** → `ModuleNotFoundError`

- [ ] **Step 3: 구현**

`server/app/domain/daily.py`:

```python
"""04:00 일일 작업 (S10 §2.5): 만료 → 승격 → 실패 재동기 → 정리 → 기록. 단계별 트랜잭션, 오류는 계속."""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.auth.models import EmailToken
from app.domain import clock
from app.domain.models import Building, JobRun, Reservation, Room
from app.domain.topology import RESV_HORIZON_DAYS
from app.lora_service import api
from app.lora_service.api import KIND_OF
from app.lora_service.models import Outbox

log = logging.getLogger(__name__)
KEEP_DAYS = 90
TOKEN_KEEP_DAYS = 7
RESYNC_WINDOW_H = 24


def _rooms_by_id(s: Session) -> dict[int, tuple[str, int]]:
    return {rid: (bld, room) for rid, bld, room in s.execute(
        select(Room.id, Building.bld, Room.room).join(Building, Building.id == Room.building_id))}


def _expire(s: Session, now_local: dt.datetime) -> int:
    n = 0
    for r in s.scalars(select(Reservation).where(Reservation.status == "requested")):
        if clock.local_dt(r.date, r.s_h, r.s_m) < now_local:
            r.status = "expired"
            n += 1
    return n


def _promote(s: Session, now_local: dt.datetime) -> int:
    today = now_local.date()
    addr = _rooms_by_id(s)
    open_ids = set()
    for o in s.scalars(select(Outbox).where(Outbox.type == "RESV_SET", Outbox.state.in_(("queued", "dispatched")))):
        open_ids.add((o.bld, o.room, json.loads(o.payload).get("resv_id")))
    n = 0
    for r in s.scalars(select(Reservation).where(
        Reservation.status == "approved", Reservation.date.between(today, today + dt.timedelta(days=RESV_HORIZON_DAYS)))):
        bld, room = addr[r.room_id]
        if (bld, room, r.id) in open_ids:
            continue
        api.enqueue_resv_set(bld, room, r.id, r.date, (r.s_h, r.s_m), (r.e_h, r.e_m), r.type, r.subject, r.professor)
        n += 1
    return n


def _resync_failed(s: Session, now_utc: dt.datetime) -> list[list]:
    since = now_utc - dt.timedelta(hours=RESYNC_WINDOW_H)
    kinds: dict[tuple[str, int], set[str]] = {}
    for o in s.scalars(select(Outbox).where(Outbox.state == "failed", Outbox.finished_at >= since)):
        kind = KIND_OF.get(o.type)
        if kind in ("schedule", "resv", "exam"):
            kinds.setdefault((o.bld, o.room), set()).add(kind)
    out = []
    for (bld, room), ks in sorted(kinds.items()):
        api.enqueue_full_sync(bld, room, tuple(sorted(ks)))
        out.append([bld, room, sorted(ks)])
    return out


def _prune(s: Session, now_utc: dt.datetime, now_local: dt.datetime) -> dict:
    cutoff_date = now_local.date() - dt.timedelta(days=KEEP_DAYS)
    return {
        "reservations": s.execute(delete(Reservation).where(Reservation.date < cutoff_date)).rowcount,
        "job_runs": s.execute(delete(JobRun).where(JobRun.ran_at < now_utc - dt.timedelta(days=KEEP_DAYS))).rowcount,
        "email_tokens": s.execute(delete(EmailToken).where(EmailToken.expires_at < now_utc - dt.timedelta(days=TOKEN_KEEP_DAYS))).rowcount,
    }


def run_daily(Session: sessionmaker, now_utc: dt.datetime | None = None) -> dict:
    now_utc = now_utc or clock.now_utc()
    now_local = clock.to_local(now_utc)
    res: dict = {"expired": 0, "promoted": 0, "resynced": [], "pruned": {}, "errors": []}

    def step(name, fn):
        try:
            with Session() as s, s.begin():
                res[name] = fn(s)
        except Exception as e:  # 한 단계 실패가 나머지를 막지 않는다
            log.exception("daily %s 실패", name)
            res["errors"].append(f"{name}: {e}")

    step("expired", lambda s: _expire(s, now_local))
    step("promoted", lambda s: _promote(s, now_local))
    step("resynced", lambda s: _resync_failed(s, now_utc))
    step("pruned", lambda s: _prune(s, now_utc, now_local))
    with Session() as s, s.begin():
        s.add(JobRun(name="daily", ran_at=now_utc, result=json.dumps(res, ensure_ascii=False)))
    return res


def already_ran_today(s: Session, now_local: dt.datetime) -> bool:
    start_utc = clock.to_utc(dt.datetime.combine(now_local.date(), dt.time()))
    return s.scalar(select(JobRun.id).where(JobRun.name == "daily", JobRun.ran_at >= start_utc).limit(1)) is not None


def tick(Session: sessionmaker) -> bool:
    """04:00(KST) 이후이고 오늘 아직 안 돌았으면 실행. 돌았으면 True."""
    now_utc = clock.now_utc()
    now_local = clock.to_local(now_utc)
    if now_local.hour < clock.DAILY_HOUR_LOCAL:
        return False
    with Session() as s:
        if already_ran_today(s, now_local):
            return False
    run_daily(Session, now_utc)
    return True


async def daily_loop(Session: sessionmaker, interval_s: float = 60.0) -> None:
    while True:
        try:
            await asyncio.to_thread(tick, Session)
        except Exception:
            log.exception("daily tick 실패")
        await asyncio.sleep(interval_s)
```

`server/app/main.py` lifespan: `daily_task = asyncio.ensure_future(daily.daily_loop(Session))` (sweeper 옆), finally 에서 cancel. **테스트에서는 `clock.now_utc` 가 monkeypatch 되기 전에 앱이 뜨므로 tick 이 실제 시각으로 한 번 돌 수 있다** — `create_app(db_path, daily=False)` 는 두지 않고, 대신 `settings.debug` 와 무관하게 lifespan 첫 tick 전에 60 s sleep 부터 하도록 `daily_loop` 를 `await asyncio.sleep(interval_s)` 먼저 하게 바꾼다(테스트 수명 < 60 s). 위 코드의 while 안 순서를 sleep → tick 으로.

`admin_resv_router.py` 에:

```python
@router.post("/jobs/daily", response_model=S.JobRunOut)
def run_daily_now(request: Request, s: Session = _DB):
    from app.domain import daily

    daily.run_daily(request.app.state.Session)
    return s.scalar(select(JobRun).where(JobRun.name == "daily").order_by(JobRun.id.desc()).limit(1))


@router.get("/jobs", response_model=list[S.JobRunOut])
def jobs(name: str = "daily", limit: int = Query(30, ge=1, le=200), s: Session = _DB):
    return s.scalars(select(JobRun).where(JobRun.name == name).order_by(JobRun.id.desc()).limit(limit)).all()
```

(`from fastapi import Request`, `from app.domain.models import JobRun`.) `run_daily_now` 는 `_DB` 세션과 별개로 `run_daily` 가 자기 세션들을 쓰므로, 읽기 전용 `_DB` 세션은 마지막 조회에만 — 같은 요청 안에서 `_DB` 가 열린 채 `run_daily` 가 쓰면 WAL 락? `_DB` 는 아직 아무것도 안 썼으므로(읽기 트랜잭션도 시작 전) 문제없다. 안전하게 `s` 의존성을 지우고 `with request.app.state.Session() as s:` 로 조회해도 된다.

`S.JobRunOut`:

```python
class JobRunOut(Out):
    id: int
    name: str
    ran_at: dt.datetime
    result: dict

    @field_validator("result", mode="before")
    @classmethod
    def _r(cls, v):
        return json.loads(v) if isinstance(v, str) else v
```

- [ ] **Step 4: 통과·커밋**

```bash
git add app/domain/daily.py app/domain/admin_resv_router.py app/schemas.py app/main.py tests/test_daily.py
git commit -m "feat(server): 04:00 일일 작업 — 만료·승격·실패 재동기·정리·기록, daily_loop, /api/admin/jobs"
```

---

### Task 8: 분석 집계 — `analytics.py` + `/api/admin/analytics/*`

**Files:**
- Create: `server/app/domain/analytics.py`
- Modify: `server/app/domain/admin_resv_router.py`, `server/app/schemas.py`
- Test: `server/tests/test_analytics.py`

**Interfaces:**
- Produces: `analytics.OPEN_MIN = 9*60`, `CLOSE_MIN = 21*60`, `MAX_DAYS = 90`, `BINS = (0, 10, 20, 30, 45, 60, 90, 120)`; `analytics.day_segments(s, room_id, date) -> list[tuple[int, int, int]]`(s, e, layout — 운영 시간 안 구간 병합); `analytics.allocation(s, school_id, d_from, d_to, building_id, group) -> list[dict]`; `analytics.free_slots(s, school_id, date, building_id) -> list[dict]`; `analytics.reservation_stats(s, school_id, d_from, d_to, group, now_local) -> dict`; `analytics.latency(s, school_id, d_from, d_to, type_) -> dict`; `analytics.latency_samples(s, school_id, d_from, d_to, type_, limit) -> list[dict]`; `analytics.parse_range(d_from, d_to, today) -> tuple[date, date]`(기본 30일, 90일 초과 → HTTPException 422).

- [ ] **Step 1: 실패 테스트**

`server/tests/test_analytics.py` (공용 헬퍼 복사 + `from app.domain import analytics as A`, `from app.lora_service.models import Outbox`):

```python
def _acked(app, bld, room, type_, created, secs):
    with app.state.Session() as s, s.begin():
        s.add(Outbox(bld=bld, room=room, unit=1, type=type_, payload="{}", state="acked", created_at=created,
                     finished_at=created + dt.timedelta(seconds=secs)))


def test_day_segments_and_allocation(app, school, monkeypatch):
    _fix_clock(monkeypatch)
    bid, ids = _building(app, 1, "E", rooms=((101, 1), (102, 1)))
    rid = ids[101]
    _slot(app, rid, 3, 9, 0, 10, 50)                 # 수 110 분 수업(1·2)
    _slot(app, rid, 3, 11, 0, 12, 0, type_=3)        # 휴강 60 분 → unused
    _resv(app, rid, dt.date(2026, 9, 23), 13, 0, 14, 0, id_=1)   # 60 분 대여
    _slot(app, rid, 3, 20, 0, 22, 0)                 # 운영 시간 밖 21~22 는 잘림 → 60 분
    with app.state.Session() as s:
        segs = A.day_segments(s, rid, dt.date(2026, 9, 23))
        assert segs == [(540, 590, 1), (590, 600, 2), (600, 650, 1), (660, 720, 3), (780, 840, 7), (1200, 1250, 1), (1250, 1260, 2)]
        rows = A.allocation(s, 1, dt.date(2026, 9, 23), dt.date(2026, 9, 23), None, "room")
        r101 = next(r for r in rows if r["key"] == rid)
        assert (r101["assigned_min"], r101["unused_min"], r101["total_min"]) == (110 + 60 + 60 + 60, 60, 720)
        assert r101["rate"] == round(290 / 720, 4) and r101["label"] == "E동 101"
        assert next(r for r in rows if r["key"] == ids[102])["assigned_min"] == 0
        by_b = A.allocation(s, 1, dt.date(2026, 9, 23), dt.date(2026, 9, 23), None, "building")
        assert by_b[0]["key"] == bid and by_b[0]["total_min"] == 1440 and by_b[0]["assigned_min"] == 290
        by_w = A.allocation(s, 1, dt.date(2026, 9, 21), dt.date(2026, 9, 27), None, "weekday")
        assert by_w[0]["key"] == 3 and by_w[0]["label"] == "수"  # rate desc — 수요일만 배정


def test_free_slots_merge(app, school, monkeypatch):
    _fix_clock(monkeypatch)
    _, ids = _building(app, 1, "E", rooms=((101, 1),))
    rid = ids[101]
    _slot(app, rid, 3, 9, 0, 10, 0)
    _slot(app, rid, 3, 10, 0, 11, 0)   # 연속 → 빈 구간 없음
    _slot(app, rid, 3, 15, 0, 16, 0)
    with app.state.Session() as s:
        out = A.free_slots(s, 1, dt.date(2026, 9, 23), None)
        assert out[0]["room"] == 101 and out[0]["free"] == [{"from": "11:00", "to": "15:00"}, {"from": "16:00", "to": "21:00"}]


def test_reservation_stats_and_no_show(app, school, monkeypatch):
    _fix_clock(monkeypatch)
    _, ids = _building(app, 1, "E", rooms=((101, 1),))
    rid = ids[101]
    d = dt.date(2026, 9, 22)
    _resv(app, rid, d, 9, 0, 10, 0, id_=1, status="approved", requested_by="s1@mju.ac.kr", requested_at=UTC_NOW)   # 종료·미체크인 → no_show
    _resv(app, rid, d, 10, 0, 11, 0, id_=2, status="approved", requested_by="s1@mju.ac.kr", requested_at=UTC_NOW, checked_in_at=UTC_NOW)
    _resv(app, rid, d, 11, 0, 12, 0, id_=3, status="rejected", requested_by="s2@mju.ac.kr", requested_at=UTC_NOW)
    _resv(app, rid, dt.date(2026, 9, 24), 11, 0, 12, 0, id_=4, status="approved", requested_by="s2@mju.ac.kr", requested_at=UTC_NOW)  # 미래 → no_show 아님
    _resv(app, rid, d, 13, 0, 14, 0, id_=5, status="approved")  # 관리자 예약 → 통계 제외
    with app.state.Session() as s:
        st = A.reservation_stats(s, 1, dt.date(2026, 9, 22), dt.date(2026, 9, 24), "day", clock.local_now())
        assert st["totals"] == {"requested": 4, "approved": 3, "rejected": 1, "cancelled": 0, "expired": 0, "no_show": 1, "checked_in": 1}
        assert st["no_show_rate"] == 0.5 and st["checkin_rate"] == 0.5
        assert [x["date"] for x in st["series"]] == ["2026-09-22", "2026-09-23", "2026-09-24"]
        assert st["series"][0]["approved"] == 2 and st["series"][2]["approved"] == 1


def test_latency_bins_and_samples(app, school, monkeypatch):
    _fix_clock(monkeypatch)
    _building(app, 1, "E", rooms=((101, 1),))
    _building(app, 2, "F", rooms=((101, 1),))
    for secs in (5, 12, 25, 31, 50, 95, 130):
        _acked(app, "E", 101, "SLOT_SET", UTC_NOW - dt.timedelta(days=1), secs)
    _acked(app, "E", 101, "RESV_SET", UTC_NOW - dt.timedelta(days=1), 8)
    _acked(app, "E", 101, "FILE", UTC_NOW - dt.timedelta(days=1), 3)         # 제외
    _acked(app, "F", 101, "SLOT_SET", UTC_NOW - dt.timedelta(days=1), 1)     # 타교
    _acked(app, "E", 101, "SLOT_SET", UTC_NOW - dt.timedelta(days=40), 1)    # 창 밖
    with app.state.Session() as s:
        d0, d1 = dt.date(2026, 8, 25), dt.date(2026, 9, 23)
        lat = A.latency(s, 1, d0, d1, "all")
        assert lat["n"] == 8 and lat["max"] == 130 and lat["p50"] == 25 and lat["p95"] == 95  # 분위 = secs[int(p*(n-1))]
        assert [b["count"] for b in lat["bins"]] == [2, 1, 1, 1, 1, 0, 1, 1]
        assert lat["bins"][-1] == {"ge": 120, "lt": None, "count": 1}
        assert lat["within_30s"] == round(4 / 8, 4) and lat["within_90s"] == round(6 / 8, 4)
        assert A.latency(s, 1, d0, d1, "RESV_SET")["n"] == 1
        smp = A.latency_samples(s, 1, d0, d1, "all", 3)
        assert len(smp) == 3 and smp[0]["seconds"] in (5, 12, 25, 31, 50, 95, 130, 8) and smp[0]["room"] == 101


def test_parse_range_and_endpoints(client, app, school, student_hdr, monkeypatch):
    _fix_clock(monkeypatch)
    assert A.parse_range(None, None, dt.date(2026, 9, 23)) == (dt.date(2026, 8, 25), dt.date(2026, 9, 23))
    _building(app, 1, "E", rooms=((101, 1),))
    assert client.get("/api/admin/analytics/allocation").status_code == 200
    assert client.get("/api/admin/analytics/allocation?from=2026-01-01&to=2026-09-23").status_code == 422
    assert client.get("/api/admin/analytics/free-slots?date=2026-09-23").json()[0]["room"] == 101
    assert client.get("/api/admin/analytics/reservations").json()["totals"]["requested"] == 0
    assert client.get("/api/admin/analytics/latency").json()["n"] == 0
    assert client.get("/api/admin/analytics/latency/samples").json() == []
    assert client.get("/api/admin/analytics/allocation", headers=student_hdr).status_code == 403
```

- [ ] **Step 2: 실패 확인** → `ModuleNotFoundError`

- [ ] **Step 3: 구현**

`server/app/domain/analytics.py`:

```python
"""분석 집계 (S10 §2.6). room_state 를 구간 병합으로 하루 단위 계산 — 분 루프 없음."""

from __future__ import annotations

import datetime as dt
from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import clock, room_state
from app.domain.models import Building, Reservation, Room
from app.lora_service.models import Outbox

OPEN_MIN, CLOSE_MIN = 9 * 60, 21 * 60
MAX_DAYS = 90
DEFAULT_DAYS = 30
BINS = (0, 10, 20, 30, 45, 60, 90, 120)
ASSIGNED = {1, 2, 3, 5, 6, 7}
WEEKDAY = "월화수목금토일"
LATENCY_TYPES = ("SLOT_SET", "RESV_SET")


def parse_range(d_from: dt.date | None, d_to: dt.date | None, today: dt.date) -> tuple[dt.date, dt.date]:
    d_to = d_to or today
    d_from = d_from or d_to - dt.timedelta(days=DEFAULT_DAYS - 1)
    if d_from > d_to or (d_to - d_from).days + 1 > MAX_DAYS:
        raise HTTPException(422, f"기간은 {MAX_DAYS}일 이내")
    return d_from, d_to


def _school_rooms(s: Session, school_id: int, building_id: int | None):
    q = (select(Room, Building).join(Building, Room.building_id == Building.id)
         .where(Building.school_id == school_id).order_by(Building.bld, Room.room))
    if building_id is not None:
        q = q.where(Building.id == building_id)
    return s.execute(q).all()


def day_segments(s: Session, room_id: int, date: dt.date) -> list[tuple[int, int, int]]:
    """운영 시간 안에서 (s, e, layout) 구간. room_state 를 변화점마다 호출해 이어 붙인다."""
    slots, resvs, in_exam = room_state.load_inputs(s, room_id, date)
    points = sorted({OPEN_MIN, CLOSE_MIN, *[p for x in slots + resvs for p in (x.s, x.e)],
                     *[m for x in slots if x.type == 1 for m in range(x.s - x.s % 60 + 50, x.e, 60)],
                     *[m for x in slots if x.type == 1 for m in range(x.s - x.s % 60 + 60, x.e, 60)]})
    points = [p for p in points if OPEN_MIN <= p <= CLOSE_MIN]
    out: list[tuple[int, int, int]] = []
    for a, b in zip(points, points[1:], strict=False):
        layout, _ = room_state.room_state(slots, resvs, in_exam, a)
        if layout == room_state.FREE:
            continue
        if out and out[-1][1] == a and out[-1][2] == layout:
            out[-1] = (out[-1][0], b, layout)
        else:
            out.append((a, b, layout))
    return out


def allocation(s: Session, school_id: int, d_from: dt.date, d_to: dt.date, building_id: int | None, group: str) -> list[dict]:
    acc: dict = defaultdict(lambda: {"assigned_min": 0, "unused_min": 0, "total_min": 0, "label": ""})
    days = [d_from + dt.timedelta(days=i) for i in range((d_to - d_from).days + 1)]
    for room, b in _school_rooms(s, school_id, building_id):
        for d in days:
            key, label = {
                "room": (room.id, f"{b.name} {room.room}"),
                "building": (b.id, b.name),
                "weekday": (d.isoweekday(), WEEKDAY[d.isoweekday() - 1]),
            }[group]
            a = acc[key]
            a["label"] = label
            a["total_min"] += CLOSE_MIN - OPEN_MIN
            for x0, x1, layout in day_segments(s, room.id, d):
                a["assigned_min"] += x1 - x0
                if layout == 3:
                    a["unused_min"] += x1 - x0
    rows = [{"key": k, **v, "rate": round(v["assigned_min"] / v["total_min"], 4) if v["total_min"] else 0.0} for k, v in acc.items()]
    return sorted(rows, key=lambda r: (-r["rate"], str(r["key"])))


def free_slots(s: Session, school_id: int, date: dt.date, building_id: int | None) -> list[dict]:
    out = []
    for room, b in _school_rooms(s, school_id, building_id):
        busy = day_segments(s, room.id, date)
        free, cur = [], OPEN_MIN
        for x0, x1, _ in busy:
            if x0 > cur:
                free.append({"from": room_state.fmt_hhmm(cur), "to": room_state.fmt_hhmm(x0)})
            cur = max(cur, x1)
        if cur < CLOSE_MIN:
            free.append({"from": room_state.fmt_hhmm(cur), "to": room_state.fmt_hhmm(CLOSE_MIN)})
        out.append({"room_id": room.id, "room": room.room, "building": b.name, "free": free})
    return out


def reservation_stats(s: Session, school_id: int, d_from: dt.date, d_to: dt.date, group: str, now_local: dt.datetime) -> dict:
    keys = ("requested", "approved", "rejected", "cancelled", "expired", "no_show", "checked_in")
    series: dict = defaultdict(lambda: dict.fromkeys(keys, 0))
    q = (select(Reservation).join(Room, Room.id == Reservation.room_id).join(Building, Building.id == Room.building_id)
         .where(Building.school_id == school_id, Reservation.requested_by.is_not(None), Reservation.date.between(d_from, d_to)))
    ended = 0
    for r in s.scalars(q):
        k = r.date.isoformat() if group == "day" else clock.week_start(r.date).isoformat()
        row = series[k]
        row["requested"] += 1
        if r.status in ("approved", "rejected", "cancelled", "expired"):
            row[r.status] += 1
        if r.status == "approved" and clock.local_dt(r.date, r.e_h, r.e_m) <= now_local:
            ended += 1
            if r.checked_in_at is None:
                row["no_show"] += 1
            else:
                row["checked_in"] += 1
    days = [d_from + dt.timedelta(days=i) for i in range((d_to - d_from).days + 1)]
    labels = sorted({d.isoformat() if group == "day" else clock.week_start(d).isoformat() for d in days})
    out_series = [{"date": k, **series[k]} for k in labels]
    totals = {k: sum(x[k] for x in out_series) for k in keys}
    return {
        "series": out_series, "totals": totals,
        "no_show_rate": round(totals["no_show"] / ended, 4) if ended else 0.0,
        "checkin_rate": round(totals["checked_in"] / ended, 4) if ended else 0.0,
    }


def _latency_rows(s: Session, school_id: int, d_from: dt.date, d_to: dt.date, type_: str):
    lo = clock.to_utc(dt.datetime.combine(d_from, dt.time()))
    hi = clock.to_utc(dt.datetime.combine(d_to + dt.timedelta(days=1), dt.time()))
    types = LATENCY_TYPES if type_ == "all" else (type_,)
    q = (select(Outbox, Room.id).join(Building, (Building.bld == Outbox.bld) & (Building.school_id == school_id))
         .join(Room, (Room.building_id == Building.id) & (Room.room == Outbox.room))
         .where(Outbox.state == "acked", Outbox.type.in_(types), Outbox.created_at >= lo, Outbox.created_at < hi,
                Outbox.finished_at.is_not(None))
         .order_by(Outbox.created_at.desc()))
    return s.execute(q).all()


def latency(s: Session, school_id: int, d_from: dt.date, d_to: dt.date, type_: str) -> dict:
    secs = sorted((o.finished_at - o.created_at).total_seconds() for o, _ in _latency_rows(s, school_id, d_from, d_to, type_))
    n = len(secs)
    edges = [*BINS, None]
    bins = [{"ge": edges[i], "lt": edges[i + 1],
             "count": sum(1 for x in secs if x >= edges[i] and (edges[i + 1] is None or x < edges[i + 1]))}
            for i in range(len(BINS))]
    pct = lambda p: secs[int(p * (n - 1))] if n else None  # noqa: E731 — 하위 분위, 내림
    return {
        "n": n, "bins": bins, "p50": pct(0.5), "p95": pct(0.95), "max": secs[-1] if n else None,
        "within_30s": round(sum(1 for x in secs if x <= 30) / n, 4) if n else 0.0,
        "within_90s": round(sum(1 for x in secs if x <= 90) / n, 4) if n else 0.0,
    }


def latency_samples(s: Session, school_id: int, d_from: dt.date, d_to: dt.date, type_: str, limit: int) -> list[dict]:
    return [
        {"outbox_id": o.id, "room_id": rid, "bld": o.bld, "room": o.room, "unit": o.unit, "type": o.type,
         "created_at": o.created_at, "finished_at": o.finished_at, "seconds": (o.finished_at - o.created_at).total_seconds()}
        for o, rid in _latency_rows(s, school_id, d_from, d_to, type_)[:limit]
    ]
```

분위 정의: 하위 p 분위 = `secs[int(p*(n-1))]`(내림). n=8 `[5,8,12,25,31,50,95,130]` → p50 = index 3 = 25, p95 = index 6 = 95.

`day_segments` 의 변화점: 수업 슬롯은 매시 50분·정각에 1↔2 가 바뀌므로 그 점들을 넣는다. 슬롯 9:00~10:50 → 점 540, 590, 600, 650 → (540,590,1),(590,600,2),(600,650,1). 20:00~22:00 슬롯은 CLOSE 21:00 에서 잘려 (1200,1250,1),(1250,1260,2) — `assigned_min` 은 둘 다 배정이라 60.

라우터(`admin_resv_router.py`):

```python
@router.get("/analytics/allocation", response_model=list[S.AllocationOut])
def analytics_allocation(from_: dt.date | None = Query(None, alias="from"), to: dt.date | None = None,
                         building_id: int | None = None, group: Literal["room", "building", "weekday"] = "room",
                         user: User = AdminUser, s: Session = _DB):
    d0, d1 = analytics.parse_range(from_, to, clock.local_today())
    return analytics.allocation(s, user.school_id, d0, d1, building_id, group)


@router.get("/analytics/free-slots", response_model=list[S.FreeSlotsOut])
def analytics_free(date: dt.date | None = None, building_id: int | None = None, user: User = AdminUser, s: Session = _DB):
    return analytics.free_slots(s, user.school_id, date or clock.local_today(), building_id)


@router.get("/analytics/reservations", response_model=S.ResvStatsOut)
def analytics_resv(from_: dt.date | None = Query(None, alias="from"), to: dt.date | None = None,
                   group: Literal["day", "week"] = "day", user: User = AdminUser, s: Session = _DB):
    d0, d1 = analytics.parse_range(from_, to, clock.local_today())
    return analytics.reservation_stats(s, user.school_id, d0, d1, group, clock.local_now())


@router.get("/analytics/latency", response_model=S.LatencyOut)
def analytics_latency(from_: dt.date | None = Query(None, alias="from"), to: dt.date | None = None,
                      type: Literal["SLOT_SET", "RESV_SET", "all"] = "all", user: User = AdminUser, s: Session = _DB):
    d0, d1 = analytics.parse_range(from_, to, clock.local_today())
    return analytics.latency(s, user.school_id, d0, d1, type)


@router.get("/analytics/latency/samples", response_model=list[S.LatencySampleOut])
def analytics_samples(from_: dt.date | None = Query(None, alias="from"), to: dt.date | None = None,
                      type: Literal["SLOT_SET", "RESV_SET", "all"] = "all", limit: int = Query(100, ge=1, le=1000),
                      user: User = AdminUser, s: Session = _DB):
    d0, d1 = analytics.parse_range(from_, to, clock.local_today())
    return analytics.latency_samples(s, user.school_id, d0, d1, type, limit)
```

스키마:

```python
class AllocationOut(BaseModel):
    key: int
    label: str
    assigned_min: int
    unused_min: int
    total_min: int
    rate: float


class FreeRange(BaseModel):
    from_: str = Field(alias="from")
    to: str
    model_config = ConfigDict(populate_by_name=True)


class FreeSlotsOut(BaseModel):
    room_id: int
    room: int
    building: str
    free: list[FreeRange]


class ResvStatsRow(BaseModel):
    date: str
    requested: int
    approved: int
    rejected: int
    cancelled: int
    expired: int
    no_show: int
    checked_in: int


class ResvStatsOut(BaseModel):
    series: list[ResvStatsRow]
    totals: dict[str, int]
    no_show_rate: float
    checkin_rate: float


class LatencyBin(BaseModel):
    ge: int
    lt: int | None
    count: int


class LatencyOut(BaseModel):
    n: int
    bins: list[LatencyBin]
    p50: float | None
    p95: float | None
    max: float | None
    within_30s: float
    within_90s: float


class LatencySampleOut(BaseModel):
    outbox_id: int
    room_id: int
    bld: str
    room: int
    unit: int
    type: str
    created_at: dt.datetime
    finished_at: dt.datetime
    seconds: float
```

`FreeRange` 의 `from` 키: 응답 직렬화에 `by_alias=True` 가 필요 — 라우터 `response_model_by_alias=True`(기본값 True) 라 그대로.

- [ ] **Step 4: 통과·커밋**

```bash
git add app/domain/analytics.py app/domain/admin_resv_router.py app/schemas.py tests/test_analytics.py
git commit -m "feat(server): 분석 집계 — 배정률·공강·예약 통계(No-show)·갱신 지연 히스토그램·샘플"
```

---

### Task 9: 문서·진행도

- `server/README.md`: 학생 API·관리자 예약·jobs·analytics 절(경로 한 줄씩 + spec 링크), `.env` 변경 없음, "일일 작업은 KST 04:00, 수동 `POST /api/admin/jobs/daily`".
- `docs/progress.html`: wj-13 PR란 `백엔드: S10 (PR #…)`. wj-11 의 "50회 표" 는 `analytics/latency/samples` 로 제공된다고 메모.
- 커밋 `docs(server): 학생·관리자 예약·일일 작업·분석 API README, 진행도`.

---

## Self-review

- **Spec coverage:** §2.1 스키마·전이·No-show → T1·T3·T8. §2.2 시각·`put_resv` KST·`DAILY_HOUR_LOCAL` → T1·T7. §2.3 `room_state`·벡터 8 → T2. §2.4 제약 7개·선착순·승인 재검사 → T3(T5 라우터 422/400/404/409). §2.5 일일 작업 5단계·트리거·수동 → T7. §2.6 정의(배정 집합·휴강 unused·No-show·bin·within) → T8. §3 스코프(학생 404·관리자 학교·남의 예약 라벨) → T4·T5·T6. §4.1 7개 → T4·T5. §4.2 6개 + 요약 버킷 → T6·T7. §4.3 5개 → T8. §5 README → T9.
- **Placeholder scan:** 없음 (테스트 기대값은 본문에서 확정: p95 = 95, 20시 슬롯 구간 2개, `by_w[0].key == 3`).
- **Type consistency:** `clock.*` T1 = 전 Task. `room_state.Span(s, e, type, label, mine, id)`·`room_state()`·`load_inputs()`·`state_of()`·`fmt_hhmm()` T2 = T4·T8. `reserve.validate_request(s, user, room, body, now_local)`·`approve/reject/cancel(by_admin=)/checkin` T3 = T5·T6. `_mine_out`·`_student_room` T4/T5 = T6 `admin.resv_admin_out`. `_free_id(s, Reservation)` = S4b T2. `daily.run_daily(Session, now_utc=None)`·`tick`·`already_ran_today` T7 = T7 테스트·라우터. `analytics.parse_range/allocation/free_slots/reservation_stats/latency/latency_samples` T8 = 라우터. conftest `student_hdr`·`other_student_hdr`·`student_hdr_school2` T3 = T4·T5·T8. `live`·`db`·`hub` 는 S2 conftest.

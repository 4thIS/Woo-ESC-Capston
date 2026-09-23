# S10 — 학생 API·관리자 승인·일일 작업·분석 집계 구현 계획 (plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

- 생성일시: 2026-09-23
- 기준 spec: `docs/specs/2026-09-23-s10-student-analytics-design.md`. **선행: S4a → S2c → S4b 완료** — `app.deps._DB`, `app.auth.deps.{AdminUser, StudentUser}`, `app.auth.scope.get_scoped`, `domain/router.py` 의 `_addr`(3-튜플)·`_commit_notify`·`_free_id`·`_ID_LOCK`·`_existing_same_room`, `api.enqueue_*(session=)`·`api.notify`, `domain/admin.py`, conftest `client`(학교 1 관리자)·`school`·`client_raw`·`other_admin_hdr` 를 쓴다.
- 개정: r2 (PR #38 리뷰 — approve·cancel 은 `session=s`+커밋 뒤 notify(🔴5), RecordProvider 에 `approved`·KST 창(🔴6), 승격은 `오늘+7` 만(🔴7), 재동기는 FILE kind·방별 try·유닛별(🔴8), tzdata(🔴10), 테스트 정정, 학생 신청 일일 상한·신청 철회는 행 삭제, 04시 이전 수동 실행이 자동을 막지 않음, 창 밖 취소는 RESV_DEL 없음).
- 개정: r3 (PR #38 cw 재검토 — **`reservations.pushed_at`** 으로 노드 전송 여부를 예약 행에 기록: 승격 = `approved ∧ 오늘≤date≤오늘+7 ∧ pushed_at IS NULL`(하루 놓쳐도 따라잡음, id 재사용 오판 없음), RESV_DEL 은 `pushed_at` 있을 때만, 날짜를 창 밖으로 옮기면 RESV_DEL. 승격은 예약마다 자기 트랜잭션. 학생 신청 검증·관리자 승인을 `_ID_LOCK` 안으로. 일일 작업 실행 락·sleep 먼저. 테스트 3곳 정정).
- 담당: wj @leemonta9482. 브랜치 `feature/s10-student`. 커밋 scope `feat(server)`. PR은 사용자 지시 시. Task 1~7(학생·승인·일일 작업)과 Task 8(분석)은 PR 을 둘로 나눠도 된다.

**Goal:** 학생이 자기 학교의 지금 빈 강의실·방 주간 표를 보고 예약을 신청·취소·체크인하며, 관리자가 승인해 노드로 보내고, 04:00 일일 작업이 만료·승격·재동기·정리를 하고, 관리자가 배정률·공강·예약 통계·갱신 지연 히스토그램을 받는다.

**Architecture:** 순수 계산은 `app/domain/{clock, room_state, reserve, daily, analytics}.py`(세션·값 → 값), 라우터는 `student_router.py`(학생)·`admin_resv_router.py`(예약 승인·jobs·analytics) 두 파일. 시각은 `clock.now_utc()` 한 곳에서만 읽어 테스트가 monkeypatch 한다. `lora_service/api.py` 는 `enqueue_resv_set/resv_del/full_sync` 호출만.

**Tech Stack:** Python 3.12(`zoneinfo`) · uv · FastAPI 0.141 · SQLAlchemy 2 · Alembic · pydantic 2 · pytest · ruff

**Spec:** `docs/specs/2026-09-23-s10-student-analytics-design.md`

## Global Constraints

- `SCHOOL_TZ = Asia/Seoul`. DB naive UTC. 요일·오늘·운영 시간·창 판정은 지역 시각. `DAILY_HOUR_LOCAL = 4`.
- `room_state`: 우선순위 예약(approved) > 시험기간 > 기본. `typeToLayout` 1→1, 2→5, 3→3, 4→4, 5→6, 6→7. 수업(type 1) 슬롯 안 분<50 → 1, ≥50 → 2. 시험기간 + 슬롯 안 → 5. 슬롯 밖 → 4. 빈 = 4. `until` = 다음 변화 시각 또는 자정.
- 신청 제약: 날짜 오늘~+7(KST) 400 · 5분 단위·시작<끝 422 · 15~120분 400 · 과거 400 · 학생당 requested+미래 approved ≤ 3 → 400 · `reservable`·자기 학교 아니면 404 · 슬롯/approved·requested 예약/시험기간 겹침 409. `type=6`, `professor=""`. 승인 시 겹침 재검사 409.
- 전이: `requested → approved|rejected|expired`, `approved → cancelled`. 학생이 `requested` 를 취소하면 **행 삭제**(철회 — id 반환). 학생 취소: approved 는 시작 전만(409). 관리자 취소: 시작 후도. `RESV_DEL` 은 **노드로 보낸 적 있는(`pushed_at` 있음) 예약만**. 이미 시작한 신청은 승인 409. 체크인 창 시작−10분 ≤ 지금 ≤ 시작+15분(409). 학생 신청 **하루 10회**(429).
- approve·cancel·승격은 `api.enqueue_*(…, session=s)` → 호출자가 `_commit_notify(s, modem_id)` (BackgroundTasks·별도 세션 금지 — S2c).
- **`pushed_at` 은 `reserve.push_set`/`push_del` 두 함수만 바꾼다** — RESV_SET 을 enqueue 하면 지금 시각, RESV_DEL 을 enqueue 하거나 노드에 없는 것으로 확정되면 NULL. 호출처: approve·관리자 작성/수정(`_write_resv`)·삭제(`delete_resv`)·취소·승격.
- 예약 쓰기의 **읽기~커밋은 전부 `_ID_LOCK` 안**: 학생 신청·철회·취소, 관리자 승인·거절·취소·작성·삭제, 승격의 예약별 트랜잭션. 락 밖에서 읽은 상태로 쓰면 동시 승인과 엇갈려 노드에 유령 예약이 남는다(자체 점검 🟡).
- **방당 예약 상한 `NODE_RESV_MAX = 24`**(노드 `Resv resv[24]`, v2 §5.1 — 넘으면 `STORE_FAIL`). 학생 신청·승인·관리자 창 안 작성은 방의 창(오늘~+7) 안 approved+requested 가 24 면 409. `record_provider` 는 창 안 예약을 (date, s_h, s_m) 순 앞 24 개만 — FILE 이 통째로 거부되지 않게. 승격은 방의 창 안 보낸 수가 24 면 건너뛰고 오류에 남긴다.
- 노드 문 앞 e-Paper 는 공개 — **학생 예약(`requested_by` 있음)의 과목은 노드에 `"학생 예약"` 으로 보낸다**(`reserve.node_subject`). 학생 API 가 남의 과목을 숨기는 규칙과 맞춘다.
- 이미 끝난 예약(오늘 날짜라도 종료 시각 지남)은 승격·RESV_DEL 하지 않는다 — 쓸모없는 웨이크. pysqlite 는 DML 전까지 트랜잭션을 열지 않아 락 안의 SELECT 는 최신 커밋을 본다.
- 남의 예약은 `label="예약됨"`·`mine=false`·`subject` 없음.
- 일일 작업 5단계(만료 · 승격(`approved ∧ 오늘 ≤ date ≤ 오늘+7 ∧ pushed_at IS NULL`, **예약마다 자기 트랜잭션**) · 실패 재동기(24 h, `last_error≠cancelled`, FILE 은 `payload.kind` 로, CMD/SET_ROOM/TIME 제외, **(bld, room, unit) 별** `enqueue_full_sync(…, unit=u)`, 방마다 try) · 정리(예약 90일, 거절·만료 7일, job_runs 90일, 토큰 7일) · 기록), 단계별 트랜잭션·오류 계속. `daily_loop` 60 s tick, 하루 1회 = **오늘 04:00(KST) 이후** 실행 기록이 있으면 건너뜀(그 전 수동 실행은 세지 않음), 수동 실행은 항상. 자동·수동이 겹치지 않게 `daily._RUN_LOCK`. `daily_loop` 는 **sleep 먼저**(기동 직후·테스트 중 실제 시각으로 돌지 않게).
- `topology.record_provider`: 예약은 `status == 'approved'` 만, `today` 기본값 `clock.local_today` (계약 ③ 구현 변경 — cw 리뷰).
- 분석: 운영 시간 09~21, 배정 = layout ∈ {1,2,3,5,6,7}, 휴강 3 은 `unused_min`. 예약 통계 상태별 + No-show(`approved`·`requested_by`·종료 지남·미체크인). 지연 = acked·SLOT_SET/RESV_SET·`finished_at−created_at` 초, bin `[0,10,20,30,45,60,90,120,∞)`, p50/p95/max/n/within_30s/within_90s. 기간 기본 30일·최대 90일(422).
- S4b 요약에 `pending_reservations` 버킷 추가(additive). `put_resv` 창 판정 KST.
- 마이그레이션 additive(`web_student`), CHECK 는 전부 이름 붙임(`ck_resv_id`·`ck_resv_status`). 의존성 `tzdata` 추가(Windows 는 시스템 tz DB 없음). `lora_service/api.py`·`hub.py`·`lora_proto/` 불변. 기존 테스트 그대로.
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
- Modify: `server/pyproject.toml`(`tzdata`), `server/app/domain/models.py`, `server/app/domain/router.py`(`put_resv`·`_existing_same_room`), `server/app/domain/topology.py`(`record_provider`), `server/app/schemas.py`, `server/tests/conftest.py`(`students`)
- Test: `server/tests/test_clock_migration.py`

**Interfaces:**
- Produces: `clock.SCHOOL_TZ`, `clock.now_utc() -> datetime`(naive UTC; 테스트가 monkeypatch), `clock.to_local(naive_utc) -> datetime`(naive 지역), `clock.to_utc(naive_local) -> datetime`, `clock.local_now()`, `clock.local_today() -> date`, `clock.week_start(date) -> date`(월요일), `clock.local_dt(date, h, m) -> datetime`. `Reservation.{status, requested_by, requested_at, decided_at, decided_by, reject_reason, checked_in_at, cancelled_at, pushed_at}`, `JobRun(id, name, ran_at, result)`. `delete_resv` 는 없는 id·다른 방 id 에 200 `{"outbox_ids": []}`(멱등, RESV_DEL 없음). `S.ResvOut` 에 `status` 노출. conftest `students`(s1@mju.ac.kr·s2@mju.ac.kr 학교 1, s3@other.ac.kr 학교 2, 학번 `S1`·`S2`·`S3`, active) — **`school` 과 별도 픽스처**(S4a·S4b 의 사용자 목록 단언을 건드리지 않게).

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
            "checked_in_at", "cancelled_at", "pushed_at"} <= cols


def test_put_resv_window_is_local_date(client, app, school, students, monkeypatch):
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
    # 학생 신청(requested) 행은 id 지정 upsert 로 못 고친다 — 미승인 RESV_SET 방지 (리뷰 🔴4a)
    with app.state.Session() as s, s.begin():
        s.add(Reservation(id=50, room_id=rid, date=dt.date(2026, 9, 24), s_h=9, s_m=0, e_h=10, e_m=0, type=6,
                          subject="신청", professor="", status="requested", requested_by="s1@mju.ac.kr"))
    assert client.post(f"/api/rooms/{rid}/reservations", json={**body, "id": 50}).status_code == 409



def test_record_provider_only_approved_and_local_window(app, students, monkeypatch):
    """FILE 재동기에 신청·취소 예약이 실리지 않고, 창은 KST 오늘 기준 (리뷰 🔴6)."""
    from app.domain.models import Building, Room
    from app.domain.topology import record_provider

    monkeypatch.setattr(clock, "now_utc", lambda: dt.datetime(2026, 9, 22, 19, 0))  # KST 9/23 04:00
    with app.state.Session() as s, s.begin():
        b = Building(school_id=1, name="E동", bld="E")
        s.add(b)
        s.flush()
        r = Room(building_id=b.id, room=101, units=1)
        s.add(r)
        s.flush()
        for i, (d, st) in enumerate([(dt.date(2026, 9, 30), "approved"), (dt.date(2026, 9, 24), "requested"),
                                     (dt.date(2026, 9, 24), "cancelled"), (dt.date(2026, 9, 23), "approved")], start=1):
            s.add(Reservation(id=i, room_id=r.id, date=d, s_h=9, s_m=0, e_h=10, e_m=0, type=6, subject="x",
                              professor="", status=st, requested_by="s1@mju.ac.kr" if st != "approved" else None))
    recs = record_provider(app.state.Session)("E", 101, "resv")
    assert sorted(x.resv_id for x in recs) == [1, 4]  # 9/30 = KST 오늘+7 포함, 신청·취소 제외


def test_resv_id_check_survives_migration(tmp_path):
    from sqlalchemy import create_engine, text

    import pytest

    db = tmp_path / "c.db"
    _upgrade(db)
    with create_engine(f"sqlite:///{db}").begin() as c:
        c.execute(text("INSERT INTO schools (id, name, net_id) VALUES (1,'a',75)"))
        c.execute(text("INSERT INTO buildings (id, school_id, name, bld) VALUES (1,1,'x','E')"))
        c.execute(text("INSERT INTO rooms (id, building_id, room, units) VALUES (1,1,101,1)"))
    with pytest.raises(Exception), create_engine(f"sqlite:///{db}").begin() as c:  # batch 재생성 뒤에도 CHECK 유지
        c.execute(text("INSERT INTO reservations (id, room_id, date, s_h, s_m, e_h, e_m, type, subject, professor)"
                       " VALUES (70000, 1, '2026-09-24', 9, 0, 10, 0, 6, 'x', '')"))
```

상단 import 에 `from app.domain.models import Reservation` 추가.

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_clock_migration.py -q` → FAIL

- [ ] **Step 2b: 의존성·학생 픽스처**

`uv add tzdata` — Windows 엔 시스템 tz DB 가 없어 `ZoneInfo("Asia/Seoul")` 가 `ZoneInfoNotFoundError`(리뷰 🔴10, CI ubuntu 에선 가려짐).

`server/tests/conftest.py`:

```python
@pytest.fixture
def students(app, school):
    """학생 3명 (학교 1 에 2명, 학교 2 에 1명). school 과 분리 — 사용자 목록 단언을 건드리지 않게."""
    with app.state.Session() as s, s.begin():
        s.add_all([
            User(email="s1@mju.ac.kr", school_id=1, role="student", status="active", name="학생1", student_no="S1", pw_hash=password.hash("password1")),
            User(email="s2@mju.ac.kr", school_id=1, role="student", status="active", name="학생2", student_no="S2", pw_hash=password.hash("password1")),
            User(email="s3@other.ac.kr", school_id=2, role="student", status="active", name="타교생", student_no="S3", pw_hash=password.hash("password1")),
        ])


@pytest.fixture
def student_hdr(app, students):
    return _hdr(app, "s1@mju.ac.kr")


@pytest.fixture
def other_student_hdr(app, students):
    return _hdr(app, "s2@mju.ac.kr")


@pytest.fixture
def student_hdr_school2(app, students):
    return _hdr(app, "s3@other.ac.kr")
```

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
    # 마지막으로 RESV_SET 을 enqueue 한 시각. NULL = 노드에 없다(안 보냈거나 RESV_DEL 로 지움).
    # 승격·RESV_DEL 판단을 outbox 이력 대신 이 칸으로 — id 재사용·놓친 날에 안전 (S10 §2.5, r3)
    pushed_at: Mapped[dt.datetime | None]
    __table_args__ = (
        CheckConstraint("id BETWEEN 1 AND 65535", name="ck_resv_id"),
        CheckConstraint("status IN ('requested','approved','rejected','cancelled','expired')", name="ck_resv_status"),
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

Run: `uv run alembic revision -m "web_student"` → `down_revision` = web_auth rev. `upgrade`: `op.create_table("job_runs", …)` + `op.create_index`, `with op.batch_alter_table("reservations") as b:` 9 컬럼(`pushed_at` 포함) `add_column`(`status` 는 `nullable=False, server_default="approved"`), `b.create_check_constraint("ck_resv_status", "status IN (...)")`, `b.create_check_constraint("ck_resv_id", "id BETWEEN 1 AND 65535")`(batch 재생성이 기존의 이름 없는 CHECK 를 지운다 — 리뷰 🟡, 실측), `b.create_foreign_key("fk_resv_requester", "users", ["requested_by"], ["email"])`, `b.create_index("ix_resv_room_date", ["room_id", "date"])`, `b.create_index("ix_resv_requester", ["requested_by", "status"])`. `downgrade` 역순. alembic 엔진은 원래 FK OFF 라 batch 재생성이 FK 에 막히지 않는다 — **`env.py` 는 건드리지 않는다**(연결에 SQL 을 먼저 실행하면 마이그레이션 전체가 조용히 롤백된다 — S4a T2, r3). **기존 예약의 `pushed_at` 을 채운다**(자체 점검 🟡): S2 는 창 안 예약을 이미 노드로 보냈으므로, NULL 로 두면 배포 직후 삭제·취소에 RESV_DEL 이 안 나가 노드에 유령 예약이 남고, 첫 일일 작업이 창 안 예약을 한낮에 전부 다시 보낸다. `batch_alter_table` 블록 **뒤에** `op.execute("UPDATE reservations SET pushed_at = CURRENT_TIMESTAMP WHERE date BETWEEN date('now', '+9 hours') AND date('now', '+9 hours', '+7 days')")` — KST 오늘~+7. 창 밖은 NULL 로 두어 승격 대상.

- [ ] **Step 5: `put_resv` KST + `ResvOut.status`**

`server/app/domain/router.py`:
- `_write_resv`(S4b): `today = dt.datetime.now(dt.UTC).date()` → `today = clock.local_today()` (`from app.domain import clock`). 관리자 생성은 `status` 기본값 `approved`. (`pushed_at` 을 쓰는 교체는 `reserve.py` 가 생기는 T3 Step 4b.)
- `_existing_same_room`(S4b): 예약이면 `obj.status != "approved"` 도 409 `"신청 상태 예약은 승인 절차로"` — 학생 신청 행을 id 지정 upsert 로 고쳐 미승인 RESV_SET 이 나가는 것을 막는다(리뷰 🔴4a).

```python
    if obj is not None and getattr(obj, "status", "approved") != "approved":
        raise HTTPException(409, "신청 상태 예약은 승인 절차로 처리하세요")
```

`server/app/schemas.py` `ResvOut` 에 `status: str = "approved"` 추가.

`server/app/domain/topology.py` `record_provider`(계약 ③ 구현 — cw 리뷰):
- `today: Callable[[], dt.date] = _utc_today` → `today = clock.local_today` (`_utc_today` 삭제). 04:00 KST 일일 작업이 UTC 전날 기준 창으로 FILE 을 만들어, 막 보낸 `오늘+7` RESV_SET 을 노드에서 지우던 문제(리뷰 🔴6).
- 예약 조회에 `Reservation.status == "approved"` — 신청·거절·취소·만료 예약이 FILE 로 노드에 가지 않게.
- 예약은 `.order_by(Reservation.date, Reservation.s_h, Reservation.s_m).limit(24)`(`NODE_RESV_MAX`, `app.domain.reserve` 에 정의 — T1 에선 `topology.py` 에 같은 값 상수를 두고 T3 의 `reserve.NODE_RESV_MAX` 가 그것을 import) — 노드 용량을 넘는 FILE 이 통째로 `STORE_FAIL` 나지 않게.
- `ResvSet` 의 `subject` 는 `r.subject if r.requested_by is None else "학생 예약"` — 문 앞 e-Paper 는 공개라 학생이 적은 목적(이름 등)을 싣지 않는다(학생 API 가 남의 과목을 숨기는 규칙과 동일).

- [ ] **Step 6: 통과·커밋**

Run: `uv run pytest -q` → PASS. ruff.

```bash
git add pyproject.toml uv.lock app/domain/clock.py app/domain/models.py app/domain/router.py app/domain/topology.py app/schemas.py alembic/versions tests/conftest.py tests/test_clock_migration.py
git commit -m "feat(server): 학교 시간대 clock, reservations 신청 컬럼·job_runs 마이그레이션, put_resv 창 KST 판정"
```

---

### Task 2: `room_state.py` — v2 §5.3 서버판 + 벡터 8개

**Files:**
- Create: `server/app/domain/room_state.py`, `server/tests/fixtures/room_state_vectors.json`
- Test: `server/tests/test_room_state.py`

벡터는 **JSON 픽스처**로 둔다 — 펌웨어 `determineLayout`(S8, cw)이 같은 파일을 읽어 대조할 수 있게(리뷰 답 3). 단위는 **자정부터의 분**(`at`, `s`, `e`, `until`), "수업 50분 규칙"의 분은 **시각의 분(minute-of-hour)** 이다(09:50 = 50분 → 쉬는시간). 휴강·특강 슬롯 벡터(5·6)는 **잠정** — v2 §5.3 은 수업 슬롯만 명시하므로 cw 가 노드 쪽을 같은 `typeToLayout` 로 맞추기로 한 합의(PR #38)를 따른다. 야간 교시(#14)는 확정 전까지 xfail.

`server/tests/fixtures/room_state_vectors.json`:

```json
{
  "note": "분 = 자정부터의 분. 50분 규칙의 분은 시각의 분(minute-of-hour). tentative 벡터는 PR #38 합의(비수업 슬롯은 typeToLayout)로 잠정.",
  "slots": [
    {"s": 540, "e": 650, "type": 1, "label": "수업"},
    {"s": 660, "e": 720, "type": 3, "label": "휴강"},
    {"s": 780, "e": 840, "type": 5, "label": "특강"},
    {"s": 900, "e": 960, "type": 6, "label": "대여"},
    {"s": 960, "e": 1020, "type": 2, "label": "시험"}
  ],
  "vectors": [
    {"name": "1-resv-beats-slot", "resvs": [{"s": 540, "e": 600, "type": 6}], "in_exam": false, "at": 570, "layout": 7, "until": 600},
    {"name": "2-exam-period-in-slot", "resvs": [], "in_exam": true, "at": 570, "layout": 5, "until": 650},
    {"name": "3-class-minute-lt-50", "resvs": [], "in_exam": false, "at": 570, "layout": 1, "until": 590},
    {"name": "4-class-minute-ge-50", "resvs": [], "in_exam": false, "at": 590, "layout": 2, "until": 600},
    {"name": "5-cancelled-slot", "tentative": true, "resvs": [], "in_exam": false, "at": 690, "layout": 3, "until": 720},
    {"name": "6-special-slot", "tentative": true, "resvs": [], "in_exam": false, "at": 810, "layout": 6, "until": 840},
    {"name": "7-outside-slot-next-start", "resvs": [], "in_exam": false, "at": 750, "layout": 4, "until": 780},
    {"name": "8-free-until-midnight", "resvs": [], "in_exam": false, "at": 1410, "layout": 4, "until": null},
    {"name": "9-night-class-45+5", "xfail": "야간 교시(45분+5분, 시각 비정렬) — #14 확정 전", "resvs": [], "in_exam": false, "at": 1085, "layout": 2, "until": 1090}
  ]
}
```

(벡터 9 는 18:00 시작 45분 수업 뒤 5분 쉬는시간을 가정한 자리 — 슬롯 목록에 야간 교시가 없으므로 지금은 xfail 로 자리만 잡는다.)

**Interfaces:**
- Produces: `TYPE_TO_LAYOUT = {1: 1, 2: 5, 3: 3, 4: 4, 5: 6, 6: 7}`, `FREE = 4`; `Span(s: int, e: int, type: int, label: str, mine: bool=False)`(분 단위 0..1440); `room_state(slots: list[Span], resvs: list[Span], in_exam: bool, at_min: int) -> tuple[int, int | None]`(layout, until_min); `load_inputs(s, room_id, date, viewer_email=None) -> tuple[list[Span], list[Span], bool]`; `state_of(s, room_id, at_local) -> tuple[int, int | None]`; `fmt_hhmm(m: int | None) -> str | None`.

- [ ] **Step 1: 실패 테스트**

`server/tests/test_room_state.py`:

```python
import datetime as dt
import json
import pathlib

import pytest

from app.domain import room_state as RS
from app.domain.room_state import Span

M = lambda h, m=0: h * 60 + m  # noqa: E731
SLOTS = [Span(M(9), M(10, 50), 1, "수업"), Span(M(11), M(12), 3, "휴강"), Span(M(13), M(14), 5, "특강"),
         Span(M(15), M(16), 6, "대여"), Span(M(16), M(17), 2, "시험")]


VECTORS = json.loads((pathlib.Path(__file__).parent / "fixtures" / "room_state_vectors.json").read_text(encoding="utf-8"))


def _spans(xs):
    return [Span(x["s"], x["e"], x["type"], x.get("label", "")) for x in xs]


@pytest.mark.parametrize("v", VECTORS["vectors"], ids=[v["name"] for v in VECTORS["vectors"]])
def test_room_state_vectors(v):
    if v.get("xfail"):
        pytest.xfail(v["xfail"])
    got = RS.room_state(_spans(VECTORS["slots"]), _spans(v["resvs"]), v["in_exam"], v["at"])
    assert got == (v["layout"], v["until"])


def test_room_state_exam_only_during_slots_and_resv_beats_exam():
    assert RS.room_state(SLOTS, [], True, M(12, 30)) == (4, M(13))  # 시험기간이라도 슬롯 밖은 빈
    assert RS.room_state(SLOTS, [Span(M(12), M(13), 6, "r")], True, M(12, 30)) == (7, M(13))
    assert RS.room_state([], [], False, M(10)) == (4, None)
    assert RS.room_state(SLOTS, [Span(M(10, 50), M(11, 30), 6, "r")], False, M(9, 55)) == (2, M(10))  # 쉬는시간 → 정각 수업


def test_type_map_and_fmt():
    assert RS.TYPE_TO_LAYOUT == {1: 1, 2: 5, 3: 3, 4: 4, 5: 6, 6: 7} and RS.FREE == 4
    assert RS.fmt_hhmm(M(9, 5)) == "09:05" and RS.fmt_hhmm(None) is None


def test_load_inputs_and_state_of(app, school, students):
    _, ids = _building(app, 1, "E")
    rid = ids[101]
    _slot(app, rid, 3, 9, 0, 10, 50)                       # 수요일
    _resv(app, rid, dt.date(2026, 9, 23), 13, 0, 14, 0, id_=1, requested_by="s1@mju.ac.kr", subject="스터디")
    _resv(app, rid, dt.date(2026, 9, 23), 15, 0, 16, 0, id_=2, status="requested")  # 신청 중은 제외
    _exam(app, rid, 1, dt.date(2026, 9, 22), dt.date(2026, 9, 24))
    with app.state.Session() as s:
        slots, resvs, in_exam = RS.load_inputs(s, rid, dt.date(2026, 9, 23), viewer_email="s1@mju.ac.kr")
        assert [(x.s, x.e, x.type) for x in slots] == [(M(9), M(10, 50), 1)]
        assert [(x.s, x.e, x.label, x.mine) for x in resvs] == [(M(13), M(14), "스터디", True)]
        assert in_exam is True
        assert RS.load_inputs(s, rid, dt.date(2026, 9, 23), viewer_email="s2@mju.ac.kr")[1][0].label == "예약됨"
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
git add app/domain/room_state.py tests/test_room_state.py tests/fixtures/room_state_vectors.json
git commit -m "feat(server): room_state — v2 §5.3 determineLayout 서버판 + until, 벡터 8개"
```

---

### Task 3: `reserve.py` — 제약 검증·겹침·전이

**Files:**
- Create: `server/app/domain/reserve.py`
- Modify: `server/app/schemas.py`(`StudentResvIn`), `server/app/domain/router.py`(`_write_resv`·`delete_resv` 가 `pushed_at` 사용)
- Test: `server/tests/test_reserve.py`

**Interfaces:**
- Consumes: T1 conftest `students`·`student_hdr` 등, S2c `api.enqueue_*(session=)`.
- Produces: `reserve.MAX_ACTIVE = 3`, `MIN_MIN = 15`, `MAX_MIN = 120`, `CHECKIN_BEFORE = 10`, `CHECKIN_AFTER = 15`, `STUDENT_TYPE = 6`; `reserve.addr(s, r) -> tuple[str, int, str | None]`(bld, room, modem_id); `reserve.overlaps(s, room_id, date, s_min, e_min, exclude_id=None) -> bool`; `reserve.validate_request(s, user, room, body, now_local) -> None`(HTTPException 400/409); `reserve.start_local(r)`, `reserve.end_local(r)`, `reserve.in_window(date, today) -> bool`; `reserve.push_set(s, r) -> list[int]`(RESV_SET enqueue + `pushed_at=지금`), `reserve.push_del(s, r, today, date=None) -> list[int]`(`pushed_at` 있고 날짜(`date` 주면 그 날짜 — 옮기기 전) ≥ 오늘이면 RESV_DEL, 어느 쪽이든 `pushed_at=None`); `reserve.approve(s, r, admin_email, now_local) -> list[int]`; `reserve.reject(s, r, admin_email, reason, now_local)`; `reserve.cancel(s, r, *, by_admin, now_local) -> list[int]`; `reserve.withdraw(s, r) -> None`(requested 행 삭제); `reserve.checkin(s, r, now_local)`. **`approve`·`cancel` 은 `enqueue_*(…, session=s)` 로 쓰고 커밋하지 않는다 — 호출자(라우터)가 `_commit_notify(s, reserve.addr(s, r)[2])`** (별도 세션 enqueue 는 도메인 쓰기 락과 5 s 뒤 `database is locked`, 리뷰 🔴5).

- [ ] **Step 1: 실패 테스트**

`server/tests/test_reserve.py` (공용 헬퍼 복사 + `from fastapi import HTTPException`, `from sqlalchemy import select`, `from app import schemas as S`, `from app.auth.models import User`, `from app.domain import reserve`, `from app.domain.models import Room`, `from app.lora_service.models import Outbox`):

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


def test_constraints(app, students, monkeypatch):
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


def test_student_transitions(app, students, monkeypatch):
    _fix_clock(monkeypatch)  # KST 9/23 10:30
    _, ids = _building(app, 1, "E")
    rid = ids[101]
    a = _resv(app, rid, dt.date(2026, 9, 24), 13, 0, 14, 0, id_=1, status="requested", requested_by="s1@mju.ac.kr", requested_at=UTC_NOW)
    b = _resv(app, rid, dt.date(2026, 9, 23), 10, 25, 11, 0, id_=2, status="approved", requested_by="s1@mju.ac.kr")  # 5분 전 시작
    with app.state.Session() as s, s.begin():
        reserve.withdraw(s, s.get(Reservation, a))            # 신청 철회 = 행 삭제 (id 반환)
    with app.state.Session() as s, s.begin():
        assert s.get(Reservation, a) is None
        r2 = s.get(Reservation, b)
        with pytest.raises(HTTPException) as e:
            reserve.cancel(s, r2, by_admin=False, now_local=clock.local_now())
        assert e.value.status_code == 409                    # 시작된 예약은 학생이 못 취소
        reserve.checkin(s, r2, clock.local_now())            # 시작 +5분 → 창 안
        assert r2.checked_in_at is not None
        with pytest.raises(HTTPException):
            reserve.checkin(s, r2, clock.local_now())        # 재체크인
    c = _resv(app, rid, dt.date(2026, 9, 23), 10, 14, 11, 0, id_=3, status="approved", requested_by="s1@mju.ac.kr")
    with app.state.Session() as s, s.begin(), pytest.raises(HTTPException):
        reserve.checkin(s, s.get(Reservation, c), clock.local_now())  # 10:14 시작, 지금 10:30 = +16분 → 창 밖


def test_approve_reject_cancel_enqueue_in_same_session(db, hub, app, students, monkeypatch):
    """approve·cancel 은 호출자 세션으로 RESV_SET/DEL 을 쓴다 — 커밋 전엔 notify 없음, 커밋하면 행이 보인다."""
    _fix_clock(monkeypatch)
    _, ids = _building(app, 1, "E", rooms=((301, 2),))  # FakeTopo("E", 301) = units 2, modem m1
    rid = ids[301]
    a = _resv(app, rid, dt.date(2026, 9, 24), 13, 0, 14, 0, id_=1, status="requested", requested_by="s1@mju.ac.kr")
    far = _resv(app, rid, dt.date(2026, 10, 15), 13, 0, 14, 0, id_=2, status="requested", requested_by="s1@mju.ac.kr")
    started = _resv(app, rid, dt.date(2026, 9, 23), 10, 0, 11, 0, id_=4, status="requested", requested_by="s2@mju.ac.kr")
    with app.state.Session() as s, s.begin():
        assert len(reserve.approve(s, s.get(Reservation, a), "admin@mju.ac.kr", clock.local_now())) == 2
        assert s.get(Reservation, a).status == "approved" and hub.notified == []
        assert s.get(Reservation, a).pushed_at is not None      # 보냈다
        assert reserve.approve(s, s.get(Reservation, far), "admin@mju.ac.kr", clock.local_now()) == []  # 창 밖 → 일일 작업이 승격
        assert s.get(Reservation, far).pushed_at is None
        with pytest.raises(HTTPException) as e:
            reserve.approve(s, s.get(Reservation, started), "admin@mju.ac.kr", clock.local_now())
        assert e.value.status_code == 409                    # 이미 시작한 신청은 승인 불가
        assert reserve.addr(s, s.get(Reservation, a)) == ("E", 301, None)  # 테스트 건물엔 modem 없음
    _resv(app, rid, dt.date(2026, 9, 24), 13, 30, 14, 30, id_=3, status="requested", requested_by="s2@mju.ac.kr")
    with app.state.Session() as s, s.begin():
        with pytest.raises(HTTPException) as e:
            reserve.approve(s, s.get(Reservation, 3), "admin@mju.ac.kr", clock.local_now())
        assert e.value.status_code == 409                    # 겹침 재검사
        r = s.get(Reservation, 3)
        reserve.reject(s, r, "admin@mju.ac.kr", "겹침", clock.local_now())
        assert r.status == "rejected" and r.reject_reason == "겹침"
        assert len(reserve.cancel(s, s.get(Reservation, a), by_admin=True, now_local=clock.local_now())) == 2
        assert reserve.cancel(s, s.get(Reservation, far), by_admin=True, now_local=clock.local_now()) == []  # 안 보낸 것 → DEL 없음
        assert s.get(Reservation, a).pushed_at is None
    with db() as s:
        assert [o.type for o in s.scalars(select(Outbox).order_by(Outbox.id))] == ["RESV_SET"] * 2 + ["RESV_DEL"] * 2
```

`server/tests/test_reserve.py` 에 이어서(노드 용량·공개 과목·관리자 REST 경로):

```python
def test_room_capacity_and_public_subject(db, hub, app, students, monkeypatch):
    """방의 창 안 예약이 노드 용량(24)에 차면 신청·승인 409, 노드엔 학생 과목 대신 고정 문구 (자체 점검 🔴·🟡)."""
    import json

    _fix_clock(monkeypatch)
    monkeypatch.setattr(reserve, "NODE_RESV_MAX", 2)
    _, ids = _building(app, 1, "E", rooms=((301, 2),))
    rid = ids[301]
    a = _resv(app, rid, dt.date(2026, 9, 24), 9, 0, 10, 0, id_=1, status="requested", requested_by="s1@mju.ac.kr", subject="면접 준비 홍길동")
    _resv(app, rid, dt.date(2026, 9, 25), 9, 0, 10, 0, id_=2, status="approved")
    assert _check(app, rid, _body(date="2026-09-26")) == 409          # 2 개로 가득
    with app.state.Session() as s, s.begin():
        reserve.approve(s, s.get(Reservation, a), "admin@mju.ac.kr", clock.local_now())  # 자기 자신은 빼고 셈
    with db() as s:
        o = s.scalars(select(Outbox).where(Outbox.type == "RESV_SET")).first()
        assert json.loads(o.payload)["subject"] == "학생 예약"
```

`server/tests/test_reserve.py` 에 이어서(관리자 REST 경로):

```python
def test_admin_write_tracks_pushed_at(client, live, app, school, students, monkeypatch):
    """pushed_at = 노드로 보냈는가. 창 밖으로 옮기면 RESV_DEL, 안 보낸 예약 삭제엔 RESV_DEL 없음 (r2 🔴1c·⚪)."""
    monkeypatch.setattr(clock, "now_utc", lambda: dt.datetime(2026, 9, 23, 1, 30))  # KST 9/23 10:30
    from app.domain.models import Building, Room
    from app.lora_service.models import Outbox
    from sqlalchemy import select

    with app.state.Session() as s, s.begin():
        b = Building(school_id=1, name="E동", bld="E")
        s.add(b)
        s.flush()
        r = Room(building_id=b.id, room=302, units=1)  # live FakeTopo: E302 units 1
        s.add(r)
        s.flush()
        rid = r.id
    body = {"date": "2026-09-24", "s_h": 9, "s_m": 0, "e_h": 10, "e_m": 0, "type": 6, "subject": "r", "professor": ""}

    def types():
        with live() as s:
            return [o.type for o in s.scalars(select(Outbox).order_by(Outbox.id))]

    i = client.post(f"/api/rooms/{rid}/reservations", json=body).json()["id"]
    with app.state.Session() as s:
        assert s.get(Reservation, i).pushed_at is not None
    client.post(f"/api/rooms/{rid}/reservations", json={**body, "id": i, "date": "2026-10-10"})  # 창 밖으로
    assert types() == ["RESV_SET", "RESV_DEL"]
    with app.state.Session() as s:
        assert s.get(Reservation, i).pushed_at is None
    client.post(f"/api/rooms/{rid}/reservations", json={**body, "id": i, "date": "2026-10-11"})  # 창 밖 → 창 밖
    assert client.delete(f"/api/rooms/{rid}/reservations/{i}").json()["outbox_ids"] == []  # 보낸 적 없음
    assert client.delete(f"/api/rooms/{rid}/reservations/999").status_code == 200  # 멱등
    assert types() == ["RESV_SET", "RESV_DEL"]
```

`db` 픽스처(conftest)의 `FakeTopo` 에 `("E", 301)` units=2 modem "m1" 이 있으므로 `api.enqueue_*` 가 행을 만든다. `reserve.addr` 는 DB 건물의 `modem_id`(테스트 건물엔 없음 → None)를 준다 — 라우터가 notify 에 쓴다.

- [ ] **Step 2: 실패 확인** → `ModuleNotFoundError`

- [ ] **Step 3: 스키마**

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

- [ ] **Step 4: 구현**

`server/app/domain/reserve.py`:

```python
"""학생 예약 제약·전이 (S10 §2.4·§4). 라우터(학생·관리자)가 공유.
outbox 는 approve·cancel 에서만, 호출자 세션으로(enqueue_*(session=s)) — 커밋·notify 는 호출자 (S2c)."""

from __future__ import annotations

import datetime as dt

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import schemas as S
from app.auth.models import User
from app.domain import clock
from app.domain.models import Building, Reservation, Room, Slot
from app.domain.topology import RESV_HORIZON_DAYS
from app.lora_service import api

from app.domain.topology import NODE_RESV_MAX  # 24 — 노드 Resv resv[24] (v2 §5.1)

MAX_ACTIVE = 3
MIN_MIN, MAX_MIN = 15, 120
STUDENT_LABEL = "학생 예약"  # 문 앞 e-Paper 는 공개 — 학생이 적은 목적은 싣지 않는다
CHECKIN_BEFORE, CHECKIN_AFTER = 10, 15  # 분
STUDENT_TYPE = 6  # 대여


def start_local(r: Reservation) -> dt.datetime:
    return clock.local_dt(r.date, r.s_h, r.s_m)


def end_local(r: Reservation) -> dt.datetime:
    return clock.local_dt(r.date, r.e_h, r.e_m)


def in_window(date: dt.date, today: dt.date) -> bool:
    """노드에 가 있는(또는 갈) 예약인가 — 오늘~+7 (v2 §12)."""
    return today <= date <= today + dt.timedelta(days=RESV_HORIZON_DAYS)


def addr(s: Session, r: Reservation) -> tuple[str, int, str | None]:
    room = s.get(Room, r.room_id)
    b = s.get(Building, room.building_id)
    return b.bld, room.room, b.modem_id


def node_subject(r: Reservation) -> str:
    return r.subject if r.requested_by is None else STUDENT_LABEL


def room_full(s: Session, room_id: int, today: dt.date, exclude_id: int | None = None) -> bool:
    """방의 창(오늘~+7) 안 approved+requested 가 노드 용량(24)에 찼는가. 넘으면 노드가 STORE_FAIL."""
    q = select(func.count()).select_from(Reservation).where(
        Reservation.room_id == room_id,
        Reservation.status.in_(("approved", "requested")),
        Reservation.date >= today,
        Reservation.date <= today + dt.timedelta(days=RESV_HORIZON_DAYS),
    )
    if exclude_id is not None:
        q = q.where(Reservation.id != exclude_id)
    return s.scalar(q) >= NODE_RESV_MAX


def push_set(s: Session, r: Reservation) -> list[int]:
    """RESV_SET 을 호출자 세션으로 enqueue 하고 pushed_at 을 찍는다 — pushed_at 을 바꾸는 두 곳 중 하나."""
    bld, room, _ = addr(s, r)
    ids = api.enqueue_resv_set(
        bld, room, r.id, r.date, (r.s_h, r.s_m), (r.e_h, r.e_m), r.type, node_subject(r), r.professor, session=s
    )
    r.pushed_at = clock.now_utc()
    return ids


def push_del(s: Session, r: Reservation, today: dt.date, date: dt.date | None = None) -> list[int]:
    """노드에 가 있을 수 있는(보낸 적 있고 아직 안 지난) 예약만 RESV_DEL. 어느 쪽이든 pushed_at 을 비운다.
    `date` 는 날짜를 옮길 때 옮기기 전 날짜 — 노드가 가진 건 옛 날짜 항목이다."""
    d = date or r.date
    ended = clock.local_dt(d, r.e_h, r.e_m) <= clock.local_now()  # 끝난 예약은 노드가 곧 버린다 — 웨이크 낭비
    if r.pushed_at is None or d < today or ended:
        r.pushed_at = None
        return []
    bld, room, _ = addr(s, r)
    r.pushed_at = None
    return api.enqueue_resv_del(bld, room, r.id, session=s)


def overlaps(s: Session, room_id: int, date: dt.date, s_min: int, e_min: int, exclude_id: int | None = None) -> bool:
    """정규 슬롯(그 요일, type 무관)·approved/requested 예약과 1분이라도 겹치면 True.
    시험기간은 슬롯이 있을 때만 의미가 있어 슬롯 겹침에 이미 포함된다."""
    day = date.isoweekday()
    for x in s.scalars(select(Slot).where(Slot.room_id == room_id, Slot.day == day)):
        if x.s_h * 60 + x.s_m < e_min and s_min < x.e_h * 60 + x.e_m:
            return True
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
    if not in_window(body.date, today):
        raise HTTPException(400, f"오늘부터 {RESV_HORIZON_DAYS}일 안에만 신청할 수 있습니다")
    s_min, e_min = body.s_h * 60 + body.s_m, body.e_h * 60 + body.e_m
    if not (MIN_MIN <= e_min - s_min <= MAX_MIN):
        raise HTTPException(400, f"{MIN_MIN}분 이상 {MAX_MIN}분 이하로 신청하세요")
    if clock.local_dt(body.date, body.s_h, body.s_m) <= now_local:
        raise HTTPException(400, "이미 지난 시간입니다")
    # 진행 중 = 아직 시작 안 한 신청 + 아직 안 끝난 승인 (spec "미래 approved"). 날짜만 보면 오늘 끝난 예약이
    # 자정까지, 시작 지난 신청이 04:00 만료까지 한도를 잡는다 (자체 점검 🟡)
    mine = s.scalars(select(Reservation).where(
        Reservation.requested_by == user.email,
        Reservation.status.in_(("requested", "approved")),
        Reservation.date >= today,
    ))
    active = sum(
        1 for x in mine
        if (start_local(x) if x.status == "requested" else end_local(x)) > now_local
    )
    if active >= MAX_ACTIVE:
        raise HTTPException(400, f"진행 중인 신청은 {MAX_ACTIVE}건까지입니다")
    if overlaps(s, room.id, body.date, s_min, e_min):
        raise HTTPException(409, "그 시간에는 이미 수업·예약이 있습니다")
    if room_full(s, room.id, today):
        raise HTTPException(409, "이 강의실은 이번 주 예약이 가득 찼습니다")


def _require(r: Reservation, *states: str) -> None:
    if r.status not in states:
        raise HTTPException(409, f"{r.status} 상태에서는 불가")


def approve(s: Session, r: Reservation, admin_email: str, now_local: dt.datetime) -> list[int]:
    _require(r, "requested")
    if start_local(r) <= now_local:
        raise HTTPException(409, "이미 시작 시각이 지난 신청입니다")
    if overlaps(s, r.room_id, r.date, r.s_h * 60 + r.s_m, r.e_h * 60 + r.e_m, exclude_id=r.id):
        raise HTTPException(409, "그 시간에 다른 예약·수업이 생겼습니다")
    if room_full(s, r.room_id, now_local.date(), exclude_id=r.id):
        raise HTTPException(409, "이 강의실은 이번 주 예약이 가득 찼습니다(노드 용량 24)")
    r.status, r.decided_at, r.decided_by = "approved", clock.to_utc(now_local), admin_email
    if not in_window(r.date, now_local.date()):
        return []  # 창 밖 — pushed_at NULL 로 남아 창에 들어오는 날 일일 작업이 승격 (S10 §2.5)
    return push_set(s, r)


def reject(s: Session, r: Reservation, admin_email: str, reason: str, now_local: dt.datetime) -> None:
    _require(r, "requested")
    r.status, r.decided_at, r.decided_by, r.reject_reason = "rejected", clock.to_utc(now_local), admin_email, reason


def withdraw(s: Session, r: Reservation) -> None:
    """학생이 결정 전 신청을 거둔다 — 행을 지워 u16 id 를 바로 돌려준다 (신청·철회 반복으로 id 소진 방지)."""
    _require(r, "requested")
    s.delete(r)


def cancel(s: Session, r: Reservation, *, by_admin: bool, now_local: dt.datetime) -> list[int]:
    """approved → cancelled. 학생은 시작 전만. 노드로 보낸 적 있는 예약만 RESV_DEL(push_del)."""
    _require(r, "approved")
    if not by_admin and start_local(r) <= now_local:
        raise HTTPException(409, "시작된 예약은 취소할 수 없습니다")
    r.status, r.cancelled_at = "cancelled", clock.to_utc(now_local)
    return push_del(s, r, now_local.date())


def checkin(s: Session, r: Reservation, now_local: dt.datetime) -> None:
    _require(r, "approved")
    if r.checked_in_at is not None:
        raise HTTPException(409, "이미 체크인했습니다")
    st = start_local(r)
    if not (st - dt.timedelta(minutes=CHECKIN_BEFORE) <= now_local <= st + dt.timedelta(minutes=CHECKIN_AFTER)):
        raise HTTPException(409, f"체크인은 시작 {CHECKIN_BEFORE}분 전부터 {CHECKIN_AFTER}분 후까지입니다")
    r.checked_in_at = clock.to_utc(now_local)
```

- [ ] **Step 4b: 관리자 REST 가 `pushed_at` 을 쓰게**

`server/app/domain/router.py` 의 `_write_resv`(S4b·T1)·`delete_resv`(S2c) 를 다음으로 교체 — 전송 여부는 `pushed_at`(위 `push_set/push_del`):

```python
def _write_resv(s, room_id, bld, room, mid, body: S.ResvIn, rid: int, obj: Reservation | None) -> dict:
    obj = obj or Reservation(id=rid, room_id=room_id)
    old_date = obj.date  # 새 행이면 None
    for k, v in body.model_dump(exclude={"id"}).items():
        setattr(obj, k, v)
    s.add(obj)
    today = clock.local_today()
    if reserve.in_window(body.date, today):
        if reserve.room_full(s, room_id, today, exclude_id=rid):
            raise HTTPException(409, "이 강의실은 이번 주 예약이 가득 찼습니다(노드 용량 24)")
        ids = reserve.push_set(s, obj)
    else:  # 창 밖으로 옮겼으면 노드의 옛 날짜 항목을 지운다 (r3, 리뷰 🔴1c — main 에도 있던 문제)
        ids = reserve.push_del(s, obj, today, date=old_date)
    _commit_notify(s, mid)
    return {"outbox_ids": ids, "id": rid}


@router.delete("/rooms/{id}/reservations/{resv_id}", response_model=S.Enqueued)
def delete_resv(id: int, resv_id: int, user: User = AdminUser, s: Session = _DB):
    bld, room, mid = _addr(s, id, user)
    r = s.get(Reservation, resv_id)
    if r is None or r.room_id != id:  # 멱등 — 없는 id 에 RESV_DEL 을 보내지 않는다
        return {"outbox_ids": []}
    with _ID_LOCK:  # 예약 쓰기는 전부 같은 락 — 동시 승인·승격과 엇갈리지 않게
        s.refresh(r)
        ids = reserve.push_del(s, r, clock.local_today())  # 노드로 보낸 적 있는 것만 (r2 ⚪: 신청·창 밖 예약엔 DEL 없음)
        s.delete(r)
        _commit_notify(s, mid)
    return {"outbox_ids": ids}
```

(import `from app.domain import clock, reserve`. `reserve` 는 `router` 를 import 하지 않으므로 순환 없음.)

- [ ] **Step 5: 통과·커밋**

```bash
git add app/domain/reserve.py app/domain/router.py app/schemas.py tests/test_reserve.py
git commit -m "feat(server): reserve — 학생 신청 제약·겹침, 승인/거절/취소/철회/체크인 전이 (enqueue 는 호출자 세션)"
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
def test_free_rooms_now_and_at(client, client_raw, app, school, student_hdr, monkeypatch):
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
    r = client.get("/api/student/rooms/free?at=2026-09-23T02:00:00Z", headers=student_hdr)  # = KST 11:00
    assert [x["room"] for x in r.json()] == [101, 102, 103]
    assert client_raw.get("/api/student/rooms/free").status_code == 401  # client 는 관리자 Bearer 가 붙어 403 이 된다
    assert client.get("/api/student/rooms/free").status_code == 403  # 관리자


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
    if at is not None and at.tzinfo is not None:  # 브라우저 toISOString() = "...Z" — 그대로 쓰면 9 시간 어긋난다
        at = at.astimezone(clock.SCHOOL_TZ).replace(tzinfo=None)
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


def test_request_list_withdraw(client, app, school, student_hdr, other_student_hdr, monkeypatch):
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
    assert r.status_code == 200 and r.json()["status"] == "cancelled"                             # 신청 철회
    assert client.get("/api/student/me/reservations?status=requested,cancelled", headers=student_hdr).json() == []  # 행 삭제
    assert client.post("/api/student/me/reservations/1/cancel", headers=student_hdr).status_code == 404
    assert client.post(f"/api/student/rooms/{rid}/reservations", json=BODY, headers=student_hdr).json()["id"] == 1  # id 재사용


def test_daily_request_cap(client, app, school, student_hdr, monkeypatch):
    from app.domain import student_router

    _fix_clock(monkeypatch)
    monkeypatch.setattr(student_router, "DAILY_REQUESTS", 1)
    _, ids = _building(app, 1, "E")
    assert client.post(f"/api/student/rooms/{ids[101]}/reservations", json=BODY, headers=student_hdr).status_code == 201
    r = client.post(f"/api/student/rooms/{ids[101]}/reservations", json={**BODY, "s_h": 15, "e_h": 16}, headers=student_hdr)
    assert r.status_code == 429  # 신청·철회 반복으로 id 를 소진하지 못하게 (리뷰 🟡)


def test_concurrent_requests_cannot_both_pass(client, app, school, student_hdr, other_student_hdr, monkeypatch):
    """검증이 락 밖이면 동시 두 신청이 둘 다 requested → 승인 재검사에서 서로 막혀 둘 다 409 (r2 🟡).
    검증~커밋이 _ID_LOCK 안이므로 둘째는 첫째의 커밋을 보고 409. (sync 핸들러는 스레드풀에서 동시에 돈다.)"""
    import threading

    _fix_clock(monkeypatch)
    _, ids = _building(app, 1, "E")
    hdrs = [student_hdr, other_student_hdr]
    gate, codes = threading.Barrier(2), []

    def go(h):
        gate.wait()
        codes.append(client.post(f"/api/student/rooms/{ids[101]}/reservations", json=BODY, headers=h).status_code)

    ts = [threading.Thread(target=go, args=(h,)) for h in hdrs]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert sorted(codes) == [201, 409]


def test_cancel_approved_sends_resv_del_and_checkin_window(client, live, app, school, student_hdr, monkeypatch):
    seen = []
    monkeypatch.setattr(api, "notify", lambda mid: seen.append(mid))  # 커밋 뒤 호출되는지 (S2c)
    _fix_clock(monkeypatch)
    _, ids = _building(app, 1, "E", rooms=((301, 2),))
    rid = ids[301]
    a = _resv(app, rid, dt.date(2026, 9, 24), 13, 0, 14, 0, id_=1, status="approved", requested_by="s1@mju.ac.kr", pushed_at=UTC_NOW)  # 노드에 가 있음
    b = _resv(app, rid, dt.date(2026, 9, 23), 10, 25, 11, 0, id_=2, status="approved", requested_by="s1@mju.ac.kr")  # 시작 5분 전
    r = client.post(f"/api/student/me/reservations/{b}/checkin", headers=student_hdr)
    assert r.status_code == 200 and r.json()["checked_in_at"]
    assert client.post(f"/api/student/me/reservations/{a}/checkin", headers=student_hdr).status_code == 409  # 내일
    assert client.post(f"/api/student/me/reservations/{b}/cancel", headers=student_hdr).status_code == 409  # 10:25 시작, 지금 10:30 → 이미 시작
    r = client.post(f"/api/student/me/reservations/{a}/cancel", headers=student_hdr)
    assert r.status_code == 200
    with live() as s:
        assert [o.type for o in s.scalars(select(Outbox))] == ["RESV_DEL", "RESV_DEL"]  # 유닛 2
    assert seen == [None]  # 테스트 건물엔 modem 없음 — 호출 자체는 됐다
```

(상단 import 에 `from app.lora_service import api`.)

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

`student_router.py` 에 (import `from app.auth import ratelimit`, `from app.domain import reserve`, `from app.domain.router import _ID_LOCK, _commit_notify, _free_id`). 레이트리밋은 S4a r3 의 **키별 창 정리**에 기대어 하루 창이 유지된다(r2 🟡 — 1분 뒤 풀리던 것):

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


DAILY_REQUESTS = 10  # 학생당 하루 신청 상한 — 신청·철회 반복으로 u16 id 를 소진하지 못하게


@router.post("/rooms/{id}/reservations", response_model=S.ResvMineOut, status_code=201)
def request_resv(id: int, body: S.StudentResvIn, user: User = StudentUser, s: Session = _DB):
    room, _ = _student_room(s, user, id)
    now = clock.local_now()
    # 검증~채번~커밋을 한 덩어리로 — 동시 두 신청이 둘 다 겹침·MAX_ACTIVE 검사를 통과하지 않게 (r2 🟡).
    # pysqlite 는 DML 전까지 트랜잭션을 열지 않아, 락 안의 SELECT 는 앞 요청의 커밋을 본다.
    with _ID_LOCK:
        reserve.validate_request(s, user, room, body, now)
        if not ratelimit.check(f"resv:{user.email}", limit=DAILY_REQUESTS, window_s=86400.0):
            raise HTTPException(429, f"신청은 하루 {DAILY_REQUESTS}회까지입니다")
        r = Reservation(
            id=_free_id(s, Reservation), room_id=id, date=body.date, s_h=body.s_h, s_m=body.s_m, e_h=body.e_h,
            e_m=body.e_m, type=reserve.STUDENT_TYPE, subject=body.subject, professor="", status="requested",
            requested_by=user.email, requested_at=clock.to_utc(now),
        )
        s.add(r)
        s.flush()
        out = _mine_out(s, r)
        s.commit()
    return out


@router.get("/me/reservations", response_model=list[S.ResvMineOut])
def my_reservations(status: str | None = None, user: User = StudentUser, s: Session = _DB):
    states = status.split(",") if status else ["requested", "approved"]
    q = (select(Reservation).where(Reservation.requested_by == user.email, Reservation.status.in_(states))
         .order_by(Reservation.date, Reservation.s_h, Reservation.s_m))
    return [_mine_out(s, r) for r in s.scalars(q)]


@router.post("/me/reservations/{id}/cancel", response_model=S.ResvMineOut)
def cancel_resv(id: int, user: User = StudentUser, s: Session = _DB):
    """requested → 철회(행 삭제), approved → 시작 전 취소(보낸 적 있으면 RESV_DEL). 커밋 뒤 허브 알림."""
    with _ID_LOCK:  # 읽기~커밋 — 동시에 관리자가 승인하면 철회가 RESV_SET 뒤에 행을 지워 유령 예약이 남는다
        r = _my_resv(s, user, id)
        if r.status == "requested":
            out = _mine_out(s, r) | {"status": "cancelled"}
            reserve.withdraw(s, r)
            s.commit()
            return out
        mid = reserve.addr(s, r)[2]
        reserve.cancel(s, r, by_admin=False, now_local=clock.local_now())
        out = _mine_out(s, r)
        _commit_notify(s, mid)
    return out


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
def test_list_scope_and_filters(client, app, school, students, other_admin_hdr, monkeypatch):
    _fix_clock(monkeypatch)
    bid, ids = _building(app, 1, "E")
    _, ids2 = _building(app, 2, "F")
    _resv(app, ids[101], dt.date(2026, 9, 24), 13, 0, 14, 0, id_=1, status="requested", requested_by="s1@mju.ac.kr", requested_at=UTC_NOW)
    _resv(app, ids[101], dt.date(2026, 9, 25), 13, 0, 14, 0, id_=2, status="approved")
    _resv(app, ids2[101], dt.date(2026, 9, 24), 13, 0, 14, 0, id_=3, status="requested", requested_by="s3@other.ac.kr")
    r = client.get("/api/admin/reservations")
    assert r.status_code == 200 and [x["id"] for x in r.json()] == [1]
    assert r.json()[0]["requester"] == {"email": "s1@mju.ac.kr", "name": "학생1", "student_no": "S1"}  # students 픽스처 학번
    assert [x["id"] for x in client.get("/api/admin/reservations?status=approved").json()] == [2]
    assert client.get("/api/admin/reservations?status=approved").json()[0]["requester"] is None
    assert [x["id"] for x in client.get(f"/api/admin/reservations?status=requested,approved&building_id={bid}").json()] == [1, 2]
    assert client.get("/api/admin/reservations?status=approved&date_from=2026-09-25&date_to=2026-09-25").json()[0]["id"] == 2
    assert [x["id"] for x in client.get("/api/admin/reservations", headers=other_admin_hdr).json()] == [3]
    assert client.get("/api/admin/reservations", headers=client.headers | {"Authorization": other_admin_hdr["Authorization"]}).status_code == 200


def test_approve_reject_cancel_and_summary_bucket(client, live, app, school, students, monkeypatch):
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
        .order_by(Reservation.requested_at, Reservation.id)  # 같은 시각이면 id — SQLite 동순위 순서는 정의되지 않음
    )
    now = clock.local_now()
    # 시작 지난 신청은 승인할 수 없다(409) — 04:00 만료 전까지 경고에 남기지 않는다
    return [resv_admin_out(s, r) for r in s.scalars(q) if reserve.start_local(r) > now]
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
from app.domain.router import _ID_LOCK, _commit_notify
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
        .order_by(Reservation.date, Reservation.s_h, Reservation.s_m, Reservation.id)  # requested_at 은 관리자 예약엔 NULL
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
    with _ID_LOCK:  # 겹침 재검사~커밋 — 동시에 들어온 학생 신청과 경합하지 않게 (학생 신청도 같은 락)
        r = _scoped_resv(s, user, id)
        reserve.approve(s, r, user.email, clock.local_now())
        out = admin.resv_admin_out(s, r)
        _commit_notify(s, reserve.addr(s, r)[2])  # 같은 세션의 RESV_SET 을 커밋한 뒤 허브 알림 (S2c)
    return out


@router.post("/reservations/{id}/reject", response_model=S.ResvAdminOut)
def reject(id: int, body: S.RejectIn, user: User = AdminUser, s: Session = _DB):
    with _ID_LOCK:
        r = _scoped_resv(s, user, id)
        reserve.reject(s, r, user.email, body.reason, clock.local_now())
        out = admin.resv_admin_out(s, r)
        s.commit()  # 락 안에서 — 응답 뒤 커밋이면 그 사이 승인과 엇갈린다
    return out


@router.post("/reservations/{id}/cancel", response_model=S.ResvAdminOut)
def cancel(id: int, user: User = AdminUser, s: Session = _DB):
    with _ID_LOCK:
        r = _scoped_resv(s, user, id)
        reserve.cancel(s, r, by_admin=True, now_local=clock.local_now())
        out = admin.resv_admin_out(s, r)
        _commit_notify(s, reserve.addr(s, r)[2])
    return out
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
def _outbox(app, bld, room, type_, state, finished_at, payload="{}", unit=1, last_error=None):
    with app.state.Session() as s, s.begin():
        o = Outbox(bld=bld, room=room, unit=unit, type=type_, payload=payload, state=state, created_at=UTC_NOW,
                   finished_at=finished_at, modem_id="m1", last_error=last_error)
        s.add(o)
        s.flush()
        return o.id


def test_run_daily_five_steps(db, hub, app, school, students, monkeypatch):
    _fix_clock(monkeypatch)  # KST 9/23 10:30 → 오늘+7 = 9/30
    _, ids = _building(app, 1, "E", rooms=((301, 2), (302, 1)))
    r301, r302 = ids[301], ids[302]
    # 1 만료: 신청인데 시작 지남
    _resv(app, r301, dt.date(2026, 9, 23), 9, 0, 10, 0, id_=1, status="requested", requested_by="s1@mju.ac.kr")
    # 2 승격: 창 안(오늘~+7) 승인 예약 중 아직 안 보낸 것(pushed_at NULL) 전부 (r3)
    _resv(app, r301, dt.date(2026, 9, 30), 13, 0, 14, 0, id_=2, status="approved")   # +7, 안 보냄 → 승격
    _outbox(app, "E", 301, "RESV_SET", "acked", UTC_NOW, payload=json.dumps({"resv_id": 2}))  # 지운 옛 예약 2 의 이력 — id 재사용에 속지 않는다
    _resv(app, r302, dt.date(2026, 9, 26), 15, 0, 16, 0, id_=8, status="approved")   # +3, 안 보냄(서버가 꺼져 그날을 놓침) → 따라잡음
    _resv(app, r301, dt.date(2026, 9, 24), 13, 0, 14, 0, id_=3, status="approved", pushed_at=UTC_NOW)  # 이미 보냄 → 안 보냄(배터리)
    _resv(app, r302, dt.date(2026, 9, 30), 15, 0, 16, 0, id_=6, status="approved", pushed_at=UTC_NOW)  # 이미 보냄
    _resv(app, r301, dt.date(2026, 10, 5), 13, 0, 14, 0, id_=4, status="approved")   # 창 밖 → 없음
    # 3 재동기: 24 h 안 실패 — SLOT_SET(302/1) + FILE resv(301/2) / CMD·25 h 전·관리자 취소분은 무시
    _outbox(app, "E", 302, "SLOT_SET", "failed", UTC_NOW - dt.timedelta(hours=1))
    _outbox(app, "E", 301, "FILE", "failed", UTC_NOW - dt.timedelta(hours=2), payload=json.dumps({"kind": 2, "records": []}), unit=2)
    _outbox(app, "E", 302, "CMD", "failed", UTC_NOW - dt.timedelta(hours=1))
    _outbox(app, "E", 301, "EXAM_SET", "failed", UTC_NOW - dt.timedelta(hours=25))
    _outbox(app, "E", 301, "SLOT_SET", "failed", UTC_NOW - dt.timedelta(hours=1), last_error="cancelled")
    # 4 정리: 91 일 전 예약, 8 일 전 거절 신청, 91 일 전 job_run, 8 일 지난 토큰
    _resv(app, r302, dt.date(2026, 6, 20), 9, 0, 10, 0, id_=5, status="approved")
    _resv(app, r302, dt.date(2026, 9, 15), 9, 0, 10, 0, id_=7, status="rejected", requested_by="s2@mju.ac.kr")
    with app.state.Session() as s, s.begin():
        s.add(JobRun(name="daily", ran_at=UTC_NOW - dt.timedelta(days=91), result="{}"))
        s.add(EmailToken(token_hash="x", email="s1@mju.ac.kr", purpose="verify", created_at=UTC_NOW - dt.timedelta(days=8),
                         expires_at=UTC_NOW - dt.timedelta(days=8)))  # created_at 은 S4a r3 에서 NOT NULL
        s.add(EmailToken(token_hash="y", email="s1@mju.ac.kr", purpose="verify", created_at=UTC_NOW - dt.timedelta(days=6),
                         expires_at=UTC_NOW - dt.timedelta(days=6)))
    res = daily.run_daily(app.state.Session)
    assert res["errors"] == []
    assert res["expired"] == 1 and res["promoted"] == 2
    assert res["resynced"] == [["E", 301, 2, ["resv"]], ["E", 302, 1, ["schedule"]]]  # 유닛별, FILE 은 payload.kind 로
    assert res["pruned"] == {"reservations": 2, "job_runs": 1, "email_tokens": 1}
    with app.state.Session() as s:
        assert s.get(Reservation, 1).status == "expired" and s.get(Reservation, 5) is None and s.get(Reservation, 7) is None
        rows = s.scalars(select(Outbox).where(Outbox.state == "queued").order_by(Outbox.id)).all()
        assert sorted((o.room, o.unit, o.type) for o in rows) == [
            (301, 1, "RESV_SET"), (301, 2, "FILE"), (301, 2, "RESV_SET"), (302, 1, "FILE"), (302, 1, "RESV_SET")]
        assert s.get(Reservation, 2).pushed_at is not None and s.get(Reservation, 4).pushed_at is None
        assert s.scalar(select(EmailToken.token_hash).where(EmailToken.token_hash == "y")) == "y"
        runs = s.scalars(select(JobRun).order_by(JobRun.id)).all()
        assert len(runs) == 1 and json.loads(runs[0].result)["promoted"] == 2
    assert daily.run_daily(app.state.Session)["promoted"] == 0  # 다음 날 다시 돌아도 이미 보낸 건 안 보낸다


def test_promote_one_failure_does_not_stop_others(db, hub, app, school, monkeypatch):
    """예약마다 자기 트랜잭션 — 한 건(삭제된 방 등)이 실패해도 나머지는 보내고, 실패분은 다음 날 다시 시도 (r3)."""
    _fix_clock(monkeypatch)
    _, ids = _building(app, 1, "E", rooms=((301, 2), (302, 1)))
    _resv(app, ids[301], dt.date(2026, 9, 25), 13, 0, 14, 0, id_=1, status="approved")
    _resv(app, ids[302], dt.date(2026, 9, 25), 13, 0, 14, 0, id_=2, status="approved")
    real = daily.api.enqueue_resv_set

    def flaky(bld, room, *a, **kw):
        if room == 301:
            raise LookupError("room gone")
        return real(bld, room, *a, **kw)

    monkeypatch.setattr(daily.api, "enqueue_resv_set", flaky)
    res = daily.run_daily(app.state.Session)
    assert res["promoted"] == 1 and any("resv 1" in e for e in res["errors"])
    with app.state.Session() as s:
        assert s.get(Reservation, 1).pushed_at is None and s.get(Reservation, 2).pushed_at is not None


def test_resync_one_room_failure_does_not_stop_others(db, hub, app, school, monkeypatch):
    _fix_clock(monkeypatch)
    _building(app, 1, "E", rooms=((301, 2), (302, 1)))
    _outbox(app, "E", 301, "SLOT_SET", "failed", UTC_NOW - dt.timedelta(hours=1))
    _outbox(app, "E", 302, "SLOT_SET", "failed", UTC_NOW - dt.timedelta(hours=1))
    real = daily.api.enqueue_full_sync

    def flaky(bld, room, kinds, unit=0):
        if room == 301:
            raise LookupError("room gone")
        return real(bld, room, kinds, unit=unit)

    monkeypatch.setattr(daily.api, "enqueue_full_sync", flaky)
    res = daily.run_daily(app.state.Session)
    assert res["resynced"] == [["E", 302, 1, ["schedule"]]] and any("E301" in e for e in res["errors"])


def test_step_failure_continues(db, hub, app, school, monkeypatch):
    _fix_clock(monkeypatch)
    monkeypatch.setattr(daily, "_promote", lambda Session, now_local, errors: (_ for _ in ()).throw(RuntimeError("boom")))
    res = daily.run_daily(app.state.Session)
    assert res["promoted"] == 0 and res["errors"] == ["promoted: boom"] and "pruned" in res


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
    # 04:00 이전 수동 실행은 그날 자동 실행을 막지 않는다 (리뷰 ⚪)
    _fix_clock(monkeypatch, dt.datetime(2026, 9, 23, 17, 0))   # KST 9/24 02:00
    daily.run_daily(app.state.Session)
    _fix_clock(monkeypatch, dt.datetime(2026, 9, 23, 19, 0))   # KST 9/24 04:00
    assert daily.tick(app.state.Session) is True


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
import threading

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.auth.models import EmailToken
from app.domain import clock, reserve
from app.domain.models import Building, JobRun, Reservation, Room
from app.domain.router import _ID_LOCK
from app.domain.topology import RESV_HORIZON_DAYS
from app.lora_service import api
from app.lora_service.api import KIND_OF
from app.lora_service.models import Outbox

log = logging.getLogger(__name__)
KEEP_DAYS = 90
TOKEN_KEEP_DAYS = 7
RESYNC_WINDOW_H = 24
_RUN_LOCK = threading.Lock()  # 자동(daily_loop)·수동(POST /jobs/daily) 실행이 겹치지 않게 — 단일 워커 전제


FILE_KINDS = {1: "schedule", 2: "resv", 3: "exam"}  # FILE payload.kind → room_versions.kind


def _rooms_by_id(s: Session) -> dict[int, tuple[str, int, str | None]]:
    return {rid: (bld, room, mid) for rid, bld, room, mid in s.execute(
        select(Room.id, Building.bld, Room.room, Building.modem_id).join(Building, Building.id == Room.building_id))}


def _kind_of(o: Outbox) -> str | None:
    if o.type == "FILE":  # KIND_OF 엔 FILE 이 없다 — payload.kind 로 (리뷰 🔴8)
        try:
            return FILE_KINDS.get(json.loads(o.payload).get("kind"))
        except ValueError:
            return None
    return KIND_OF.get(o.type)


def _expire(s: Session, now_local: dt.datetime) -> int:
    n = 0
    for r in s.scalars(select(Reservation).where(Reservation.status == "requested")):
        if clock.local_dt(r.date, r.s_h, r.s_m) < now_local:
            r.status = "expired"
            n += 1
    return n


def _pushed_in_window(s: Session, room_id: int, today: dt.date) -> int:
    return s.scalar(select(func.count()).select_from(Reservation).where(
        Reservation.room_id == room_id, Reservation.pushed_at.is_not(None),
        Reservation.date >= today, Reservation.date <= today + dt.timedelta(days=RESV_HORIZON_DAYS),
    ))


def _promote(Session: sessionmaker, now_local: dt.datetime, errors: list[str]) -> int:
    """창 안(오늘~오늘+7)인데 아직 노드로 안 보낸(pushed_at IS NULL) 승인 예약을 RESV_SET (r3).
    - 서버가 꺼져 하루를 놓쳐도 다음 실행이 따라잡는다(r2 의 "날짜 == 오늘+7 만" 은 그날을 놓치면 영영 안 갔다).
    - outbox 이력이 아니라 예약 행의 pushed_at 으로 판단 — 지운 예약의 id 를 새 예약이 재사용해도 오판 없음.
    - 이미 보낸 예약은 다시 보내지 않는다(예약 k × 유닛 u 번 웨이크 방지, v2 §1.4).
    예약마다 자기 트랜잭션: 한 건이 실패해도(방 삭제 등) 나머지는 보내고, 실패분은 pushed_at NULL 로 남아 다음 날 재시도.
    pysqlite 는 기본 설정에서 SAVEPOINT 가 동작하지 않아 세션 하나에서 부분 롤백을 할 수 없다."""
    today = now_local.date()
    with Session() as s:
        ids = s.scalars(
            select(Reservation.id).where(
                Reservation.status == "approved",
                Reservation.pushed_at.is_(None),
                Reservation.date >= today,
                Reservation.date <= today + dt.timedelta(days=RESV_HORIZON_DAYS),
            ).order_by(Reservation.date, Reservation.id)
        ).all()
    n = 0
    for rid in ids:
        try:
            with Session() as s, s.begin():
                with _ID_LOCK:  # 관리자가 그 사이 날짜를 옮기면 옛 날짜로 보내지 않게 — 락 안에서 다시 읽는다
                    r = s.get(Reservation, rid)
                    if r is None or r.status != "approved" or r.pushed_at is not None:
                        continue  # 그 사이 취소·삭제·전송됨
                    if reserve.end_local(r) <= now_local:
                        continue  # 오늘 이미 끝남 — 보내 봐야 웨이크 낭비, 내일 창 밖
                    if _pushed_in_window(s, r.room_id, today) >= reserve.NODE_RESV_MAX:
                        errors.append(f"promoted: resv {rid}: 방 예약이 노드 용량({reserve.NODE_RESV_MAX})에 참")
                        continue
                    mid = reserve.addr(s, r)[2]
                    reserve.push_set(s, r)
                    s.commit()
            api.notify(mid)  # 커밋 뒤 (S2c)
            n += 1
        except Exception as e:
            log.exception("승격 실패 resv %s", rid)
            errors.append(f"promoted: resv {rid}: {e}")
    return n


def _resync_failed(s: Session, now_utc: dt.datetime, errors: list[str]) -> list[list]:
    """지난 24 h 실패한 (bld, room, unit) 마다 실패한 kind 들로 FILE 재동기 1회. 관리자 취소분·CMD·SET_ROOM·TIME 제외.
    방 하나가 실패해도(삭제된 방 → NotFound 등) 나머지는 계속한다 (리뷰 🔴8)."""
    since = now_utc - dt.timedelta(hours=RESYNC_WINDOW_H)
    kinds: dict[tuple[str, int, int], set[str]] = {}
    for o in s.scalars(select(Outbox).where(Outbox.state == "failed", Outbox.finished_at >= since)):
        if o.last_error == "cancelled":
            continue
        kind = _kind_of(o)
        if kind in ("schedule", "resv", "exam"):
            kinds.setdefault((o.bld, o.room, o.unit), set()).add(kind)
    out = []
    for (bld, room, unit), ks in sorted(kinds.items()):
        try:
            api.enqueue_full_sync(bld, room, tuple(sorted(ks)), unit=unit)  # 자기 세션 — RecordProvider 가 커밋된 DB 를 읽는다
            out.append([bld, room, unit, sorted(ks)])
        except Exception as e:
            log.exception("재동기 실패 %s%s/%s", bld, room, unit)
            errors.append(f"resynced: {bld}{room}/{unit}: {e}")
    return out


DECIDED_KEEP_DAYS = 7  # 거절·만료 신청은 1주 뒤 지운다 — u16 id 를 오래 잡지 않게


def _prune(s: Session, now_utc: dt.datetime, now_local: dt.datetime) -> dict:
    today = now_local.date()
    old = Reservation.date < today - dt.timedelta(days=KEEP_DAYS)
    decided = Reservation.status.in_(("rejected", "expired")) & (Reservation.date < today - dt.timedelta(days=DECIDED_KEEP_DAYS))
    return {
        "reservations": s.execute(delete(Reservation).where(old | decided)).rowcount,
        "job_runs": s.execute(delete(JobRun).where(JobRun.ran_at < now_utc - dt.timedelta(days=KEEP_DAYS))).rowcount,
        "email_tokens": s.execute(delete(EmailToken).where(EmailToken.expires_at < now_utc - dt.timedelta(days=TOKEN_KEEP_DAYS))).rowcount,
    }


def run_daily(Session: sessionmaker, now_utc: dt.datetime | None = None) -> dict:
    with _RUN_LOCK:
        return _run_daily(Session, now_utc)


def _run_daily(Session: sessionmaker, now_utc: dt.datetime | None) -> dict:
    now_utc = now_utc or clock.now_utc()
    now_local = clock.to_local(now_utc)
    res: dict = {"expired": 0, "promoted": 0, "resynced": [], "pruned": {}, "errors": []}

    def step(name, fn):
        mids: set = set()
        try:
            with Session() as s, s.begin():
                res[name] = fn(s, mids)
        except Exception as e:  # 한 단계 실패가 나머지를 막지 않는다
            log.exception("daily %s 실패", name)
            res["errors"].append(f"{name}: {e}")
            return
        for mid in mids:  # 커밋 뒤 허브 알림 (S2c)
            api.notify(mid)

    step("expired", lambda s, mids: _expire(s, now_local))
    step("promoted", lambda s, mids: _promote(Session, now_local, res["errors"]))  # 예약마다 자기 세션
    step("resynced", lambda s, mids: _resync_failed(s, now_utc, res["errors"]))
    step("pruned", lambda s, mids: _prune(s, now_utc, now_local))
    with Session() as s, s.begin():
        s.add(JobRun(name="daily", ran_at=now_utc, result=json.dumps(res, ensure_ascii=False)))
    return res


def already_ran_today(s: Session, now_local: dt.datetime) -> bool:
    """오늘 04:00(KST) 이후 실행 기록이 있는가 — 그 전의 수동 실행은 세지 않는다(리뷰 ⚪)."""
    start_utc = clock.to_utc(dt.datetime.combine(now_local.date(), dt.time(clock.DAILY_HOUR_LOCAL)))
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
        # sleep 먼저 — 기동 직후(테스트 포함) clock 이 monkeypatch 되기 전 실제 시각으로 돌지 않게. 04:00~04:01 사이 실행
        await asyncio.sleep(interval_s)
        try:
            await asyncio.to_thread(tick, Session)
        except Exception:
            log.exception("daily tick 실패")
```

`server/app/main.py` lifespan: `daily_task = asyncio.ensure_future(daily.daily_loop(Session))` (sweeper 옆), finally 에서 cancel.

`admin_resv_router.py` 에:

```python
@router.post("/jobs/daily", response_model=S.JobRunOut)
def run_daily_now(request: Request):
    """전 학교 대상 전역 작업(학교 스코프 없음) — 결과는 멱등(보낸 예약은 다시 안 보냄)이라 어느 관리자가 눌러도 안전.
    `_DB` 를 쓰지 않는다: run_daily 가 자기 세션들로 쓰고, 조회는 끝난 뒤 새 세션으로."""
    from app.domain import daily

    Session = request.app.state.Session
    daily.run_daily(Session)
    with Session() as s:
        return S.JobRunOut.model_validate(
            s.scalar(select(JobRun).where(JobRun.name == "daily").order_by(JobRun.id.desc()).limit(1))
        )


@router.get("/jobs", response_model=list[S.JobRunOut])
def jobs(name: str = "daily", limit: int = Query(30, ge=1, le=200), s: Session = _DB):
    return s.scalars(select(JobRun).where(JobRun.name == name).order_by(JobRun.id.desc()).limit(limit)).all()
```

(`from fastapi import Request`, `from app.domain.models import JobRun`.)

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


def test_reservation_stats_and_no_show(app, school, students, monkeypatch):
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


# ponytail: 방·날짜마다 load_inputs 쿼리 3개(방 100·30일 ≈ 9000 쿼리, SQLite 로 1 s 안쪽). 느려지면 방별로
# 기간 전체 슬롯·예약·시험을 한 번에 읽어 날짜별로 나누는 load_inputs_range 로 바꾼다.
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

- **Spec coverage:** §2.1 스키마·전이·No-show → T1·T3·T8. §2.2 시각·`put_resv` KST·`DAILY_HOUR_LOCAL` → T1·T7. §2.3 `room_state`·벡터(JSON 9, 1 xfail) → T2, RecordProvider → T1. §2.4 제약 7개·선착순·승인 재검사 → T3(T5 라우터 422/400/404/409). §2.5 일일 작업 5단계·트리거·수동 → T7. §2.6 정의(배정 집합·휴강 unused·No-show·bin·within) → T8. §3 스코프(학생 404·관리자 학교·남의 예약 라벨) → T4·T5·T6. §4.1 7개 → T4·T5. §4.2 6개 + 요약 버킷 → T6·T7. §4.3 5개 → T8. §5 README → T9.
- **Placeholder scan:** 없음 (테스트 기대값은 본문에서 확정: p95 = 95, 20시 슬롯 구간 2개, `by_w[0].key == 3`).
- **리뷰(PR #38) 반영:** 🔴5 approve·cancel·승격은 `enqueue_*(session=s)` + 커밋 뒤 알림(T3·T5·T6·T7). 🔴6 `record_provider` approved·KST(T1). 🔴7 승격 `오늘+7` 만·acked 포함 중복 방지(T7). 🔴8 FILE kind·유닛별·방별 try·취소분 제외(T7). 🔴10 tzdata(T1). 🟡 픽스처 충돌 → `students` 분리·학번 S1~S3(T1), FK → 모든 requested_by 테스트가 `students` 요청, 목록 정렬에서 NULL `requested_at` 제거(T6), `"promoted: boom"`(T7), 벡터 JSON·tentative·xfail(T2), 이름 붙인 CHECK(T1), 신청 철회 삭제·하루 10회(T3·T5). ⚪ 이미 시작한 신청 승인 409·창 밖 취소 DEL 없음(T3), 04시 이전 수동 실행이 자동을 막지 않음(T7), allocation 쿼리 수 ceiling 주석(T8).
- **Type consistency:** `clock.*` T1 = 전 Task. `room_state.Span(s, e, type, label, mine, id)`·`room_state()`·`load_inputs()`·`state_of()`·`fmt_hhmm()` T2 = T4·T8. `reserve.validate_request(s, user, room, body, now_local)`·`approve/reject/cancel(by_admin=)/checkin` T3 = T5·T6. `_mine_out`·`_student_room` T4/T5 = T6 `admin.resv_admin_out`. `_free_id(s, Reservation)` = S4b T2. `daily.run_daily(Session, now_utc=None)`·`tick`·`already_ran_today` T7 = T7 테스트·라우터. `analytics.parse_range/allocation/free_slots/reservation_stats/latency/latency_samples` T8 = 라우터. conftest `students`·`student_hdr`·`other_student_hdr`·`student_hdr_school2` T1 = T2~T8. `reserve.addr`·`reserve.withdraw` T3 = T5·T6. `reserve.push_set/push_del` T3 = T3 Step 4b(`_write_resv`·`delete_resv`)·T7 `_promote`. `_ID_LOCK` = T5 신청·T6 승인. `daily._promote(Session, now_local, errors)` T7 = T7 테스트 monkeypatch. `_commit_notify`·`_ID_LOCK` = S2c·S4b. `live`·`db`·`hub` 는 S2 conftest.

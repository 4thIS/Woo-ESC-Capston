# 서버 additive A1~A3 (웹 선행) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 웹 F1·F2·F4 가 기다리는 응답 필드 셋을 기존 필드는 그대로 둔 채 더한다(additive) — 회원 거절 사유(A1), 관리자 예약 표의 신청자·`pushed_at`(A2), 학생 주간 표의 합친 `busy` 와 신청 가능한 `free`(A3).

**Architecture:** A1·A2 는 스키마 필드 추가와 조회 헬퍼 한 개(`admin.resv_with_room_rows`, 신청자를 한 쿼리로 조인)다. A3 의 `busy` 는 `room_state.merge_busy`(겹친 구간 합치기)와 `room_state.week_busy`(주간 로더)가, `free` 는 `reserve.free_spans`/`free_days` 가 만든다. `free` 는 신청 겹침 검사 `reserve.overlaps` 와 **같은 차단 목록**(`reserve._blockers`)의 여집합이라, 화면에 보인 빈 구간은 겹침 409 가 나지 않는다.

**Tech Stack:** Python 3.12 · FastAPI · SQLAlchemy 2 · Pydantic v2 · pytest · ruff · uv

**Spec:** `docs/specs/2026-09-25-web-frontend-design.md` §6 「서버 additive」 A1~A3 (+ 소비 화면 `docs/design/screens/admin-users.md` 거절 사유 툴팁, `admin-rooms.md` 예약 표 신청자·학번·`예정`, `student-room.md` 주간 격자 §겹침·예약 §화면이 거는 제약·§데이터 ⚠, 서버 계약 `docs/specs/2026-09-23-s10-student-analytics-design.md` §2.4·§2.6·§4.1)

## Global Constraints

- 작업 위치: `server/` 만. `server/app/lora_service/`·마이그레이션은 건드리지 않는다(컬럼 추가 없음 — 필요한 값은 이미 DB 에 있다: `users.reject_reason`, `reservations.pushed_at`·`requested_by`).
- 브랜치: 메인 체크아웃 `C:\Users\Monta\Desktop\Woo-ESC-Capston` 에서 `feature/s10-student` 로부터 `feature/web-server-additive` 를 만든다(Task 1 Step 0). force push·`reset --hard` 금지.
- 응답은 **additive 만** — 기존 필드의 이름·타입·의미를 바꾸지 않는다. 새 필드는 기본값(`None`·`[]`)을 준다. 유일한 기존 동작 변경은 둘: `GET /api/rooms/{id}/reservations` 의 정렬에 `s_h, s_m` 를 더한 것(같은 날 두 건의 순서가 정해지지 않았다)과 `GET /api/student/rooms/{id}/week?date=` 가 `9999-12-27` 이후를 500 대신 422 로 거절하는 것.
- 개인정보: 신청자 `requester{email, name, student_no}` 는 **관리자 전용 라우터**(`/api/**` 의 `AdminUser`, `/api/admin/**`)에서만 나간다. 학생 응답(`WeekOut`)에는 남의 신청의 `subject`·이메일이 없고 라벨 `"예약됨"` 뿐이다(`room_state.public_label`).
- 학교 스코프: 타 학교 리소스는 404(S4a §3.3). 새 코드는 기존 스코프 함수(`_rooms_of`·`scope.get_scoped`·`_student_room`) 뒤에서만 돈다.
- 시각: 판정은 KST(`clock.local_now()`), 응답 `*_at` 은 naive UTC 그대로. `busy`·`free` 의 시각은 `"HH:MM"` 문자열(`FreeRange` 와 같은 `from`/`to`).
- 운영 시간 09:00~21:00 KST(S10 §2.6) — 값은 `reserve.OPEN_MIN`/`CLOSE_MIN` 한 곳, `analytics` 는 그것을 가리킨다.
- 신청 제약(S10 §2.4)은 그대로: 5분 격자, 15~120분, 시작 > 지금, 오늘~+7, 겹침(슬롯 type 무관 + approved + requested), 방 용량 24.
- 테스트: `cd server && uv run pytest -q`. 린트: `uv run ruff check . && uv run ruff format --check .`. 매 Task 끝에 둘 다 통과.
- Windows 체크아웃(`core.autocrlf=true`) — 만든·고친 파일은 `uv run ruff format` 으로 정리, CRLF 만 바뀐 파일은 커밋하지 않는다(`git diff --stat` 로 확인).
- 커밋: `feat(server): …` / `test(server): …`. Claude·AI 저작 표기와 `Co-Authored-By` 트레일러 금지.

## Review Focus

테스트가 직접 겨누지 않으면 사람이 가장 먼저 밟을 입력·상황 다섯. 각 줄의 고정 테스트는 담당 Task 에 들어 있다.

1. 학생 A 가 주간 표를 연다 — 학생 B 의 `requested` 가 **"예약됨"**·`status: null` 로만 보이고 B 의 용도·이메일은 응답 본문 어디에도 없다. A 자신의 신청은 `status: "requested"`, 승인분은 `"approved"`. — Task 3 `test_week_busy_merges_and_hides_requesters`
2. `free` 에 보인 구간의 첫 15분을 신청 → 201, 그 경계를 5분만 넘으면 → 409. 신청 직후 다시 열면 그 15분이 `free` 에서 빠진다. — Task 4 `test_week_free_spans_match_what_request_accepts`
3. 자정 직후(KST 00:10, UTC 로는 전날 15:10)와 운영 종료 직전(20:40·20:50)에 연다 — 날짜 칩은 KST 날짜로 시작하고, 20:40 은 `20:45–21:00`(딱 15분), 20:50 은 빈 목록. — Task 4 `test_week_free_uses_kst_today_and_operating_hours`
4. 다른 학교 관리자·학생 토큰으로 건물/방 예약 목록을 부른다 — 404/403, 신청자 이름·학번이 새지 않는다. — Task 2 `test_reservation_reads_carry_status_requester_pushed_at`
5. 거절 사유가 거절 행에만 있고 학생 `/api/auth/me` 에는 `null` 이다. — Task 1 `test_reject_reason_only_on_rejected_rows`

## Rulings (spec·디자인이 어긋난 곳 — 컨트롤러 확인됨)

- **A2 `requester` 모양**: spec 은 `{name, student_no}`, 기존 `RequesterOut` 은 `{email, name, student_no}`. 기존 타입을 그대로 쓴다 — 관리자 전용 응답이고 `admin-rooms.md` 신청 대기 블록이 이메일을 툴팁으로 쓴다.
- **시험기간과 `free`**: `student-room.md` 제약 표는 시험기간도 겹침이라 적었지만, 서버 `reserve.overlaps` 는 슬롯 없는 시험기간을 막지 않는다. `free` 는 서버가 실제로 받는 것을 따른다(더 좁게 보이면 신청 가능한 시간이 숨고, 더 넓게 보이면 409).
- **빈강의실(type 4) 슬롯과 `busy`**: `room_state` 는 type 4 를 FREE 로 그리지만 `overlaps` 는 type 무관하게 막는다. `busy` 에 type 4 그대로 싣는다 — 격자에 빈 칸으로 보이는데 `free` 에 없는 모순을 막고, 그리기는 화면이 `type` 으로 정한다.
- **`busy` 의 `status`**: 내 예약만 `'requested'|'approved'`, 남의 것·관리자 예약·슬롯은 `None`(남의 신청은 존재만 보인다). 격자가 "내 신청(대기)"와 "내 예약"을 가른다.
- **`WeekOut.full`**: 신청 검사와 같은 `reserve.room_full`(창 안 approved+requested ≥ 24). 참이면 `free` 는 전부 빈 목록 — 화면은 "빈 시간 없음"이 아니라 "예약이 가득 찼어요".

## 범위 밖

- 운영 시간(09~21) 강제를 `reserve.validate_request` 에 넣는 것 — API 로 07:00 신청은 지금도 받는다. `free` 가 운영 시간 안만 보여줄 뿐이다. 별도 이슈.

## 파일 지도

```
server/
├── app/
│   ├── schemas.py               UserOut.reject_reason · ResvAdminOut.pushed_at · ResvWithRoom.requester/pushed_at ·
│   │                            FreeRange(위로 이동) · BusySpan · BusyDay · FreeDay · WeekOut.busy/free
│   └── domain/
│       ├── admin.py             _requester · resv_admin_out(+pushed_at) · resv_with_room_rows
│       ├── router.py            building_reservations · list_resv → resv_with_room_rows
│       ├── room_state.py        merge_busy · week_busy
│       ├── reserve.py           OPEN_MIN/CLOSE_MIN/STEP_MIN · _blockers · overlaps(리팩터) · free_spans · free_days
│       ├── analytics.py         OPEN_MIN/CLOSE_MIN 을 reserve 에서
│       └── student_router.py    week: date 상한 422 · busy · free
└── tests/
    ├── test_auth_admin_cli.py   A1
    ├── test_admin_building.py   A2 (건물·방 목록, 스코프)
    ├── test_admin_resv.py       A2 (관리자 목록 pushed_at)
    ├── test_room_state.py       merge_busy 단위
    └── test_student_rooms.py    A3 busy · date 상한 · free 3종
```

## Task 순서와 의존

| Task | 내용 | 의존 |
|---|---|---|
| 1 | A1 `UserOut.reject_reason` (+ 브랜치 생성) | — |
| 2 | A2 관리자 예약 응답에 `requester`·`pushed_at` | 1 |
| 3 | A3 `WeekOut.busy` — 겹침 합치기 + `date` 상한 | 1 |
| 4 | A3 `WeekOut.free` · `full` — 신청 가능 구간과 가득 참 | 3 |

Task 2 와 3 은 서로 독립이지만 같은 `schemas.py` 를 고치므로 순서대로 한다.

---

### Task 1: A1 — `UserOut.reject_reason`

**Files:**
- Modify: `server/app/schemas.py`
- Test: `server/tests/test_auth_admin_cli.py`

**Interfaces:**
- Consumes: `User.reject_reason`(ORM, 이미 있음). `POST /api/admin/users/{email}/reject` 가 채운다. 재신청(`/api/auth/verify`)은 거절 행을 **지우고 새로 만들므로** 값이 남지 않는다.
- Produces: `S.UserOut.reject_reason: str | None = None`. 이것을 쓰는 모든 응답(`GET /api/admin/users`, 승인·거절·정지·해제 응답, `GET /api/auth/me`, `summary.warnings.pending_approval.items`)에 필드가 생긴다.

규칙(가장 작은 안전 규칙): 필드는 `UserOut` 하나에 두고 가리지 않는다. 값이 있는 행은 `status == "rejected"` 뿐이고, `/api/auth/me` 는 `active` 만 통과하므로(`current_user`) 학생 본인 응답에서는 구조적으로 `null` 이다. 테스트가 그 사실을 고정한다.

- [ ] **Step 0: 브랜치**

```bash
cd C:/Users/Monta/Desktop/Woo-ESC-Capston
git switch feature/s10-student && git pull --ff-only
git switch -c feature/web-server-additive
```

- [ ] **Step 1: 실패 테스트**

`server/tests/test_auth_admin_cli.py` 끝에 추가
```python
def test_reject_reason_only_on_rejected_rows(client, app, hdr, mails):
    r = client.post(
        "/api/admin/users/p1@mju.ac.kr/reject", json={"reason": "학번 불일치"}, headers=hdr
    )
    assert r.json()["reject_reason"] == "학번 불일치"
    rows = {u["email"]: u for u in client.get("/api/admin/users", headers=hdr).json()}
    assert rows["p1@mju.ac.kr"]["reject_reason"] == "학번 불일치"
    assert rows["a1@mju.ac.kr"]["reject_reason"] is None
    assert "o@other.ac.kr" not in rows  # 타 학교 행은 사유째 안 보인다
    me = client.get("/api/auth/me", headers=_hdr(app, "a1@mju.ac.kr")).json()
    assert me["reject_reason"] is None  # 학생 본인 응답 — active 만 /me 를 통과한다
```

- [ ] **Step 2: 실패 확인**

Run: `cd server && uv run pytest -q tests/test_auth_admin_cli.py -k reject_reason`
Expected: FAIL — `KeyError: 'reject_reason'`

- [ ] **Step 3: 구현**

`server/app/schemas.py` 의 `UserOut` — `approved_at` 다음 줄에 추가
```python
class UserOut(Out):
    email: str
    school_id: int
    role: str
    status: str
    name: str
    student_no: str | None
    created_at: dt.datetime
    approved_at: dt.datetime | None
    # web A1 — 관리자 회원 목록의 거절 사유. 값은 status=rejected 행에만 있다: 재신청(verify)이 행을
    # 교체하고 /api/auth/me 는 active 만 통과하므로 학생 본인 응답에서는 구조적으로 null
    reject_reason: str | None = None
```

- [ ] **Step 4: 통과 확인**

Run: `cd server && uv run pytest -q tests/test_auth_admin_cli.py && uv run ruff check . && uv run ruff format --check .`
Expected: `6 passed`, `All checks passed!`, `already formatted`

- [ ] **Step 5: 커밋**

```bash
git add server/app/schemas.py server/tests/test_auth_admin_cli.py
git commit -m "feat(server): UserOut.reject_reason — 관리자 회원 목록에 거절 사유 (web A1)"
```

---

### Task 2: A2 — 관리자 예약 응답에 `requester` · `pushed_at`

**Files:**
- Modify: `server/app/schemas.py`, `server/app/domain/admin.py`, `server/app/domain/router.py`
- Test: `server/tests/test_admin_building.py`, `server/tests/test_admin_resv.py`

**Interfaces:**
- Consumes: `S.RequesterOut{email, name, student_no}`(있음), `Reservation.requested_by`(users.email FK)·`pushed_at`(있음). `ResvOut.status` 는 이미 ORM 값을 읽는다(`ResvWithRoom` 에 이미 있음 — 이 Task 가 테스트로 고정만 한다).
- Produces:
  - `S.ResvWithRoom` += `requester: RequesterOut | None = None`, `pushed_at: dt.datetime | None = None`
  - `S.ResvAdminOut` += `pushed_at: dt.datetime | None = None`
  - `admin._requester(u: User | None) -> dict | None`
  - `admin.resv_with_room_rows(s: Session, q) -> list[dict]` — `q` 는 `select(Reservation)…`. 신청자를 **한 쿼리**로 읽는다(건물 전체면 수백 행 — 행마다 `s.get` 하지 않게).
  - `GET /api/buildings/{id}/reservations` → `ResvWithRoom[]`(필드 추가), `GET /api/rooms/{id}/reservations` → `ResvOut[]` 에서 **`ResvWithRoom[]`** 로(필드 추가: `room_id`·`requester`·`pushed_at`, 정렬 `date, s_h, s_m`), `GET /api/admin/reservations` 와 승인·거절·취소 응답 → `ResvAdminOut` 에 `pushed_at`.

규칙: 화면의 `예정` 배지 = `pushed_at IS NULL`(노드에 없음 — 7일 창 밖 승인, 또는 신청). 신청자는 `requested_by` 로 조인하고 관리자가 넣은 예약은 `null`. spec 은 `requester{name, student_no}` 라 적었지만 기존 `RequesterOut`(이메일 포함)을 그대로 쓴다 — 관리자 전용 응답이고 `admin-rooms.md` 신청 대기 블록이 이메일 툴팁을 쓴다.

- [ ] **Step 1: 실패 테스트**

`server/tests/test_admin_building.py` 끝에 추가 (이 파일은 이미 `dt`·`Reservation` 을 import 한다)
```python
def test_reservation_reads_carry_status_requester_pushed_at(
    client, app, school, students, other_admin_hdr, student_hdr
):
    bid, ids = _building(app, 1, "E")
    pushed = dt.datetime(2026, 9, 23, 1, 30)  # noqa: DTZ001 — 앱 전역이 naive UTC
    with app.state.Session() as s, s.begin():
        s.add_all(
            [
                Reservation(
                    id=1,
                    room_id=ids[101],
                    date=dt.date(2026, 9, 24),
                    s_h=9,
                    s_m=0,
                    e_h=10,
                    e_m=0,
                    type=6,
                    subject="행사",
                    professor="학생처",
                    pushed_at=pushed,
                ),
                Reservation(
                    id=2,
                    room_id=ids[101],
                    date=dt.date(2026, 9, 24),
                    s_h=13,
                    s_m=0,
                    e_h=14,
                    e_m=0,
                    type=6,
                    subject="스터디",
                    professor="",
                    status="requested",
                    requested_by="s1@mju.ac.kr",
                ),
                Reservation(
                    id=3,
                    room_id=ids[102],
                    date=dt.date(2026, 12, 1),
                    s_h=9,
                    s_m=0,
                    e_h=10,
                    e_m=0,
                    type=6,
                    subject="창 밖",
                    professor="",
                ),
            ]
        )
    s1 = {"email": "s1@mju.ac.kr", "name": "학생1", "student_no": "S1"}
    got = client.get(f"/api/buildings/{bid}/reservations").json()
    assert [(x["id"], x["status"], x["requester"], x["pushed_at"]) for x in got] == [
        (1, "approved", None, "2026-09-23T01:30:00"),
        (2, "requested", s1, None),
        (3, "approved", None, None),  # 창 밖 — pushed_at NULL 이 '예정' 배지
    ]
    got = client.get(f"/api/rooms/{ids[101]}/reservations").json()
    assert [(x["id"], x["room_id"], x["requester"], x["pushed_at"]) for x in got] == [
        (1, ids[101], None, "2026-09-23T01:30:00"),
        (2, ids[101], s1, None),
    ]
    # 신청자 이름·학번은 자기 학교 관리자에게만
    for path in (f"/api/buildings/{bid}/reservations", f"/api/rooms/{ids[101]}/reservations"):
        assert client.get(path, headers=other_admin_hdr).status_code == 404, path
        assert client.get(path, headers=student_hdr).status_code == 403, path
```

`server/tests/test_admin_resv.py` 끝에 추가 (이 파일의 `_resv` 는 이미 `pushed_at` 인자를 받는다)
```python
def test_list_carries_pushed_at(client, app, school, students, monkeypatch):
    _fix_clock(monkeypatch)
    _, ids = _building(app, 1, "E")
    _resv(app, ids[101], dt.date(2026, 9, 24), 13, 0, 14, 0, id_=1, pushed_at=UTC_NOW)
    _resv(app, ids[101], dt.date(2026, 12, 1), 13, 0, 14, 0, id_=2)  # 창 밖 — 아직 안 보냄
    got = client.get("/api/admin/reservations?status=approved").json()
    assert [(x["id"], x["pushed_at"]) for x in got] == [(1, "2026-09-23T01:30:00"), (2, None)]
```

- [ ] **Step 2: 실패 확인**

Run: `cd server && uv run pytest -q tests/test_admin_building.py tests/test_admin_resv.py`
Expected: FAIL 2개 — `KeyError: 'requester'`(건물 목록), `KeyError: 'pushed_at'`(관리자 목록)

- [ ] **Step 3: 구현**

`server/app/schemas.py` — 두 클래스를 아래로 바꾼다
```python
class ResvAdminOut(ResvMineOut):
    requester: RequesterOut | None
    pushed_at: dt.datetime | None = None  # web A2 — NULL = 노드에 없음, 화면의 '예정' 배지
```
```python
class ResvWithRoom(ResvOut):
    room_id: int
    # web A2 — 관리자 예약 표의 신청자·학번 열과 '예정' 배지. 관리자 전용 라우터에서만 쓴다
    requester: RequesterOut | None = None  # 관리자가 넣은 예약은 null
    pushed_at: dt.datetime | None = None
```

`server/app/domain/admin.py` — 기존 `resv_admin_out` 전체를 아래 셋으로 바꾼다(`select`·`S`·`User` 는 이미 import 돼 있다)
```python
def _requester(u: User | None) -> dict | None:
    return {"email": u.email, "name": u.name, "student_no": u.student_no} if u else None


def resv_admin_out(s: Session, r: Reservation) -> dict:
    u = s.get(User, r.requested_by) if r.requested_by else None
    return {**_mine_out(s, r), "requester": _requester(u), "pushed_at": r.pushed_at}


def resv_with_room_rows(s: Session, q) -> list[dict]:
    """select(Reservation) → ResvWithRoom dict (web A2). 신청자는 한 쿼리로 읽는다 — 건물 전체가 수백 행."""
    rows = s.scalars(q).all()
    emails = {r.requested_by for r in rows if r.requested_by}
    users = {u.email: u for u in s.scalars(select(User).where(User.email.in_(emails)))}
    return [
        {
            **S.ResvOut.model_validate(r).model_dump(),
            "room_id": r.room_id,
            "requester": _requester(users.get(r.requested_by)),
            "pushed_at": r.pushed_at,
        }
        for r in rows
    ]
```

`server/app/domain/router.py` — 두 핸들러 전체를 아래로 바꾼다(`admin` 은 이미 import 돼 있다)
```python
@router.get("/buildings/{id}/reservations", response_model=list[S.ResvWithRoom])
def building_reservations(id: int, user: User = AdminUser, s: Session = _DB):
    return admin.resv_with_room_rows(
        s,
        select(Reservation)
        .where(Reservation.room_id.in_(_rooms_of(s, id, user)))
        .order_by(Reservation.room_id, Reservation.date, Reservation.s_h, Reservation.s_m),
    )
```
```python
@router.get("/rooms/{id}/reservations", response_model=list[S.ResvWithRoom])
def list_resv(id: int, user: User = AdminUser, s: Session = _DB):
    scope.get_scoped(s, Room, id, user.school_id)
    return admin.resv_with_room_rows(
        s,
        select(Reservation)
        .where(Reservation.room_id == id)
        .order_by(Reservation.date, Reservation.s_h, Reservation.s_m),
    )
```

- [ ] **Step 4: 통과 확인**

Run: `cd server && uv run pytest -q tests/test_admin_building.py tests/test_admin_resv.py tests/test_domain.py tests/test_admin_ids.py && uv run ruff check . && uv run ruff format --check .`
Expected: 전부 PASS(기존 `test_domain`·`test_admin_ids` 의 방 단위 예약 조회 포함), `All checks passed!`

- [ ] **Step 5: 커밋**

```bash
git add server/app/schemas.py server/app/domain/admin.py server/app/domain/router.py server/tests/test_admin_building.py server/tests/test_admin_resv.py
git commit -m "feat(server): 관리자 예약 응답에 requester·pushed_at — 신청자 열과 예정 배지 (web A2)"
```

---

### Task 3: A3 — `WeekOut.busy` (겹침 합치기) + `date` 상한

**Files:**
- Modify: `server/app/schemas.py`, `server/app/domain/room_state.py`, `server/app/domain/student_router.py`
- Test: `server/tests/test_room_state.py`, `server/tests/test_student_rooms.py`

**Interfaces:**
- Consumes: `room_state.Span(s, e, type, label, mine=False, id=None)`, `room_state.public_label(r, viewer_email) -> (mine, label)`, `room_state.fmt_hhmm`, `clock.week_start`.
- Produces:
  - `room_state.Span` += `status: str | None = None`(마지막 필드 — 기존 위치 인자 생성은 그대로)
  - `room_state.merge_busy(spans: list[Span]) -> list[Span]`
  - `room_state.week_busy(s: Session, room_id: int, start: dt.date, viewer_email: str) -> list[dict]` — 항상 7개 `{"day": 1..7, "spans": [{"from", "to", "label", "type", "mine", "status"}]}`
  - `S.BusySpan(FreeRange)`(`label: str`, `type: int`, `mine: bool`, `status: Literal["requested", "approved"] | None = None`), `S.BusyDay{day: int, spans: list[BusySpan]}`, `S.WeekOut.busy: list[BusyDay] = []`. `FreeRange` 는 `WeekOut` 위로 **옮긴다**(내용 불변 — `BusySpan` 이 상속하고 Task 4 의 `FreeDay` 가 쓴다).
  - `GET /api/student/rooms/{id}/week?date=` 가 `9999-12-26` 보다 뒤면 422(그 주 일요일이 `date` 범위를 넘어 지금은 `OverflowError` 500).

규칙(`student-room.md` §겹침 + spec A3):
- 입력 = 그 요일 정규 슬롯(type 무관) + 그 날 `approved` + `requested`(남의 것은 `"예약됨"`, 내 것은 용도 + `mine`). `rejected`·`cancelled`·`expired` 는 뺀다.
- 시험기간인 날의 슬롯은 `type` 2 — `room_state` 가 시험기간 중 슬롯 구간을 시험(layout 5)으로 그리는 것과 같다. 슬롯 없는 시험기간은 아무것도 그리지 않는다(`reserve.overlaps` 도 막지 않는다).
- `status` 는 내 예약만(`mine` 일 때 행의 `status`), 남의 것·관리자 예약·슬롯은 `None`.
- 1분이라도 겹치면 한 덩어리: 머리 = 먼저 시작한 것(같으면 긴 것), 라벨 `"<머리> 외 N건"`, 시각 = 합집합, `type` = 머리의 것, `mine` = 하나라도 내 것, `status` = 머리부터 첫 내 것의 상태. 맞닿기만 한 구간(10:00 끝·10:00 시작)은 따로.
- `type` 4(빈강의실) 슬롯도 `busy` 에 싣는다 — 신청을 막으므로(`reserve.overlaps` type 무관) 격자에서 빈 칸으로 보이면 `free` 와 어긋난다. 그리기는 화면이 `type` 으로 정한다.
- 시작 ≥ 끝인 행(관리자 입력엔 순서 검증이 없다)은 그리지 않는다.
- `busy` 는 `date` 가 가리키는 주(월~일) 전체 — 지난 요일도 그대로.

- [ ] **Step 1: 실패 테스트**

`server/tests/test_room_state.py` 끝에 추가 (파일 상단의 `RS`·`Span`·`M` 을 쓴다)
```python
def test_merge_busy_chains_overlaps_but_keeps_touching_apart():
    out = RS.merge_busy(
        [
            Span(M(11), M(13), 6, "동아리 대관"),
            Span(M(10), M(12), 1, "알고리즘"),
            Span(M(12, 30), M(14), 6, "예약됨", mine=True),
            Span(M(14), M(15), 1, "운영체제"),  # 14:00 에 맞닿기만 — 따로 둔다
            Span(M(16), M(15), 1, "뒤집힘"),  # 관리자 입력엔 시작<끝 검증이 없다 — 버린다
        ]
    )
    assert [(x.s, x.e, x.type, x.label, x.mine) for x in out] == [
        (M(10), M(14), 1, "알고리즘 외 2건", True),
        (M(14), M(15), 1, "운영체제", False),
    ]
    same = RS.merge_busy([Span(M(9), M(10), 6, "짧은"), Span(M(9), M(11), 1, "긴")])
    assert [(x.label, x.e) for x in same] == [("긴 외 1건", M(11))]  # 같은 시작이면 긴 것이 머리
    mixed = RS.merge_busy(
        [Span(M(9), M(11), 1, "수업"), Span(M(10), M(12), 6, "스터디", True, status="requested")]
    )
    assert [(x.label, x.mine, x.status) for x in mixed] == [("수업 외 1건", True, "requested")]
    assert RS.merge_busy([]) == []
```

`server/tests/test_student_rooms.py` 끝에 추가 (파일 상단의 `_fix_clock`·`_building`·`_slot`·`_resv`·`_exam` 을 쓴다)
```python
def test_week_busy_merges_and_hides_requesters(
    client, app, school, student_hdr, other_student_hdr, monkeypatch
):
    _fix_clock(monkeypatch)  # KST 수 9/23 10:30 — 주 = 9/21(월)~9/27(일)
    _, ids = _building(app, 1, "E", rooms=((101, 1), (102, 1)))
    rid = ids[101]
    _slot(app, rid, 2, 9, 0, 10, 0, subject="A")
    _slot(app, rid, 2, 10, 0, 11, 0, subject="B")  # 10:00 에 맞닿기만 — 합치지 않는다
    _exam(app, rid, 1, dt.date(2026, 9, 22), dt.date(2026, 9, 22))  # 화요일만 시험기간
    _slot(app, rid, 5, 10, 0, 12, 0, subject="알고리즘")
    _resv(app, rid, dt.date(2026, 9, 25), 11, 0, 13, 0, id_=1, subject="동아리 대관")
    thu = dt.date(2026, 9, 24)
    _resv(
        app,
        rid,
        thu,
        14,
        0,
        15,
        0,
        id_=2,
        status="requested",
        requested_by="s2@mju.ac.kr",
        subject="비밀",
    )
    _resv(
        app,
        rid,
        thu,
        16,
        0,
        17,
        0,
        id_=3,
        status="requested",
        requested_by="s1@mju.ac.kr",
        subject="스터디",
    )
    _resv(app, rid, thu, 18, 0, 19, 0, id_=9, requested_by="s1@mju.ac.kr", subject="내 예약")
    _resv(app, rid, thu, 9, 0, 10, 0, id_=4, status="rejected", requested_by="s2@mju.ac.kr")
    _resv(app, rid, thu, 10, 0, 11, 0, id_=5, status="cancelled")
    _resv(app, rid, thu, 11, 0, 12, 0, id_=6, status="expired", requested_by="s2@mju.ac.kr")
    _resv(app, ids[102], thu, 9, 0, 10, 0, id_=7)  # 다른 방
    _resv(app, rid, dt.date(2026, 9, 28), 9, 0, 10, 0, id_=8)  # 다음 주
    r = client.get(f"/api/student/rooms/{rid}/week", headers=student_hdr)
    assert r.status_code == 200
    assert [d["day"] for d in r.json()["busy"]] == [1, 2, 3, 4, 5, 6, 7]
    busy = {
        d["day"]: [
            (x["from"], x["to"], x["label"], x["type"], x["mine"], x["status"]) for x in d["spans"]
        ]
        for d in r.json()["busy"]
    }
    assert busy == {
        1: [],
        2: [("09:00", "10:00", "A", 2, False, None), ("10:00", "11:00", "B", 2, False, None)],
        3: [],
        4: [
            ("14:00", "15:00", "예약됨", 6, False, None),  # 남의 신청 — 상태도 숨긴다
            ("16:00", "17:00", "스터디", 6, True, "requested"),  # 내 신청(대기)
            ("18:00", "19:00", "내 예약", 6, True, "approved"),
        ],
        5: [("10:00", "13:00", "알고리즘 외 1건", 1, False, None)],
        6: [],
        7: [],
    }
    assert "비밀" not in r.text and "s2@mju.ac.kr" not in r.text  # 남의 신청은 존재만 보인다
    j2 = client.get(f"/api/student/rooms/{rid}/week", headers=other_student_hdr).json()
    assert [(x["label"], x["mine"], x["status"]) for x in j2["busy"][3]["spans"]] == [
        ("비밀", True, "requested"),
        ("예약됨", False, None),
        ("예약됨", False, None),  # s1 의 승인 예약도 남에게는 상태 없이
    ]


def test_week_date_upper_bound_is_422_not_500(client, app, school, student_hdr, monkeypatch):
    _fix_clock(monkeypatch)
    _, ids = _building(app, 1, "E")
    url = f"/api/student/rooms/{ids[101]}/week"
    # 9999-12-27(월) 의 주 끝은 10000년 — 계산하면 OverflowError(500)
    assert client.get(f"{url}?date=9999-12-27", headers=student_hdr).status_code == 422
    j = client.get(f"{url}?date=9999-12-26", headers=student_hdr).json()
    assert j["week_start"] == "9999-12-20" and len(j["busy"]) == 7
```

- [ ] **Step 2: 실패 확인**

Run: `cd server && uv run pytest -q tests/test_room_state.py tests/test_student_rooms.py`
Expected: FAIL 3개 — `AttributeError: module 'app.domain.room_state' has no attribute 'merge_busy'`, `KeyError: 'busy'`, `OverflowError: date value out of range`

- [ ] **Step 3: 구현**

`server/app/schemas.py`
1. 파일 아래쪽(`AllocationOut` 다음)의 `class FreeRange` 블록을 **지운다**.
2. `class WeekOut` 전체를 아래 블록으로 바꾼다(지운 `FreeRange` 가 여기 온다)
```python
class FreeRange(BaseModel):
    from_: str = Field(alias="from")
    to: str
    model_config = ConfigDict(populate_by_name=True)


class BusySpan(FreeRange):
    label: str  # 남의 학생 예약·신청은 "예약됨" (room_state.public_label)
    type: int  # 1~6. 시험기간 안의 정규 슬롯은 2
    mine: bool
    # 내 예약만 — 격자가 '내 신청(대기)'과 '내 예약'을 가른다. 남의 것·슬롯은 None
    status: Literal["requested", "approved"] | None = None


class BusyDay(BaseModel):
    day: int  # 1=월 … 7=일 (SlotOut.day 와 같다)
    spans: list[BusySpan]


class WeekOut(BaseModel):
    room: RoomStateOut
    week_start: dt.date
    slots: list[SlotOut]
    reservations: list[ResvPublicOut]
    exams: list[ExamOut]
    busy: list[BusyDay] = []  # web A3 — 겹친 구간을 합친 요일별 사용 구간 (room_state.week_busy)
```

`server/app/domain/room_state.py`
- `class Span` 의 `id` 필드 다음에 한 줄 추가
```python
    status: str | None = None  # 내 예약만 'requested'|'approved' (web A3 busy)
```
- import 두 줄을 바꾼다
```python
import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, replace
```
- 파일 끝(`fmt_hhmm` 다음)에 추가
```python
def merge_busy(spans: list[Span]) -> list[Span]:
    """1분이라도 겹친 구간을 한 덩어리로 (student-room §겹침). 머리 = 먼저 시작한 것(같으면 긴 것) —
    라벨은 머리 + ' 외 N건', type 도 머리 것, mine 은 하나라도 내 것이면, status 는 머리부터 첫 내 것의
    상태. 맞닿기만 한 구간은 따로 둔다."""
    out: list[tuple[Span, int]] = []
    for x in sorted(spans, key=lambda x: (x.s, -x.e)):
        if x.e <= x.s:
            continue  # ponytail: 관리자 입력엔 시작<끝 검증이 없다 — 뒤집힌 구간은 그리지 않는다
        if out and x.s < out[-1][0].e:
            head, n = out[-1]
            merged = replace(
                head, e=max(head.e, x.e), mine=head.mine or x.mine, status=head.status or x.status
            )
            out[-1] = (merged, n + 1)
        else:
            out.append((x, 0))
    return [replace(h, label=f"{h.label} 외 {n}건") if n else h for h, n in out]


_BUSY_STATUSES = ("approved", "requested")  # = reserve._LIVE. reserve 를 import 하면 순환


def week_busy(s: Session, room_id: int, start: dt.date, viewer_email: str) -> list[dict]:
    """주간 격자의 요일별 사용 구간 (web A3). 정규 슬롯 · approved · requested(남의 것은 '예약됨')를
    날짜마다 merge_busy. 시험기간 안의 슬롯은 type 2 — room_state 가 그 구간을 시험으로 그리는 것과 같다.
    시험기간만 있고 슬롯이 없는 날은 비어 있다(겹침 검사 reserve.overlaps 도 그렇게 본다)."""
    end = start + dt.timedelta(days=6)
    slots: dict[int, list[Span]] = defaultdict(list)
    for x in s.scalars(select(Slot).where(Slot.room_id == room_id)):
        slots[x.day].append(Span(x.s_h * 60 + x.s_m, x.e_h * 60 + x.e_m, x.type, x.subject))
    resvs: dict[dt.date, list[Span]] = defaultdict(list)
    for r in s.scalars(
        select(Reservation).where(
            Reservation.room_id == room_id,
            Reservation.date.between(start, end),
            Reservation.status.in_(_BUSY_STATUSES),
        )
    ):
        mine, label = public_label(r, viewer_email)
        st = r.status if mine else None  # 남의 것은 상태도 숨긴다 — 존재만
        resvs[r.date].append(
            Span(r.s_h * 60 + r.s_m, r.e_h * 60 + r.e_m, r.type, label, mine, status=st)
        )
    exams = s.execute(
        select(ExamPeriod.date_start, ExamPeriod.date_end).where(
            ExamPeriod.room_id == room_id,
            ExamPeriod.date_start <= end,
            ExamPeriod.date_end >= start,
        )
    ).all()
    out = []
    for i in range(7):
        d = start + dt.timedelta(days=i)
        day_slots = slots[d.isoweekday()]
        if any(a <= d <= b for a, b in exams):
            day_slots = [replace(x, type=2) for x in day_slots]
        spans = merge_busy(day_slots + resvs[d])
        out.append(
            {
                "day": d.isoweekday(),
                "spans": [
                    {
                        "from": fmt_hhmm(x.s),
                        "to": fmt_hhmm(x.e),
                        "label": x.label,
                        "type": x.type,
                        "mine": x.mine,
                        "status": x.status,
                    }
                    for x in spans
                ],
            }
        )
    return out
```

`server/app/domain/student_router.py`
- import 한 줄을 바꾼다
```python
from fastapi import APIRouter, HTTPException, Query
```
- `@router.get("/rooms/{id}/week", ...)` 데코레이터와 `def week(...)` 시그니처 두 줄을 아래로 바꾼다(모듈 싱글턴 — 인라인 `Query(...)` 는 ruff B008)
```python
# 9999-12-26 = 그 주 일요일이 date 범위 안인 마지막 날 — 넘기면 week_start+6 이 OverflowError(500)
_WEEK_DATE = Query(None, le=dt.date(9999, 12, 26))


@router.get("/rooms/{id}/week", response_model=S.WeekOut)
def week(id: int, date: dt.date | None = _WEEK_DATE, user: User = StudentUser, s: Session = _DB):
```
- 같은 함수의 `return {...}` 딕셔너리 끝, `"exams": …` 항목 다음에 한 줄 추가
```python
        "busy": room_state.week_busy(s, id, start, user.email),
```

- [ ] **Step 4: 통과 확인**

Run: `cd server && uv run pytest -q && uv run ruff check . && uv run ruff format --check .`
Expected: 전부 PASS(기존 xfail 2개는 그대로 — #14 야간 교시), `All checks passed!`

- [ ] **Step 5: 커밋**

```bash
git add server/app/schemas.py server/app/domain/room_state.py server/app/domain/student_router.py server/tests/test_room_state.py server/tests/test_student_rooms.py
git commit -m "feat(server): WeekOut.busy — 슬롯·승인·남의 신청을 겹침 병합한 요일별 구간 (web A3)"
```

---

### Task 4: A3 — `WeekOut.free` · `full` (신청 가능 구간 · 가득 참)

**Files:**
- Modify: `server/app/schemas.py`, `server/app/domain/reserve.py`, `server/app/domain/analytics.py`, `server/app/domain/student_router.py`
- Test: `server/tests/test_student_rooms.py`

**Interfaces:**
- Consumes: `S.FreeRange`(Task 3 에서 `WeekOut` 위로 옮김), `reserve.room_full`, `reserve._hit`, `reserve.MIN_MIN`, `topology.RESV_HORIZON_DAYS`(=7), `room_state.fmt_hhmm`.
- Produces:
  - `reserve.OPEN_MIN, reserve.CLOSE_MIN = 540, 1260`, `reserve.STEP_MIN = 5`; `analytics.OPEN_MIN/CLOSE_MIN` 은 이 값을 가리킨다.
  - `reserve._blockers(s, room_id, date, exclude_id=None) -> list` — 그 요일 슬롯 + 그 날 `approved`/`requested` 행. `overlaps` 가 이것을 쓴다(동작 불변).
  - `reserve.free_spans(s, room_id, date, lo: int) -> list[tuple[int, int]]` (분)
  - `reserve.free_days(s, room_id, now_local: dt.datetime, full: bool) -> list[dict]` — 항상 8개 `{"date": date, "spans": [{"from", "to"}]}`. `full` 은 호출자가 `room_full` 로 한 번 계산해 넘긴다(같은 값을 `WeekOut.full` 로도 싣는다).
  - `S.FreeDay{date: dt.date, spans: list[FreeRange]}`, `S.WeekOut.free: list[FreeDay] = []`, `S.WeekOut.full: bool = False`

규칙(spec A3 + S10 §2.4 + `student-room.md` 예약 §화면이 거는 제약):
- 날짜 = KST 오늘 ~ +7 (8개, 날짜 칩과 같다). `?date=` 와 무관하다.
- 범위 = 운영 시간 09:00~21:00. 오늘은 **지금 이후** — 시작 > 지금이어야 하므로 하한은 `지금(분) + 1` 을 5분 올림.
- 빼는 것 = `reserve.overlaps` 와 **같은 목록**(`_blockers`): 슬롯(type 무관, 빈강의실 4 포함) + `approved` + `requested`(내 것 포함). 슬롯 없는 시험기간·`cancelled`·`rejected`·`expired` 는 빼지 않는다.
- 끝점은 5분 격자 **안쪽**으로(시작 올림, 끝 내림), 15분(`MIN_MIN`) 미만 조각은 버린다 — 남은 구간 안에서 고른 신청은 겹침·길이·격자·과거 검사를 통과한다. 120분 상한은 화면이 끝 시각 목록에서 건다.
- 방이 노드 용량(24)만큼 찼으면(`room_full` — 신청 검사와 같은 규칙: 창 안 approved+requested) `full: true` 이고 모든 날이 빈 목록 — 어디를 골라도 409 다. 화면은 `full` 로 "예약이 가득 찼어요"를 말한다.
- 남는 경합(목록을 보는 사이 남이 먼저 신청)은 여전히 409 — 화면이 Toast + 재조회(spec §4.1).

- [ ] **Step 1: 실패 테스트**

`server/tests/test_student_rooms.py` 상단 import 한 줄을 바꾼다
```python
from app.domain import clock, reserve
```
파일 끝에 추가
```python
def test_week_free_spans_match_what_request_accepts(client, app, school, student_hdr, monkeypatch):
    _fix_clock(monkeypatch)  # KST 수 9/23 10:30
    _, ids = _building(app, 1, "E")
    rid = ids[101]
    _slot(app, rid, 3, 13, 0, 14, 0)  # 수 — 오늘과 다음 주 수요일
    _slot(app, rid, 4, 9, 0, 12, 0, type=4, subject="빈강의실")  # type 무관하게 신청을 막는다
    fri = dt.date(2026, 9, 25)
    _resv(app, rid, fri, 15, 0, 16, 0, id_=1, status="requested", requested_by="s2@mju.ac.kr")
    _resv(app, rid, fri, 17, 0, 18, 0, id_=2, status="cancelled")  # 취소는 막지 않는다
    _slot(app, rid, 6, 9, 0, 10, 2)  # 토 — 끝이 5분 격자 밖
    _slot(app, rid, 6, 10, 12, 11, 0)  # 틈 10:02~10:12 → 격자 안쪽 10:05~10:10 = 5분 < 15분 → 버림
    _slot(app, rid, 7, 7, 0, 9, 30)  # 일 — 운영 시작 전부터
    _slot(app, rid, 1, 20, 0, 22, 0)  # 월 — 운영 끝 뒤까지
    # 화 — 슬롯 없는 시험기간은 신청을 막지 않는다 (reserve.overlaps 와 같다)
    _exam(app, rid, 1, dt.date(2026, 9, 29), dt.date(2026, 9, 29))
    url = f"/api/student/rooms/{rid}/week"

    def free():
        j = client.get(url, headers=student_hdr).json()
        return [(d["date"], [(x["from"], x["to"]) for x in d["spans"]]) for d in j["free"]]

    assert free() == [
        ("2026-09-23", [("10:35", "13:00"), ("14:00", "21:00")]),  # 10:30 지남 → 10:31 뒤 첫 5분
        ("2026-09-24", [("12:00", "21:00")]),
        ("2026-09-25", [("09:00", "15:00"), ("16:00", "21:00")]),  # 남의 신청도 막는다
        ("2026-09-26", [("11:00", "21:00")]),
        ("2026-09-27", [("09:30", "21:00")]),
        ("2026-09-28", [("09:00", "20:00")]),
        ("2026-09-29", [("09:00", "21:00")]),
        ("2026-09-30", [("09:00", "13:00"), ("14:00", "21:00")]),
    ]
    # free 의 경계가 곧 신청이 받아들이는 경계다
    post = f"/api/student/rooms/{rid}/reservations"
    body = {"date": "2026-09-25", "subject": "스터디"}
    t1 = {"s_h": 15, "s_m": 55, "e_h": 16, "e_m": 10}
    t2 = {"s_h": 16, "s_m": 0, "e_h": 16, "e_m": 15}
    assert client.post(post, json=body | t1, headers=student_hdr).status_code == 409
    assert client.post(post, json=body | t2, headers=student_hdr).status_code == 201
    assert free()[2] == ("2026-09-25", [("09:00", "15:00"), ("16:15", "21:00")])  # 내 신청도 뺀다
    # 다른 주를 봐도 free 는 오늘~+7 그대로
    j = client.get(f"{url}?date=2026-10-20", headers=student_hdr).json()
    assert j["week_start"] == "2026-10-19" and j["free"][0]["date"] == "2026-09-23"
    assert j["full"] is False


def test_week_free_uses_kst_today_and_operating_hours(
    client, app, school, student_hdr, monkeypatch
):
    _, ids = _building(app, 1, "E")
    url = f"/api/student/rooms/{ids[101]}/week"

    def at(utc):
        monkeypatch.setattr(clock, "now_utc", lambda: utc)
        return client.get(url, headers=student_hdr).json()["free"]

    j = at(dt.datetime(2026, 9, 23, 15, 10))  # noqa: DTZ001 — KST 9/24(목) 00:10
    assert [d["date"] for d in j] == [
        str(dt.date(2026, 9, 24) + dt.timedelta(days=i)) for i in range(8)
    ]
    assert j[0]["spans"] == [{"from": "09:00", "to": "21:00"}]  # 새벽 — 운영 시작부터
    j = at(dt.datetime(2026, 9, 23, 11, 40))  # noqa: DTZ001 — KST 20:40
    assert j[0]["spans"] == [{"from": "20:45", "to": "21:00"}]  # 딱 15분
    j = at(dt.datetime(2026, 9, 23, 11, 50))  # noqa: DTZ001 — KST 20:50
    assert j[0] == {"date": "2026-09-23", "spans": []}  # 20:55~21:00 은 15분 미만
    assert j[1]["spans"] == [{"from": "09:00", "to": "21:00"}]


def test_week_full_flag_empties_free(client, app, school, student_hdr, monkeypatch):
    _fix_clock(monkeypatch)
    monkeypatch.setattr(reserve, "NODE_RESV_MAX", 1)  # 창 안 1건이면 가득 — 신청은 409
    _, ids = _building(app, 1, "E")
    _resv(app, ids[101], dt.date(2026, 9, 26), 9, 0, 10, 0, id_=1)
    j = client.get(f"/api/student/rooms/{ids[101]}/week", headers=student_hdr).json()
    assert j["full"] is True  # 화면은 '예약이 가득 찼어요' — '빈 시간 없음' 이 아니라
    assert len(j["free"]) == 8 and all(d["spans"] == [] for d in j["free"])
```

- [ ] **Step 2: 실패 확인**

Run: `cd server && uv run pytest -q tests/test_student_rooms.py`
Expected: FAIL 3개 — 모두 `KeyError: 'free'`

- [ ] **Step 3: 구현**

`server/app/schemas.py`
- `class BusyDay` 다음에 추가
```python
class FreeDay(BaseModel):
    date: dt.date
    spans: list[FreeRange]
```
- `WeekOut` 의 `busy` 줄 다음에 추가
```python
    # web A3 — KST 오늘~+7 신청 가능 구간 (reserve.free_days). date 파라미터와 무관
    free: list[FreeDay] = []
    # web A3 — 창(오늘~+7) 안 approved+requested 가 노드 용량(24)에 찼다 (reserve.room_full). 그러면 free 는 전부 빈 목록
    full: bool = False
```

`server/app/domain/reserve.py`
- import 한 줄을 바꾼다
```python
from app.domain import clock, room_state
```
- `MIN_MIN, MAX_MIN = 15, 120` 다음에 추가
```python
OPEN_MIN, CLOSE_MIN = 9 * 60, 21 * 60  # 운영 시간 KST (S10 §2.6) — analytics 도 이 값을 쓴다
STEP_MIN = 5  # StudentResvIn 의 s_m·e_m multiple_of=5
```
- 기존 `def overlaps(...)` 전체를 아래로 바꾼다(`_hit` 은 그대로 둔다)
```python
def _blockers(s: Session, room_id: int, date: dt.date, exclude_id: int | None = None) -> list:
    """겹침 판정 대상 — 그 요일 정규 슬롯(type 무관) + 그 날 approved/requested 예약.
    overlaps 와 free_spans 가 같은 목록을 본다: 빈 구간으로 보여준 곳이 겹침 409 가 나지 않게."""
    q = select(Reservation).where(
        Reservation.room_id == room_id,
        Reservation.date == date,
        Reservation.status.in_(_LIVE),
    )
    if exclude_id is not None:
        q = q.where(Reservation.id != exclude_id)
    slots = s.scalars(select(Slot).where(Slot.room_id == room_id, Slot.day == date.isoweekday()))
    return [*slots, *s.scalars(q)]


def overlaps(
    s: Session, room_id: int, date: dt.date, s_min: int, e_min: int, exclude_id: int | None = None
) -> bool:
    """정규 슬롯(그 요일, type 무관)·approved/requested 예약과 1분이라도 겹치면 True.
    시험기간은 슬롯이 있을 때만 의미가 있어 슬롯 겹침에 이미 포함된다."""
    return any(_hit(x, s_min, e_min) for x in _blockers(s, room_id, date, exclude_id))


def free_spans(s: Session, room_id: int, date: dt.date, lo: int) -> list[tuple[int, int]]:
    """[lo, CLOSE_MIN] 안에서 _blockers 의 여집합 (분). 끝점은 5분 격자 안쪽으로 맞추고
    MIN_MIN 보다 짧은 조각은 버린다 — 남은 구간 안의 신청은 겹침·길이·격자 검사를 통과한다."""
    gaps, cur = [], lo
    for a, b in sorted(
        (x.s_h * 60 + x.s_m, x.e_h * 60 + x.e_m) for x in _blockers(s, room_id, date)
    ):
        if b <= a:
            continue  # ponytail: 관리자 입력엔 시작<끝 검증이 없다 — merge_busy 와 같이 무시
        if a > cur:
            gaps.append((cur, a))
        cur = max(cur, b)
    gaps.append((cur, CLOSE_MIN))
    out = []
    for a, b in gaps:
        a, b = -(-a // STEP_MIN) * STEP_MIN, min(b, CLOSE_MIN) // STEP_MIN * STEP_MIN
        if b - a >= MIN_MIN:
            out.append((a, b))
    return out


def free_days(s: Session, room_id: int, now_local: dt.datetime, full: bool) -> list[dict]:
    """예약 화면의 날짜 칩 8개(KST 오늘~+7)와 날마다 신청 가능한 구간 (web A3).
    오늘은 지금 이후만(시작 > 지금). full(= room_full, 호출자가 WeekOut.full 로도 싣는다)이면 전부
    빈 목록 — 신청해도 409 라서."""
    today = now_local.date()
    out = []
    for i in range(RESV_HORIZON_DAYS + 1):  # ponytail: 날마다 쿼리 2개(16개) — 느려지면 범위 조회로
        d = today + dt.timedelta(days=i)
        lo = OPEN_MIN if i else max(OPEN_MIN, now_local.hour * 60 + now_local.minute + 1)
        spans = [] if full else free_spans(s, room_id, d, lo)
        out.append(
            {
                "date": d,
                "spans": [
                    {"from": room_state.fmt_hhmm(a), "to": room_state.fmt_hhmm(b)} for a, b in spans
                ],
            }
        )
    return out
```

`server/app/domain/analytics.py` — 상수 한 줄을 바꾼다(`reserve` 는 이미 import 돼 있다)
```python
OPEN_MIN, CLOSE_MIN = reserve.OPEN_MIN, reserve.CLOSE_MIN  # 운영 시간은 한 곳 (web A3 free)
```

`server/app/domain/student_router.py` (`reserve` 는 이미 import 돼 있다)
- `week` 첫 줄 `room, b = _student_room(s, user, id)` 다음에 추가
```python
    now = clock.local_now()
    full = reserve.room_full(s, id, now.date())  # 신청 검사와 같은 규칙 — 창 안 live 24건
```
- `return {...}` 에서 Task 3 의 `"busy"` 줄 다음에 추가
```python
        "free": reserve.free_days(s, id, now, full),
        "full": full,
```

- [ ] **Step 4: 통과 확인**

Run: `cd server && uv run pytest -q && uv run ruff check . && uv run ruff format --check .`
Expected: 전부 PASS(기존 xfail 2개 그대로 — `overlaps` 리팩터 뒤에도 `test_student_resv`·`test_admin_resv` 의 겹침 409 가 그대로), `All checks passed!`

- [ ] **Step 5: 커밋**

```bash
git add server/app/schemas.py server/app/domain/reserve.py server/app/domain/analytics.py server/app/domain/student_router.py server/tests/test_student_rooms.py
git commit -m "feat(server): WeekOut.free·full — 신청 검사와 같은 기준의 오늘~+7 빈 구간과 가득 참 (web A3)"
```

---

## PR 체크리스트

- 브랜치 `feature/web-server-additive`. 베이스는 `main` — 단 `feature/s10-student`(S10 PR)가 아직 머지 전이면 그 PR 이 먼저 머지될 때까지 **draft** 로 두고 베이스를 `feature/s10-student` 로 연다(머지 뒤 베이스만 `main` 으로 바꾼다. rebase·force push 하지 않는다).
- 제목 `feat(server): 웹 선행 additive A1~A3 — 거절 사유, 예약 신청자·pushed_at, 주간 busy·free`.
- 본문: `uv run pytest -q`·`ruff check`·`ruff format --check` 결과, 필드 표(아래), "기존 필드 불변 — additive" 명시, 동작 변경 둘(방 단위 예약 정렬, `week?date` 상한 422).

| 응답 | 추가 필드 |
|---|---|
| `UserOut` | `reject_reason: str \| null` (rejected 행에만 값) |
| `ResvWithRoom` (`/api/buildings/{id}/reservations`, `/api/rooms/{id}/reservations`) | `requester: {email, name, student_no} \| null`, `pushed_at: datetime \| null` (방 단위는 `room_id` 도) |
| `ResvAdminOut` (`/api/admin/reservations`, 승인·거절·취소) | `pushed_at: datetime \| null` |
| `WeekOut` (`/api/student/rooms/{id}/week`) | `busy: [{day, spans: [{from, to, label, type, mine, status}]}]`(7개, `status` 는 내 것만 `requested` 또는 `approved`), `free: [{date, spans: [{from, to}]}]`(8개), `full: bool` |

- 리뷰어: cw(@ssenu) — `server/lora_service/` 는 건드리지 않았다(필수 리뷰 계층 아님). 웹 F1·F2·F4 plan 의 `api/types.ts` 가 이 표를 그대로 옮긴다.

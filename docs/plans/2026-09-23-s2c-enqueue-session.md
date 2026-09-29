# S2c — `api.enqueue_*(session=)` 원자화 구현 계획 (plan, 이슈 #9)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

- 생성일시: 2026-09-23
- 기준: 이슈 #9 (PR #5 리뷰 Minor). spec 없음 — bounded 변경, 설계는 이슈 본문 + 이 plan. 도메인·outbox 규칙은 `docs/specs/2026-09-14-s2-server-design.md` §2.3.
- 담당: wj @leemonta9482. 브랜치 `feature/enqueue-session`. 커밋 scope `feat(server)`. `lora_service/api.py` 시그니처 변경 → **cw 필수 리뷰**. PR은 사용자 지시 시. **순서: S4a → S2c → S4b → S10 고정**(S4b·S10 라우터가 이 시그니처를 쓴다. S10 approve·cancel 은 이것 없이는 `database is locked` — PR #38 리뷰 🔴5).
- 개정: r2 (PR #38 리뷰 — 커밋 뒤 직접 notify, 원자성 테스트 정정).

**Goal:** 슬롯·예약·시험·CMD 변경에서 버전 +1·outbox 삽입·도메인 write 가 **한 트랜잭션**이 되어, 도메인 write 실패 시 outbox 행이 남지 않는다. "enqueue 먼저" 순서 제약과 그 주석을 없앤다.

**Architecture:** `api._enqueue` 가 선택 인자 `session` 을 받으면 자기 세션을 열지 않고 그 세션 안에서 버전·outbox 를 쓰고 **커밋·notify 를 하지 않는다**. 공개 `enqueue_*` 8개는 `session` 을 그대로 넘긴다. 라우터는 `session=s` 로 부르고 **핸들러에서 `s.commit()` 한 뒤** `api.notify(modem_id)` 를 직접 부른다(`_commit_notify`). BackgroundTasks 는 get_db 커밋 전에 돌아 쓰지 않는다. 기존 호출자(허브·재동기·CSV·일일 작업)는 인자 없이 종전 동작.

**Tech Stack:** Python 3.12 · FastAPI 0.141 · SQLAlchemy 2 · pytest · ruff

## Global Constraints

- `session` 은 키워드 전용·기본 `None`(additive). `None` 이면 종전과 동일(자체 세션·커밋·`_hub.notify`).
- `session` 모드: `_bump_ver`·`C.encode_payload`·`_insert` 를 그 세션에서, `flush` 까지만. 커밋·notify 없음. 반환값 동일(`list[int]` outbox ids — `flush` 로 id 확보).
- 신규 `api.notify(modem_id: str | None) -> None`: `None` 이면 no-op, 아니면 `_hub.notify`(루프 스레드로 넘기는 `call_soon_threadsafe` 라 threadpool 에서 불러도 안전). 라우터가 커밋 뒤 직접 호출.
- `enqueue_full_sync`·`enqueue_file_replace`·`provision`·`reassign_queued` 는 변경 없음(RecordProvider 가 커밋된 DB 를 읽어야 하거나 호출자가 다름).
- 라우터: `put_slot`·`delete_slot`·`clear_day`·`put_resv`·`delete_resv`·`put_exam`·`delete_exam`·`cmd_room` 이 `session=s` + `_commit_notify`. `sync_room`·`import_slots` 는 그대로. S10 `reserve.approve/cancel` 도 `session=s` 로 쓴다(S10 plan T3).
- `lora_proto/`·`hub.py` 불변. 기존 테스트 그대로 통과.
- uv only; ruff 100/py312; 명령은 `server/`. 커밋 `feat(server): ...`, AI 표기 없음.

---

### Task 1: `api._enqueue(session=)` · `enqueue_*` 패스스루 · `api.notify`

**Files:**
- Modify: `server/app/lora_service/api.py`
- Test: `server/tests/test_api_enqueue.py`

**Interfaces:**
- Produces: `enqueue_slot_set(..., unit=0, *, session: Session | None = None)`(나머지 7개 동일 형태), `api.notify(modem_id: str | None) -> None`.

- [ ] **Step 1: 실패 테스트**

`server/tests/test_api_enqueue.py` 끝에:

```python
def test_enqueue_with_session_is_atomic_and_silent(db, hub):
    """session 모드: 호출자 트랜잭션 안에서 버전·outbox 를 쓰고 커밋·notify 는 하지 않는다."""
    with db() as s, s.begin():
        ids = api.enqueue_slot_set("E", 301, 1, (9, 0), (10, 0), 1, "a", "b", session=s)
        assert len(ids) == 2 and hub.notified == []  # flush 로 id 는 있고, notify 는 없음
        assert s.get(RoomVersion, ("E", 301, "schedule")).ver == 1
    assert [r.id for r in _rows(db)] == ids and hub.notified == []
    api.notify("m1")
    assert hub.notified == ["m1"]
    api.notify(None)
    assert hub.notified == ["m1"]


def test_enqueue_with_session_rolls_back_with_caller(db, hub):
    with pytest.raises(RuntimeError), db() as s, s.begin():
        api.enqueue_slot_set("E", 301, 1, (9, 0), (10, 0), 1, "a", "b", session=s)
        raise RuntimeError("domain write failed")
    assert _rows(db) == []
    with db() as s:
        assert s.get(RoomVersion, ("E", 301, "schedule")) is None  # 버전도 롤백


def test_enqueue_without_session_unchanged(db, hub):
    ids = api.enqueue_resv_del("E", 302, 7)
    assert len(ids) == 1 and hub.notified == ["m1"]


@pytest.mark.parametrize(
    "fn,args",
    [
        (api.enqueue_slot_del, ("E", 301, 1, (9, 0))),
        (api.enqueue_day_clear, ("E", 301, 1)),
        (api.enqueue_resv_set, ("E", 301, 7, dt.date(2026, 9, 24), (9, 0), (10, 0), 6, "r", "")),
        (api.enqueue_resv_del, ("E", 301, 7)),
        (api.enqueue_exam_set, ("E", 301, 3, dt.date(2026, 10, 19), dt.date(2026, 10, 23))),
        (api.enqueue_exam_del, ("E", 301, 3)),
        (api.enqueue_cmd, ("E", 301, 4, b"")),
    ],
)
def test_all_enqueue_accept_session(db, hub, fn, args):
    with db() as s, s.begin():
        assert len(fn(*args, session=s)) == 2
    assert hub.notified == []
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_api_enqueue.py -k session -q` → FAIL (`TypeError: unexpected keyword 'session'`)

- [ ] **Step 3: 구현**

`api.py` `_enqueue`:

```python
def _enqueue(
    bld: str,
    room: int,
    unit: int,
    type_: str,
    make: Callable[[int | None], object],
    session: Session | None = None,
) -> list[int]:
    """버전 +1 → codec 객체 생성·인코딩(검증) → outbox 삽입. 전부 한 트랜잭션.
    `session` 이 주어지면 그 안에서 flush 까지만 — 커밋·notify 는 호출자 몫(#9 원자화).
    호출자는 커밋 뒤 `notify(modem_id)` 를 불러야 허브가 새 작업을 본다."""
    info = _room(bld, room)

    def body(s: Session) -> list[int]:
        kind = KIND_OF.get(type_)
        new_ver = _bump_ver(s, bld, room, kind) if kind else None
        obj = make(new_ver)
        try:
            C.encode_payload(obj)  # 실패면 여기서 롤백 — 모뎀Pi의 bad_payload 를 서버에서 막는다
        except C.FrameError as e:
            raise ValidationError(str(e)) from e
        return _insert(s, info, bld, room, unit, type_, _to_json(obj), new_ver)

    if session is not None:
        return body(session)
    with _Session() as s, s.begin():
        ids = body(s)
    if info.modem_id:
        _hub.notify(info.modem_id)
    return ids


def notify(modem_id: str | None) -> None:
    """라우터가 s.commit() 한 뒤 직접 부른다 (session 모드의 짝). _hub.notify 는 call_soon_threadsafe 라 threadpool 에서도 안전."""
    if modem_id:
        _hub.notify(modem_id)
```

공개 8개(`enqueue_slot_set`, `enqueue_slot_del`, `enqueue_day_clear`, `enqueue_resv_set`, `enqueue_resv_del`, `enqueue_exam_set`, `enqueue_exam_del`, `enqueue_cmd`)에 `*, session: Session | None = None` 을 마지막 인자로 추가하고 `_enqueue(..., session=session)` 으로 넘긴다. 예:

```python
def enqueue_slot_del(
    bld: str, room: int, day: int, start: tuple[int, int], unit: int = 0, *, session: Session | None = None
) -> list[int]:
    return _enqueue(bld, room, unit, "SLOT_DEL", lambda v: C.SlotDel(v, day, start[0], start[1]), session)
```

- [ ] **Step 4: 통과·커밋**

Run: `uv run pytest -q` → PASS. ruff.

```bash
git add app/lora_service/api.py tests/test_api_enqueue.py
git commit -m "feat(server): api.enqueue_*(session=) — 호출자 트랜잭션 안에서 버전·outbox, api.notify 분리 (#9)"
```

---

### Task 2: 라우터 한 트랜잭션 + 커밋 뒤 notify + "enqueue 먼저" 제거

**Files:**
- Modify: `server/app/domain/router.py`
- Test: `server/tests/test_domain.py`

**Interfaces:**
- Produces: `_addr(s, room_id, user) -> tuple[str, int, str | None]`(bld, room, modem_id), `_commit_notify(s, modem_id)`. S4b T2·S10 T3 이 이 둘을 쓴다.

- [ ] **Step 1: 실패 테스트**

`server/tests/test_domain.py` 끝에 (`from app.lora_service import api`, `from app.lora_service.models import Outbox, RoomVersion` 가 없으면 추가):

```python
SLOT = {"day": 1, "s_h": 9, "s_m": 0, "e_h": 10, "e_m": 50, "type": 1, "subject": "a", "professor": ""}


def test_slot_put_is_atomic_with_outbox(client, app, monkeypatch):
    """enqueue 뒤 요청이 실패하면 outbox 행·버전 증가도 롤백된다 (#9).
    enqueue 를 감싸 호출 직후 예외 — 구현 전(자체 세션 커밋)이면 outbox 행이 남아 FAIL."""
    _sch, _b, r = _setup(client)
    real = api.enqueue_slot_set

    def boom(*a, **k):
        real(*a, **k)
        raise RuntimeError("domain write failed after enqueue")

    monkeypatch.setattr(api, "enqueue_slot_set", boom)
    with TestClient(app, headers=client.headers, raise_server_exceptions=False) as c:
        assert c.put(f"/api/rooms/{r['id']}/slots", json=SLOT).status_code == 500
    with app.state.Session() as s:
        assert s.scalars(select(Outbox)).all() == []
        assert s.get(RoomVersion, ("E", 301, "schedule")) is None
        assert s.scalars(select(Slot)).all() == []


def test_notify_runs_after_commit(client, app, monkeypatch):
    """허브 알림 시점에 outbox 행이 이미 커밋돼 있어야 한다 — 아니면 허브가 못 보고 5 s sweep 까지 늦는다."""
    _sch, _b, r = _setup(client)
    seen = []

    def spy(mid):
        with app.state.Session() as s:  # 새 세션 — 커밋된 것만 보인다
            seen.append(len(s.scalars(select(Outbox)).all()))

    monkeypatch.setattr(api, "notify", spy)
    assert client.put(f"/api/rooms/{r['id']}/slots", json=SLOT).status_code == 200
    assert seen and seen[0] == 2  # 유닛 2 행이 커밋된 뒤 알림
```

(`from fastapi.testclient import TestClient`. `_setup` 의 방은 units=2, 건물 modem 없음 → `notify(None)` 도 호출되는지 확인하려면 spy 가 인자와 무관하게 기록한다.)

- [ ] **Step 2: 실패 확인** → 첫 테스트는 outbox 행이 남아 FAIL, 두 번째는 `api.notify` 가 없어 FAIL

- [ ] **Step 3: 라우터**

`server/app/domain/router.py`:
- `# 참고: 도메인·outbox 두 세션. …` 주석 블록(put_slot 위) 삭제. 대신: `# 버전·outbox·도메인 write 는 같은 세션(#9). 핸들러가 커밋한 뒤 허브에 알린다 — BackgroundTasks 는 get_db 커밋 전에 돌므로 쓰지 않는다.`
- 헬퍼:

```python
def _addr(s: Session, room_id: int, user: User) -> tuple[str, int, str | None]:
    r = scope.get_scoped(s, Room, room_id, user.school_id)
    b = s.get(Building, r.building_id)
    return b.bld, r.room, b.modem_id


def _commit_notify(s: Session, modem_id: str | None) -> None:
    """커밋을 먼저 끝내고 허브를 깨운다 — 허브가 새 outbox 행을 바로 본다 (#9)."""
    s.commit()
    api.notify(modem_id)
```

- 8개 핸들러(`put_slot`·`delete_slot`·`clear_day`·`put_resv`·`delete_resv`·`put_exam`·`delete_exam`·`cmd_room`): `bld, room, mid = _addr(s, id, user)` → 도메인 write → `api.enqueue_*(..., session=s)` → `_commit_notify(s, mid)` → return. 도메인 write 와 enqueue 순서는 이제 무관 — 읽기 쉬운 순서(도메인 → enqueue).
- `put_resv`·`put_exam` 은 이 시점의 S2 버전(클라이언트 id upsert). 채번·같은 방 가드는 S4b T2 가 이 코드 위에 얹는다.
- `sync_room` 은 `bld, room, _ = _addr(...)` 로 갱신(동작 불변).

예 `delete_slot`:

```python
@router.delete("/rooms/{id}/slots/{day}/{s_h}/{s_m}", response_model=S.Enqueued)
def delete_slot(id: int, day: int, s_h: int, s_m: int, user: User = AdminUser, s: Session = _DB):
    bld, room, mid = _addr(s, id, user)
    s.execute(delete(Slot).where(Slot.room_id == id, Slot.day == day, Slot.s_h == s_h, Slot.s_m == s_m))
    ids = api.enqueue_slot_del(bld, room, day, (s_h, s_m), session=s)
    _commit_notify(s, mid)
    return {"outbox_ids": ids}
```

- [ ] **Step 4: 통과·커밋**

Run: `uv run pytest -q` → PASS(허브 테스트 `test_hello_sends_config_then_queued_jobs` 등은 `api.enqueue_*` 직접 호출이라 불변). ruff.

```bash
git add app/domain/router.py tests/test_domain.py
git commit -m "feat(server): 도메인 REST 변경을 outbox 와 한 트랜잭션으로 — enqueue(session=s), 커밋 뒤 notify (#9)"
```

---

## Self-review

- **이슈 커버리지:** "선택 `session=` 으로 한 트랜잭션" → T1·T2. "`# 참고:` 주석 제거" → T2. 기존 호출자 불변 → T1 `test_enqueue_without_session_unchanged`.
- **리뷰(PR #38) 반영:** 원자성 테스트는 enqueue 를 감싸 예외 — 구현 전엔 반드시 실패(autoflush 로 우연히 통과하던 문제 제거). 알림은 BackgroundTasks 가 아니라 **핸들러의 `s.commit()` 뒤 직접 호출**(BackgroundTasks 는 get_db 커밋 전에 돈다 — 실측) + `test_notify_runs_after_commit`.
- **Placeholder:** 없음.
- **Type consistency:** `session` 키워드 8개 = T2 호출. `api.notify(modem_id | None)` T1 = T2 `_commit_notify`. `_addr` 3-튜플·`_commit_notify` = S4b T2·S10 T3 사용. 순서 **S4a → S2c → S4b → S10** 고정.

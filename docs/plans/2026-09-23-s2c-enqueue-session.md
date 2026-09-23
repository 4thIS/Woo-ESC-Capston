# S2c — `api.enqueue_*(session=)` 원자화 구현 계획 (plan, 이슈 #9)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

- 생성일시: 2026-09-23
- 기준: 이슈 #9 (PR #5 리뷰 Minor). spec 없음 — bounded 변경, 설계는 이슈 본문 + 이 plan. 도메인·outbox 규칙은 `docs/specs/2026-09-14-s2-server-design.md` §2.3.
- 담당: wj @leemonta9482. 브랜치 `feature/enqueue-session`. 커밋 scope `feat(server)`. `lora_service/api.py` 시그니처 변경 → **cw 필수 리뷰**. PR은 사용자 지시 시. **순서: S4a 뒤, S4b 앞**(S4b·S10 라우터가 이 시그니처를 쓰도록).

**Goal:** 슬롯·예약·시험·CMD 변경에서 버전 +1·outbox 삽입·도메인 write 가 **한 트랜잭션**이 되어, 도메인 write 실패 시 outbox 행이 남지 않는다. "enqueue 먼저" 순서 제약과 그 주석을 없앤다.

**Architecture:** `api._enqueue` 가 선택 인자 `session` 을 받으면 자기 세션을 열지 않고 그 세션 안에서 버전·outbox 를 쓰고 **커밋·notify 를 하지 않는다**. 공개 `enqueue_*` 8개는 `session` 을 그대로 넘긴다. 라우터는 `session=s` 로 부르고 `BackgroundTasks` 로 커밋 뒤 `api.notify(modem_id)`. 기존 호출자(허브·재동기·CSV·일일 작업)는 인자 없이 종전 동작.

**Tech Stack:** Python 3.12 · FastAPI 0.141 · SQLAlchemy 2 · pytest · ruff

## Global Constraints

- `session` 은 키워드 전용·기본 `None`(additive). `None` 이면 종전과 동일(자체 세션·커밋·`_hub.notify`).
- `session` 모드: `_bump_ver`·`C.encode_payload`·`_insert` 를 그 세션에서, `flush` 까지만. 커밋·notify 없음. 반환값 동일(`list[int]` outbox ids — `flush` 로 id 확보).
- 신규 `api.notify(modem_id: str | None) -> None`: `None` 이면 no-op, 아니면 `_hub.notify`. 라우터가 `bg.add_task(api.notify, mid)`.
- `enqueue_full_sync`·`enqueue_file_replace`·`provision`·`reassign_queued` 는 변경 없음(RecordProvider 가 커밋된 DB 를 읽어야 하거나 호출자가 다름).
- 라우터: `put_slot`·`delete_slot`·`clear_day`·`put_resv`·`delete_resv`·`put_exam`·`delete_exam`·`cmd_room` 이 `session=s` + bg notify. `sync_room`·`import_slots` 는 그대로. S10 `reserve.approve/cancel` 은 이 plan 뒤에 `session=s` 로 바꾼다(S10 plan T3 주석).
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
    """라우터가 커밋 뒤 BackgroundTasks 로 부른다 (session 모드의 짝)."""
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

### Task 2: 라우터 한 트랜잭션 + bg notify + "enqueue 먼저" 제거

**Files:**
- Modify: `server/app/domain/router.py`
- Test: `server/tests/test_domain.py`

- [ ] **Step 1: 실패 테스트**

`server/tests/test_domain.py` 끝에:

```python
def test_slot_put_is_atomic_with_outbox(client, app, monkeypatch):
    """도메인 write 가 실패하면 outbox 행·버전 증가도 없다 (#9)."""
    from sqlalchemy.orm import Session as _S

    _sch, _b, r = _setup(client)
    body = {"day": 1, "s_h": 9, "s_m": 0, "e_h": 10, "e_m": 50, "type": 1, "subject": "a", "professor": ""}
    real_flush = _S.flush
    calls = {"n": 0}

    def boom(self, *a, **k):
        calls["n"] += 1
        if calls["n"] == 2:  # 1: _insert 의 flush(outbox), 2: 라우터의 도메인 flush → 실패
            raise RuntimeError("domain write failed")
        return real_flush(self, *a, **k)

    monkeypatch.setattr(_S, "flush", boom)
    with TestClient(app, headers=client.headers, raise_server_exceptions=False) as c:
        assert c.put(f"/api/rooms/{r['id']}/slots", json=body).status_code == 500
    monkeypatch.setattr(_S, "flush", real_flush)
    with app.state.Session() as s:
        assert s.scalars(select(Outbox)).all() == [] and s.get(RoomVersion, ("E", 301, "schedule")) is None
        assert s.scalars(select(Slot)).all() == []
    # 정상 경로: 커밋 뒤 notify 가 허브에 닿는다 (SpyHub 가 아닌 실제 허브 — notified 대신 outbox dispatched 흐름은 test_hub 에서)
    assert client.put(f"/api/rooms/{r['id']}/slots", json=body).status_code == 200
```

(`from fastapi.testclient import TestClient`, `from app.lora_service.models import Outbox, RoomVersion`.) `flush` 호출 순서(1: outbox `_insert`, 2: 도메인)는 구현 뒤 확인해 `calls["n"]` 임계값을 맞춘다 — 목적은 "도메인 flush 실패 → 둘 다 롤백".

- [ ] **Step 2: 실패 확인** → 현재는 outbox 가 이미 커밋돼 `_rows != []` 로 FAIL

- [ ] **Step 3: 라우터**

`server/app/domain/router.py`:
- `# 참고: 도메인·outbox 두 세션. …` 주석 블록(put_slot 위) 삭제. 대신 한 줄: `# 버전·outbox·도메인 write 는 같은 세션(#9). 커밋은 get_db teardown, 허브 알림은 커밋 뒤 BackgroundTasks.`
- 8개 핸들러에 `bg: BackgroundTasks` 인자 추가, `api.enqueue_*(..., session=s)`, 끝에 `bg.add_task(api.notify, _modem_of(s, room_obj.building_id))`. `_addr` 가 `(bld, room)` 만 주므로 `_addr` 를 `(bld, room, modem_id)` 3-튜플로 바꾸고(S4a 의 `_addr(s, room_id, user)`) 호출부 갱신.
- `put_slot`: 도메인 write(`s.add`/setattr) 와 enqueue 순서는 이제 무관 — 읽기 쉬운 순서(도메인 → enqueue)로.
- `put_resv`·`put_exam`(S4b 채번 포함): 동일.

예 `delete_slot`:

```python
@router.delete("/rooms/{id}/slots/{day}/{s_h}/{s_m}", response_model=S.Enqueued)
def delete_slot(id: int, day: int, s_h: int, s_m: int, bg: BackgroundTasks, user: User = AdminUser, s: Session = _DB):
    bld, room, mid = _addr(s, id, user)
    s.execute(delete(Slot).where(Slot.room_id == id, Slot.day == day, Slot.s_h == s_h, Slot.s_m == s_m))
    ids = api.enqueue_slot_del(bld, room, day, (s_h, s_m), session=s)
    bg.add_task(api.notify, mid)
    return {"outbox_ids": ids}
```

- [ ] **Step 4: 통과·커밋**

Run: `uv run pytest -q` → PASS(허브 테스트 `test_hello_sends_config_then_queued_jobs` 등은 `api.enqueue_*` 직접 호출이라 불변). ruff.

```bash
git add app/domain/router.py tests/test_domain.py
git commit -m "feat(server): 도메인 REST 변경을 outbox 와 한 트랜잭션으로 — enqueue(session=s) + 커밋 뒤 notify (#9)"
```

---

## Self-review

- **이슈 커버리지:** "선택 `session=` 으로 한 트랜잭션" → T1·T2. "`# 참고:` 주석 제거" → T2. 기존 호출자 불변 → T1 `test_enqueue_without_session_unchanged`.
- **Placeholder:** T2 의 `calls["n"]` 임계값은 구현 순서에 따라 확인하라고 명시(테스트 목적은 고정). 그 외 없음.
- **Type consistency:** `session` 키워드 8개 = T2 호출. `api.notify(modem_id | None)` T1 = T2 `bg.add_task`. `_addr` 3-튜플 변경은 S4a 이후 시그니처(`_addr(s, room_id, user)`) 위에 얹는다 — S10 `reserve._addr` 는 별도 함수라 무관.

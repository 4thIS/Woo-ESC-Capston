# 학생 조기 퇴실 — 구현 계획 (plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 체크인한 학생이 예약 진행 중에 조기 퇴실하면 끝 시각이 퇴실 분으로 당겨지고, 문 앞 노드에서 예약이 지워지며, 남은 시간이 바로 빈 강의실·예약 가능 구간이 된다.

**Architecture:** 서버는 `reservations.checked_out_at` 컬럼을 더하고 `reserve.checkout()` 이 `e_h`·`e_m` 을 max(퇴실 분, 시작+1분)으로 당긴 뒤 원래 끝 시각으로 `push_del`(RESV_DEL)을 부른다. 끝 시각을 당기므로 현재 상태·주간·승격·재동기화·통계·빈 구간은 코드 수정 없이 맞는다. 웹은 내 예약 카드에 조기 퇴실 버튼과 확인 창을 더한다.

**Tech Stack:** FastAPI + SQLAlchemy + alembic + pytest (uv) / Vue 3 + TypeScript + Vitest (pnpm)

**Spec:** `docs/specs/2026-09-29-early-checkout-design.md`

## Global Constraints

- 공중 프로토콜(`lora_proto/`)·펌웨어·모뎀Pi·`server/app/lora_service/` 는 바꾸지 않는다 — 기존 `api.enqueue_resv_del` 만 쓴다.
- 새 상태를 만들지 않는다 — 퇴실한 예약도 `status == 'approved'`. `ck_resv_status` 그대로.
- `checked_out_at` 은 UTC naive datetime(`clock.to_utc`), `checked_in_at` 과 같은 규칙.
- 새 끝 시각 = max(퇴실한 분(초 버림), 시작 + 1분).
- 409 문구(정확히): "체크인한 예약만 퇴실할 수 있습니다" · "이미 퇴실했습니다" · "시작 전에는 취소를 쓰세요" · "이미 끝난 예약입니다". 상태가 approved 가 아니면 기존 `_require` 문구.
- 웹 문구(정확히): 버튼 "조기 퇴실", 확인 창 제목 "조기 퇴실", 본문 "퇴실하면 문 앞 화면에서 예약이 지워지고, 남은 시간은 다른 사람이 예약할 수 있어요.", 성공 알림 "퇴실했어요", 카드 "✓ HH:MM 퇴실".
- 커밋 메시지에 AI 저작 표기·Co-Authored-By 를 넣지 않는다. `lora_proto/` 수정 금지. force push·reset --hard 금지.
- Windows `core.autocrlf=true` — prettier 는 고친 파일에만 `--end-of-line auto` 로, 실제 변경은 `git diff --ignore-cr-at-eol` 로 확인.

## Review Focus

1. 시작한 그 분 안에 퇴실(예: 10:00 시작, 10:00:30 퇴실) → 끝 10:01, 길이 0 이 아니다 (Task 2 테스트).
2. 노드로 보낸 적 없는 예약(pushed_at NULL)을 퇴실 → RESV_DEL 이 나가지 않는다 (Task 2 테스트).
3. 퇴실과 관리자 취소가 거의 동시에 → 취소된 행에 퇴실이 찍히지 않는다: `_ID_LOCK` 안에서 `_require("approved")` (Task 2 — 상태 409 테스트로 고정).
4. 퇴실 직후 사이드바 '다음 예약' 카드와 체크인 한도 — 퇴실한 예약은 다음 예약이 아니다 (Task 3 테스트).
5. 퇴실한 카드에서 체크인·취소·퇴실 버튼이 다시 보이지 않는다 (Task 4 테스트).

---

### Task 1: 서버 — `checked_out_at` 컬럼·마이그레이션·응답 필드

**Files:**
- Modify: `server/app/domain/models.py` (Reservation, `checked_in_at` 아래)
- Create: `server/alembic/versions/resv_checkout_<rev>.py`
- Modify: `server/app/schemas.py` (`ResvMineOut`)
- Modify: `server/app/domain/admin.py` (`_mine_out`)
- Test: `server/tests/test_migrations.py`, `server/tests/test_student_resv.py`

**Interfaces:**
- Produces: `Reservation.checked_out_at: Mapped[dt.datetime | None]`, 응답 `ResvMineOut.checked_out_at: datetime | None`

- [ ] **Step 1: 실패 테스트** — `tests/test_migrations.py` 끝에:

```python
def test_resv_checkout_column(tmp_path):
    db = tmp_path / "c.db"
    _upgrade(db)
    cols = {c["name"]: c for c in inspect(create_engine(f"sqlite:///{db}")).get_columns("reservations")}
    assert cols["checked_out_at"]["nullable"] is True
```

`tests/test_student_resv.py` 의 `test_request_list_withdraw` 에서 신청 응답 `j` 검사 뒤에 한 줄:

```python
    assert j["checked_out_at"] is None
```

- [ ] **Step 2: 실패 확인** — `cd server && uv run pytest tests/test_migrations.py::test_resv_checkout_column tests/test_student_resv.py::test_request_list_withdraw -q` → FAIL (`KeyError: 'checked_out_at'`)

- [ ] **Step 3: 구현**

`models.py` — `checked_in_at` 다음 줄:

```python
    checked_out_at: Mapped[dt.datetime | None]  # 조기 퇴실 — 끝 시각(e_h·e_m)은 이 분으로 당겨진다
```

마이그레이션 — `cd server && uv run alembic revision -m "resv_checkout"` 로 만들고 `down_revision = "b78771d56b6e"` 확인 후 본문:

```python
def upgrade() -> None:
    with op.batch_alter_table(
        "reservations",
        table_args=(sa.CheckConstraint("id BETWEEN 1 AND 65535", name="ck_resv_id"),),
    ) as b:
        b.add_column(sa.Column("checked_out_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("reservations") as b:
        b.drop_column("checked_out_at")
```

`schemas.py` `ResvMineOut` — `checked_in_at` 다음:

```python
    checked_out_at: dt.datetime | None
```

`admin.py` `_mine_out` — `"checked_in_at": r.checked_in_at,` 다음:

```python
        "checked_out_at": r.checked_out_at,
```

- [ ] **Step 4: 통과 확인** — 같은 명령 → PASS. 그리고 `uv run pytest -q` 전체 PASS.
- [ ] **Step 5: 커밋** — `git add server/app server/alembic server/tests && git commit -m "feat(server): 예약에 checked_out_at — 조기 퇴실 기록 칸(마이그레이션)·학생/관리자 예약 응답 필드"`

### Task 2: 서버 — `reserve.checkout()` 과 `POST /me/reservations/{id}/checkout`

**Files:**
- Modify: `server/app/domain/reserve.py` (`checkin` 아래)
- Modify: `server/app/domain/student_router.py` (`checkin_resv` 아래)
- Test: `server/tests/test_student_resv.py`

**Interfaces:**
- Consumes: Task 1 의 `Reservation.checked_out_at`
- Produces: `reserve.checkout(s, r, now_local) -> list[int]` (enqueue 된 outbox id), 엔드포인트 200 → `ResvMineOut`

- [ ] **Step 1: 실패 테스트** — `tests/test_student_resv.py` 끝에(지금 KST 9/23 10:30, `UTC_NOW`):

```python
def _checked_in(app, rid, id_, s_h, s_m, e_h, e_m, *, pushed=True):
    _resv(app, rid, dt.date(2026, 9, 23), s_h, s_m, e_h, e_m, id_=id_, status="approved",
          requested_by="s1@mju.ac.kr", pushed_at=UTC_NOW if pushed else None)
    with app.state.Session() as s, s.begin():
        s.get(Reservation, id_).checked_in_at = UTC_NOW
    return id_


def test_checkout_frees_room(client, live, app, school, student_hdr, other_student_hdr, monkeypatch):
    _fix_clock(monkeypatch)
    _, ids = _building(app, 1, "E", rooms=((301, 1),))
    rid = ids[301]
    a = _checked_in(app, rid, 1, 10, 0, 12, 0)  # 10:00~12:00, 지금 10:30
    url = f"/api/student/me/reservations/{a}/checkout"
    assert client.post(url, headers=other_student_hdr).status_code == 404  # 남의 예약
    r = client.post(url, headers=student_hdr)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["checked_out_at"] and (j["e_h"], j["e_m"]) == (10, 30)  # 끝을 퇴실 분으로
    assert client.post(url, headers=student_hdr).json()["detail"] == "이미 퇴실했습니다"
    with live() as s:
        assert [o.type for o in s.scalars(select(Outbox))] == ["RESV_DEL"]
        assert s.get(Reservation, a).pushed_at is None
    rooms = client.get("/api/student/rooms", headers=student_hdr).json()
    assert [x["layout"] for x in rooms if x["room_id"] == rid] == [4]  # 바로 빈 강의실
    week = client.get(f"/api/student/rooms/{rid}/week", headers=student_hdr).json()
    today = next(d for d in week["free"] if d["date"] == "2026-09-23")
    assert today["spans"][0]["from"] == "10:30"  # 남은 시간이 예약 가능


def test_checkout_rejects(client, live, app, school, student_hdr, monkeypatch):
    _fix_clock(monkeypatch)
    _, ids = _building(app, 1, "E", rooms=((301, 1),))
    rid = ids[301]
    post = lambda i: client.post(f"/api/student/me/reservations/{i}/checkout", headers=student_hdr)
    _resv(app, rid, dt.date(2026, 9, 23), 10, 0, 11, 0, id_=1, status="approved",
          requested_by="s1@mju.ac.kr")  # 체크인 안 함
    assert post(1).json()["detail"] == "체크인한 예약만 퇴실할 수 있습니다"
    _checked_in(app, rid, 2, 10, 35, 11, 30)  # 10:35 시작, 지금 10:30(일찍 체크인)
    assert post(2).json()["detail"] == "시작 전에는 취소를 쓰세요"
    _checked_in(app, rid, 3, 9, 0, 10, 30)  # 10:30 끝 — 지금이 끝
    assert post(3).json()["detail"] == "이미 끝난 예약입니다"
    _resv(app, rid, dt.date(2026, 9, 23), 10, 0, 11, 0, id_=4, status="requested",
          requested_by="s1@mju.ac.kr")
    r = post(4)
    assert r.status_code == 409 and "requested" in r.json()["detail"]
    assert {post(i).status_code for i in (1, 2, 3)} == {409}


def test_checkout_same_minute_and_unpushed(client, live, app, school, student_hdr, monkeypatch):
    monkeypatch.setattr(clock, "now_utc", lambda: dt.datetime(2026, 9, 23, 1, 30, 40))  # noqa: DTZ001 — 10:30:40
    _, ids = _building(app, 1, "E", rooms=((301, 1),))
    a = _checked_in(app, ids[301], 1, 10, 30, 11, 0, pushed=False)  # 10:30 시작, 노드에 안 감
    j = client.post(f"/api/student/me/reservations/{a}/checkout", headers=student_hdr).json()
    assert (j["e_h"], j["e_m"]) == (10, 31)  # 시작 분 안의 퇴실 — 길이 0 이 아니라 +1분
    with live() as s:
        assert list(s.scalars(select(Outbox))) == []  # 보낸 적 없으니 RESV_DEL 도 없다
```

- [ ] **Step 2: 실패 확인** — `uv run pytest tests/test_student_resv.py -q -k checkout` → FAIL (404/405, 엔드포인트 없음)

- [ ] **Step 3: 구현**

`reserve.py` — `checkin` 아래:

```python
def checkout(s: Session, r: Reservation, now_local: dt.datetime) -> list[int]:
    """조기 퇴실 — 끝 시각을 퇴실 분으로 당겨 바로 빈 강의실·예약 가능으로 만든다.
    끝을 당기므로 현재 상태·주간·승격·재동기화·통계·빈 구간이 그대로 맞는다(spec §2).
    RESV_DEL 판단은 당기기 전의 원래 끝으로 — 노드에 가 있고 아직 안 끝난 예약만."""
    _require(r, "approved")
    if r.checked_in_at is None:
        raise HTTPException(409, "체크인한 예약만 퇴실할 수 있습니다")
    if r.checked_out_at is not None:
        raise HTTPException(409, "이미 퇴실했습니다")
    st, en = start_local(r), end_local(r)
    if now_local < st:
        raise HTTPException(409, "시작 전에는 취소를 쓰세요")
    if now_local >= en:
        raise HTTPException(409, "이미 끝난 예약입니다")
    old_end = (r.date, r.e_h, r.e_m)
    # 초 버림, 시작 분 안이면 +1분 — 길이 0 은 겹침 검사에서 그 시각을 걸치는 신청을 막는다
    new_end = max(now_local.hour * 60 + now_local.minute, r.s_h * 60 + r.s_m + 1)
    r.e_h, r.e_m = divmod(new_end, 60)
    r.checked_out_at = clock.to_utc(now_local)
    return push_del(s, r, now_local, end=old_end)
```

`student_router.py` — `checkin_resv` 아래:

```python
@router.post("/me/reservations/{id}/checkout", response_model=S.ResvMineOut)
def checkout_resv(id: int, user: User = StudentUser, s: Session = _DB):
    with _ID_LOCK:  # 관리자 취소와 엇갈려 cancelled 행에 퇴실이 찍히지 않게
        r = _my_resv(s, user, id)
        mid = reserve.addr(s, r)[2]
        reserve.checkout(s, r, clock.local_now())
        out = _mine_out(s, r)
        _commit_notify(s, mid)
    return out
```

- [ ] **Step 4: 통과 확인** — `uv run pytest tests/test_student_resv.py -q -k checkout` → PASS, `uv run pytest -q` 전체 PASS, `uv run ruff check . && uv run ruff format --check .` clean(포맷이 어긋나면 `uv run ruff format` 을 고친 파일에만).
- [ ] **Step 5: 커밋** — `git add server && git commit -m "feat(server): 학생 조기 퇴실 — POST /me/reservations/{id}/checkout, 끝 시각을 퇴실 분으로 당기고 노드에 RESV_DEL"`

### Task 3: 웹 — 타입·API·규칙

**Files:**
- Modify: `web/src/api/types.ts` (`ResvMineOut`, `RESV_MINE_DATES`)
- Modify: `web/src/api/__fixtures__/mine.ts`
- Modify: `web/src/api/student.ts`
- Modify: `web/src/components/student/rules.ts`
- Test: `web/src/api/__tests__/student.spec.ts`, `web/src/components/student/__tests__/rules.spec.ts`

**Interfaces:**
- Consumes: Task 2 의 엔드포인트·필드
- Produces: `studentApi.checkout(id: number): Promise<ResvMineOut>`, `checkoutState(r: ResvMineOut, now: Date): { kind: 'open' } | { kind: 'done'; at: string } | null`, `nextResv` 가 퇴실한 예약을 건너뜀

- [ ] **Step 1: 실패 테스트**

`api/__tests__/student.spec.ts` — 체크인 URL 검사 옆에:

```ts
    await studentApi.checkout(7)
    expect(call(2).url).toBe('/api/student/me/reservations/7/checkout')
```

(같은 테스트의 fetch 목이 세 번째 응답도 돌려주게 기존 `mockResolvedValue` 를 그대로 쓴다.)

`rules.spec.ts` — `describe('내 예약', …)` 안에(`NOW` = KST 10/23 10:42, 기존 상수):

```ts
  it('조기 퇴실 — 체크인했고 시작~끝 사이만, 퇴실하면 시각', () => {
    const inUse = { s_h: 10, s_m: 0, e_h: 12, e_m: 0, checked_in_at: new Date('2026-10-23T01:01:00Z') }
    expect(checkoutState(resv(inUse), NOW)).toEqual({ kind: 'open' })
    expect(checkoutState(resv({ ...inUse, checked_in_at: null }), NOW)).toBeNull()
    expect(checkoutState(resv({ ...inUse, s_h: 10, s_m: 50 }), NOW)).toBeNull() // 시작 전
    expect(checkoutState(resv({ ...inUse, e_h: 10, e_m: 40 }), NOW)).toBeNull() // 끝남
    expect(
      checkoutState(resv({ ...inUse, e_m: 0, e_h: 10, checked_out_at: new Date('2026-10-23T01:23:00Z') }), NOW),
    ).toEqual({ kind: 'done', at: '10:23' })
  })

  it('다음 예약은 퇴실한 예약을 건너뛴다', () => {
    const out = resv({ id: 1, s_h: 10, s_m: 0, e_h: 10, e_m: 43, checked_in_at: new Date(), checked_out_at: new Date() })
    const later = resv({ id: 2, s_h: 15, s_m: 0, e_h: 16, e_m: 0 })
    expect(nextResv([out, later], NOW)?.id).toBe(2)
  })
```

(`resv` 는 이 파일의 기존 빌더 — `mineResv({ date: '2026-10-23', ... })` 꼴. import 에 `checkoutState` 추가.)

- [ ] **Step 2: 실패 확인** — `cd web && pnpm -s vitest run src/api src/components/student` → FAIL

- [ ] **Step 3: 구현**

`types.ts` `ResvMineOut` — `checked_in_at` 다음 `checked_out_at: Date | null`, `RESV_MINE_DATES` 에 `'checked_out_at'` 추가.

`__fixtures__/mine.ts` — `checked_in_at: null,` 다음 `checked_out_at: null,`.

`student.ts` — `checkin` 다음:

```ts
  /** 체크인했고 시작~끝 사이의 approved 만. 끝 시각을 퇴실 분으로 당긴다. 그 밖 409 */
  checkout: (id: number) =>
    request<ResvMineOut>('POST', `/api/student/me/reservations/${id}/checkout`, undefined, mineOpts),
```

`rules.ts` — `checkinState` 아래:

```ts
export type CheckoutState = { kind: 'open' } | { kind: 'done'; at: string }
/** 조기 퇴실 — 체크인한 승인 예약이 시작~끝 사이일 때만 (spec §3). 퇴실했으면 그 시각 */
export function checkoutState(r: ResvMineOut, now: Date): CheckoutState | null {
  if (r.checked_out_at) return { kind: 'done', at: formatHm(r.checked_out_at) }
  if (r.status !== 'approved' || !r.checked_in_at) return null
  const n = nowAt(now)
  return startAt(r) <= n && n < endAt(r) ? { kind: 'open' } : null
}
```

`nextResv` 의 filter 를 `(r) => !r.checked_out_at && isActive(r, n)` 으로.

- [ ] **Step 4: 통과 확인** — 같은 명령 PASS, `pnpm -s typecheck && pnpm -s lint` clean.
- [ ] **Step 5: 커밋** — `git add web/src && git commit -m "feat(web): 조기 퇴실 API·규칙 — checked_out_at, studentApi.checkout, checkoutState, 다음 예약은 퇴실한 예약을 건너뜀"`

### Task 4: 웹 — 내 예약 카드 버튼·확인 창

**Files:**
- Modify: `web/src/components/student/MyResvCard.vue`
- Modify: `web/src/student/views/MyView.vue`
- Test: `web/src/components/student/__tests__/myResvCard.spec.ts`, `web/src/student/__tests__/me.spec.ts`

**Interfaces:**
- Consumes: Task 3 의 `checkoutState`, `studentApi.checkout`
- Produces: `MyResvCard` 이벤트 `checkout`, `busy` prop 에 `'checkout'`

- [ ] **Step 1: 실패 테스트**

`myResvCard.spec.ts`:

```ts
  it('체크인하고 사용 중이면 조기 퇴실, 퇴실하면 시각만 — 버튼이 다시 생기지 않는다', async () => {
    const now = new Date('2026-10-23T01:42:00Z') // KST 10:42
    const inUse = mineResv({ date: '2026-10-23', s_h: 10, e_h: 12, checked_in_at: new Date('2026-10-23T01:01:00Z') })
    const w = mount(MyResvCard, { props: { resv: inUse, now } })
    await w.findAll('button').find((b) => b.text() === '조기 퇴실')!.trigger('click')
    expect(w.emitted('checkout')).toHaveLength(1)
    const out = mount(MyResvCard, {
      props: { resv: { ...inUse, e_h: 10, e_m: 23, checked_out_at: new Date('2026-10-23T01:23:00Z') }, now },
    })
    expect(out.text()).toContain('✓ 10:23 퇴실')
    expect(out.findAll('button')).toHaveLength(0)
  })
```

`me.spec.ts` — `describe('MyView — /me', …)` 안에:

```ts
  it('조기 퇴실 — 확인 창을 거쳐 한 번 보내고 알림 뒤 다시 부른다', async () => {
    const inUse = resv({ id: 7, s_m: 0, e_h: 12, checked_in_at: new Date('2026-10-23T01:01:00Z') })
    api.mine.mockResolvedValue([inUse])
    api.checkout.mockResolvedValue({ ...inUse, checked_out_at: new Date() })
    const { w } = await mountAt(MyView, '/me', '/me')
    await w.findAll('button').find((b) => b.text() === '조기 퇴실')!.trigger('click')
    const dlg = w.get('[role="dialog"]')
    expect(dlg.text()).toContain('남은 시간은 다른 사람이 예약할 수 있어요')
    await confirm(w)
    expect(api.checkout).toHaveBeenCalledWith(7)
    expect(texts()).toContain('퇴실했어요')
    expect(api.mine).toHaveBeenCalledTimes(2)
  })
```

(`me.spec.ts` 의 `vi.mock('@/api/student', …)` 목록에 `checkout: vi.fn()` 추가, `beforeEach` 에 `api.checkout.mockReset()`.)

- [ ] **Step 2: 실패 확인** — `pnpm -s vitest run src/components/student src/student/__tests__/me.spec.ts` → FAIL

- [ ] **Step 3: 구현**

`MyResvCard.vue`:
- script: `busy?: 'checkin' | 'cancel' | 'checkout' | null`, emits 에 `checkout: []`, `const co = computed(() => checkoutState(props.resv, props.now))`, import `checkoutState`.
- 템플릿: 체크인 표시(`ci?.kind === 'done'`)는 퇴실하지 않았을 때만 — `v-if="ci?.kind === 'done' && !co"` 를 `co?.kind !== 'done'` 조건으로 감싼다. `.mc__actions` 안, 체크인 버튼 뒤에:

```vue
      <p v-if="co?.kind === 'done'" class="mc__done num">✓ {{ co.at }} 퇴실</p>
      <Button
        v-else-if="co?.kind === 'open'"
        variant="secondary"
        :disabled="busy !== null"
        :loading="busy === 'checkout'"
        @click="emit('checkout')"
        >조기 퇴실</Button
      >
```

- `.mc__actions` 의 `v-if` 를 `ci || cancel || co` 로.
- 퇴실한 카드(`co?.kind === 'done'`)에서는 체크인 완료 줄을 숨겨 "✓ 퇴실" 한 줄만 남긴다.

`MyView.vue`:
- `type Kind = 'checkin' | 'cancel' | 'checkout'`
- `const leaving = ref<ResvMineOut | null>(null)`, `askCheckout = (r) => { if (!busy.value) leaving.value = r }`, `closeLeave = () => (leaving.value = null)`,

```ts
async function confirmCheckout() {
  const r = leaving.value
  if (!r) return
  leaving.value = null
  await run(r, 'checkout', () => studentApi.checkout(r.id), '퇴실했어요', CHANGED_TEXT)
}
```

- `MyResvCard` 에 `@checkout="askCheckout(r)"`.
- 두 번째 `Modal`:

```vue
    <Modal :open="leaving !== null" title="조기 퇴실" size="sm" @close="closeLeave">
      <p class="me__confirm">
        퇴실하면 문 앞 화면에서 예약이 지워지고, 남은 시간은 다른 사람이 예약할 수 있어요.
      </p>
      <template #footer>
        <Button variant="secondary" @click="closeLeave">닫기</Button>
        <Button @click="confirmCheckout">조기 퇴실</Button>
      </template>
    </Modal>
```

- [ ] **Step 4: 통과 확인** — `pnpm -s vitest run` 전체 PASS, `pnpm -s typecheck && pnpm -s lint` clean.
- [ ] **Step 5: 커밋** — `git add web/src && git commit -m "feat(web): 내 예약 카드에 조기 퇴실 — 확인 창, 퇴실 뒤 '✓ 퇴실' 표시"`

### Task 5: 실제 흐름 확인·E2E 무회귀

**Files:** 없음(확인만)

- [ ] **Step 1:** E2E 무회귀 — detached worktree 에서 `E2E_API_PORT=8200 E2E_WEB_PORT=5373 pnpm e2e` → 59 passed. (조기 퇴실 자체는 E2E 로 재지 않는다 — 신청은 미래 시각만 받아 "시작이 지난 체크인 예약"을 만들려면 몇 분을 기다려야 한다. 서버 통합 테스트(Task 2)와 컴포넌트 테스트(Task 4)가 맡는다.)
- [ ] **Step 2:** 수동 서버(8000·5173)에서 Playwright 로: student1 이 다음 5분 정각 시작 예약 신청 → admin1 승인 → 시작 시각이 지나면 체크인 → 조기 퇴실 → 확인 → 카드 "✓ 퇴실", 학생 목록에서 그 강의실 "비어있음", 서버 outbox 에 RESV_DEL(노드로 보낸 적 있을 때). 스크린샷 390·1440.
- [ ] **Step 3:** 서버 PR 과 웹 PR 을 나눠 올릴 수 있게 커밋이 서버(Task 1·2)·웹(Task 3·4)으로 갈려 있는지 `git log --oneline` 로 확인.

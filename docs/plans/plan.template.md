# <기능명> — 구현 계획 (plan)

<!-- 배치: docs/plans/YYYY-MM-DD-<feature-slug>.md -->
<!-- writing-plans 스킬로 작성. spec을 "어떻게"로 옮긴 작업지시서. Task 단위로 쪼갠다. -->
<!-- 각 Task는 그대로 실행 가능해야 한다: 파일·인터페이스·실패테스트·구현·커밋까지 명시. -->

- 생성일시: YYYY-MM-DD
- 기준 spec: `docs/specs/YYYY-MM-DD-<feature-slug>-design.md`

**Goal:** (한 문장)

**Architecture:** (구현 방식 요약. 기존 무엇을 재사용, 무엇이 신규.)

**Tech Stack:** (해당 영역의 스택 — firmware: PlatformIO/C++ · server: FastAPI/uv · web: Vue 3/pnpm)

---

### Task 1: <작업 제목>

**Files:**
- Create/Modify: `<파일 경로>`
- Test: `<테스트 파일 경로>`

**Interfaces:**
- Produces: `<함수·구조체 시그니처>`

- [ ] **Step 1: 실패하는 테스트**

```cpp
// 실패 테스트 코드
```

Run: `<테스트 명령> <선택자>` → FAIL.

- [ ] **Step 2: 구현**

```cpp
// 구현 코드
```

- [ ] **Step 3: 통과 + 커밋**

Run: `<테스트 명령>` → PASS.

```bash
git add <파일들>
git commit -m "feat(<area>): <작업 제목>"
```

---

### Task 2: <작업 제목>

(Task 1과 동일 구조로 반복)

---

### Task N: 전체 게이트 + PR

- [ ] **Step 1: full 게이트**

바꾼 영역의 명령을 모두 통과시킨다.

```bash
# firmware
pio test -e native && pio check -e terminal --fail-on-defect medium
# server
uv run pytest -q && uv run ruff check . && uv run ruff format --check .
# web
pnpm test && pnpm lint && pnpm exec vue-tsc --noEmit
```

- [ ] **Step 2: PR**

- 제목: `feat(<area>): <기능명>`
- 본문: Task 요약 + 게이트 결과 + (계약 변경 시) **lockstep 필요 명시**.

## 이후

- (배포 순서, 후속 작업, 타 영역 연계.)

## Self-Review (계획 검토)

- 스펙 커버리지: spec의 각 목표 → 어느 Task가 담당하는지. ✅
- Placeholder 없음(실제 코드로 채워짐). ✅
- 함정 선제 회피: (계약 변경 순서·재사용 헬퍼 실존·프레임 크기 한계 등 미리 점검한 것.)

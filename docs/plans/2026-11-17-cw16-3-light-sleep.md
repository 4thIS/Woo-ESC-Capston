# 노드 light sleep (절전 작업 3단계 중 3a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 빌드 플래그 `SLEEP_MODE=1`(LIGHT, v2 §6.7)로 노드가 할 일이 없을 때 ESP32 light sleep 에 들어가고, SX1262 는 수신 duty cycle(웨이크 프리앰블 감지)로 듣는다. 무선 프레임(DIO1)·다음 화면 변경 시각·STATUS 예약 시각에 깬다. 같은 화면은 다시 그리지 않는다(모든 모드). 웨이크 미수신률 ≤ 5 % 를 실기로 잰다.

**Architecture:** 판단(같은 화면인가·얼마나 잘까)은 `lib/node_core` 순수 함수로 두고 호스트에서 시험한다. `main.cpp` 는 `#if SLEEP_MODE == 1` 블록에서 잠들기·깨기만 한다. light sleep 은 RAM·RadioLib 객체·millis 가 그대로라 지금의 깨어 있는 루프를 그대로 쓰고, 루프 끝에 "잘 수 있으면 잔다"만 더한다. 기본 빌드(플래그 없음)는 지금과 같은 깨어 있는 모드 — 경진대회(11/19) 시연 펌웨어는 바뀌지 않는다. deep sleep(3b)은 이 계획 밖.

**Tech Stack:** C++17, PlatformIO, ESP-IDF sleep API(`esp_light_sleep_start`, `gpio_wakeup_enable`), RadioLib 7.1.2 `startReceiveDutyCycleAuto`

## Global Constraints

- `lora_proto/`·`lib/lora_codec/`·`lib/node_store/`·`lib/schedule/`·`lib/render*` 은 바꾸지 않는다.
- 기본 빌드(`SLEEP_MODE` 정의 없음 또는 0) 동작은 같은 화면 다시 그리지 않기 외에는 FW 4 와 같다.
- `SLEEP_MODE == 1`(LIGHT): 잠들기 조건 = 마지막 내 프레임 뒤 `QUIET_MS`(8 s) 지남 · 받은 프레임 없음(`g_irq` 거짓) · 그릴 것이 없음(`g_dirty` 거짓, 또는 지금은 그릴 수 없음 — 시계 무효이거나 오늘 슬롯 준비 전).
- 잘 시간 = min(다음 화면 변경 `sch::nextChangeAt`(+2 s 포함, 하루 STATUS 시각 포함) − 지금, STATUS 예약까지, 상한). 상한 = 30 min, 오늘 슬롯 준비 전(refreshDay 실패 중)이면 60 s. 최소 1 s 미만이면 자지 않는다.
- 무선: 잠들기 전 `radio.startReceiveDutyCycleAuto(RX_PREAMBLE_SYM, RP_RX_DUTY_MIN_SYM)`(DIO1 = RX_DONE). 깨면 연속 수신(`listen()`)으로 돌아간다 — FILE_DATA·END 는 짧은 프리앰블로 오기 때문(§6.4 세션 창).
- DIO1 깨우기: 잠들기 전 DIO1 인터럽트를 떼고(`radio.clearDio1Action()`) `gpio_wakeup_enable(DIO1, GPIO_INTR_HIGH_LEVEL)`. 깨면 `gpio_wakeup_disable` → `radio.setDio1Action(onDio1)` → DIO1 이 HIGH 면 `g_irq = true`. (level 인터럽트를 붙인 채 깨면 ISR 이 끝없이 돈다)
- 같은 화면 판단: `RenderModel` 의 화면에 그려지는 필드(layout·bld·room·unit·dateStr·weekday·cur·next·nToday·today[0..nToday)·newTag)가 마지막으로 그린 것과 같으면 그리지 않는다. `battMv` 는 화면에 안 그리므로 비교에서 뺀다. 상태키(레이아웃·요일·시작 분)는 그대로 갱신한다.
- 로그: 깨면 `[node] 깸 cause=<radio|timer> slept=<ms>`. 잠들기 전 `Serial.flush()`.
- 펌웨어 버전 `FW_VER` 4 → 5.
- 커밋 형식 `feat(firmware):`.

## 파일 구조

| 파일 | 변경 | 책임 |
|---|---|---|
| `firmware/lib/node_core/node_core.h`·`.cpp` | 수정 | `sameScreen`, `StatusPlan::msUntilDue`, `sleepMs` |
| `firmware/test/test_node_core/test_main.cpp` | 수정 | 시험 추가 |
| `firmware/src/terminal/main.cpp` | 수정 | 같은 화면 건너뛰기, `SLEEP_MODE` LIGHT 잠들기·깨기, FW 5 |
| `docs/specs/2026-09-09-lora-v2-wor-design.md` | 수정(짧게) | §6.7 메모 |

---

### Task 1: 잠들기 판단 로직 (`lib/node_core`)

**Files:** `firmware/lib/node_core/node_core.h`, `node_core.cpp`, `firmware/test/test_node_core/test_main.cpp`

**Interfaces — Produces:**
```cpp
bool sameScreen(const RenderModel& a, const RenderModel& b);  // battMv 무시
// StatusPlan 에 추가: 한 번짜리 예약까지 남은 ms. 이미 지났으면 0, 없으면(또는 시계가 맞아 건너뛸 재시도면) UINT32_MAX
uint32_t StatusPlan::msUntilDue(uint32_t nowMs, bool clockOk) const;
constexpr uint32_t kSleepCapMs = 30u * 60u * 1000u;
constexpr uint32_t kSleepCapNoDayMs = 60000;
constexpr uint32_t kSleepMinMs = 1000;
// 잘 시간(ms). 0 이면 자지 않는다. nextChangeEpoch = sch::nextChangeAt(...) (clockOk 일 때만 쓴다), dayReady = 오늘 슬롯 준비됨
uint32_t sleepMs(uint32_t nowMs, bool clockOk, uint32_t nowEpoch, uint32_t nextChangeEpoch, bool dayReady,
                 const StatusPlan& p);
```

- [ ] **Step 1: 실패하는 시험** — `test_main.cpp` 의 STATUS 시험들 뒤에 넣고 `main()` 에 등록:

```cpp
// ---------------- 같은 화면(절전 3단계) ----------------
void test_same_screen_ignores_batt_and_unused_today() {
  RenderModel a{}, b{};
  R->slotsDay = 4;
  R->nSlots = 1;
  R->slots[0] = slot(4, 13, 0, 14, 50, "수업");
  buildModel(*R, NOW, a);
  buildModel(*R, NOW, b);
  TEST_ASSERT_TRUE(sameScreen(a, b));
  b.battMv = a.battMv + 100;
  TEST_ASSERT_TRUE(sameScreen(a, b));  // 배터리는 화면에 없다
  b.today[20].sH = 7;                  // nToday 밖 칸
  TEST_ASSERT_TRUE(sameScreen(a, b));
  b = a;
  b.cur.subj[0] = 'X';
  TEST_ASSERT_FALSE(sameScreen(a, b));
  b = a;
  b.layout = LP_LAYOUT_BREAK;
  TEST_ASSERT_FALSE(sameScreen(a, b));
  b = a;
  b.dateStr[4] = '9';
  TEST_ASSERT_FALSE(sameScreen(a, b));
  b = a;
  b.today[0].eM = 40;
  TEST_ASSERT_FALSE(sameScreen(a, b));
  b = a;
  b.nToday = 0;
  TEST_ASSERT_FALSE(sameScreen(a, b));
}

// ---------------- 잘 시간(절전 3단계) ----------------
void test_status_plan_ms_until_due() {
  StatusPlan p;
  TEST_ASSERT_EQUAL_UINT32(UINT32_MAX, p.msUntilDue(0, false));
  p.request(1000, 4000);
  TEST_ASSERT_EQUAL_UINT32(4000, p.msUntilDue(1000, false));
  TEST_ASSERT_EQUAL_UINT32(0, p.msUntilDue(9000, false));  // 지났다
  p.sent(5000, true, false, LP_STATUSFLAG_CLOCK_STALE);   // 시계 재시도 30 s
  TEST_ASSERT_EQUAL_UINT32(kStaleRetryFirstMs, p.msUntilDue(5000, false));
  TEST_ASSERT_EQUAL_UINT32(UINT32_MAX, p.msUntilDue(5000, true));  // 시계가 맞으면 건너뛸 재시도
}

void test_sleep_ms() {
  StatusPlan p;
  // 시계 있음: 다음 변경 10 min 뒤
  TEST_ASSERT_EQUAL_UINT32(600000, sleepMs(0, true, NOW, NOW + 600, true, p));
  // 상한 30 min
  TEST_ASSERT_EQUAL_UINT32(kSleepCapMs, sleepMs(0, true, NOW, NOW + 7200, true, p));
  // 오늘 슬롯 준비 전 — 60 s
  TEST_ASSERT_EQUAL_UINT32(kSleepCapNoDayMs, sleepMs(0, true, NOW, NOW + 7200, false, p));
  // 시계 없음 — 다음 변경은 쓰지 않는다
  TEST_ASSERT_EQUAL_UINT32(kSleepCapMs, sleepMs(0, false, 1000, 0, false, p));
  // STATUS 예약이 더 이르면 그때
  p.request(0, 20000);
  TEST_ASSERT_EQUAL_UINT32(20000, sleepMs(0, true, NOW, NOW + 600, true, p));
  // 1 s 미만이면 자지 않는다
  TEST_ASSERT_EQUAL_UINT32(0, sleepMs(19500, true, NOW, NOW + 600, true, p));
  StatusPlan q;
  TEST_ASSERT_EQUAL_UINT32(0, sleepMs(0, true, NOW, NOW, true, q));  // 변경 시각이 지금
  TEST_ASSERT_EQUAL_UINT32(0, sleepMs(0, true, NOW, NOW - 5, true, q));
}
```
```cpp
  RUN_TEST(test_same_screen_ignores_batt_and_unused_today);
  RUN_TEST(test_status_plan_ms_until_due);
  RUN_TEST(test_sleep_ms);
```
(`slot()`·`R`·`NOW`(2026-11-19 목 13:30 KST)·`buildModel` 은 파일에 이미 있다. `#include <cstdint>` 의 `UINT32_MAX` 가 없으면 `<climits>`·`<stdint.h>` 를 더한다.)

- [ ] **Step 2: 실패 확인** — `cd firmware && pio test -e native -f test_node_core` → 컴파일 실패

- [ ] **Step 3: 구현** — `node_core.h` 의 `StatusPlan` public 에 `uint32_t msUntilDue(uint32_t nowMs, bool clockOk) const;` 를 더하고, 클래스 뒤에:

```cpp
// ---- 잠들기 판단 (v2 §6.3·6.7, 절전 3단계) ----
constexpr uint32_t kSleepCapMs = 30u * 60u * 1000u;  // 한 번에 최대 30 min
constexpr uint32_t kSleepCapNoDayMs = 60000;         // 오늘 슬롯 준비 전(refreshDay 실패 중) 60 s 마다 재시도
constexpr uint32_t kSleepMinMs = 1000;               // 이보다 짧으면 자지 않는다

// 화면에 그려지는 필드가 같은가(battMv 와 nToday 밖 today 칸은 보지 않는다)
bool sameScreen(const RenderModel& a, const RenderModel& b);
// 잘 시간(ms), 0 = 자지 않음. nextChangeEpoch 는 clockOk 일 때만 본다(sch::nextChangeAt 값, +2 s·하루 STATUS 포함)
uint32_t sleepMs(uint32_t nowMs, bool clockOk, uint32_t nowEpoch, uint32_t nextChangeEpoch, bool dayReady,
                 const StatusPlan& p);
```
`node_core.cpp` 끝(`}  // namespace nc` 앞)에:

```cpp
uint32_t StatusPlan::msUntilDue(uint32_t nowMs, bool clockOk) const {
  if (!pending_ || (onlyIfStale_ && clockOk)) return UINT32_MAX;
  const int32_t left = (int32_t)(dueMs_ - nowMs);
  return left <= 0 ? 0 : (uint32_t)left;
}

namespace {
bool sameSlot(const RenderSlot& a, const RenderSlot& b) {
  return std::strcmp(a.subj, b.subj) == 0 && std::strcmp(a.prof, b.prof) == 0 && a.sH == b.sH && a.sM == b.sM &&
         a.eH == b.eH && a.eM == b.eM && a.type == b.type && a.flags == b.flags;
}
}  // namespace

bool sameScreen(const RenderModel& a, const RenderModel& b) {
  if (a.layout != b.layout || a.bld != b.bld || a.room != b.room || a.unit != b.unit || a.weekday != b.weekday ||
      a.nToday != b.nToday)
    return false;
  if (std::strncmp(a.dateStr, b.dateStr, sizeof a.dateStr) != 0) return false;
  if (std::strncmp(a.newTag, b.newTag, sizeof a.newTag) != 0) return false;
  if (!sameSlot(a.cur, b.cur) || !sameSlot(a.next, b.next)) return false;
  for (uint8_t i = 0; i < a.nToday && i < 24; ++i) {
    const TodaySlot &x = a.today[i], &y = b.today[i];
    if (x.sH != y.sH || x.sM != y.sM || x.eH != y.eH || x.eM != y.eM || x.type != y.type ||
        std::strcmp(x.subj, y.subj) != 0)
      return false;
  }
  return true;
}

uint32_t sleepMs(uint32_t nowMs, bool clockOk, uint32_t nowEpoch, uint32_t nextChangeEpoch, bool dayReady,
                 const StatusPlan& p) {
  uint32_t ms = dayReady ? kSleepCapMs : kSleepCapNoDayMs;
  if (clockOk) {
    if (nextChangeEpoch <= nowEpoch) return 0;
    const uint32_t untilChange = nextChangeEpoch - nowEpoch;
    if (untilChange < ms / 1000u) ms = untilChange * 1000u;
  }
  const uint32_t untilStatus = p.msUntilDue(nowMs, clockOk);
  if (untilStatus < ms) ms = untilStatus;
  return ms < kSleepMinMs ? 0 : ms;
}
```
(`<cstring>`·`<cstdint>`/`<climits>` include 를 확인한다. `RenderModel` 은 `render_model.h` 로 이미 들어와 있다.)

- [ ] **Step 4: 통과** — `pio test -e native -f test_node_core` PASS, clang-format clean.
- [ ] **Step 5: Commit** — `feat(firmware): 잠들기 판단 로직 — 같은 화면 비교·잘 시간(sleepMs)·STATUS 예약까지 남은 시간`

---

### Task 2: 같은 화면 건너뛰기 + LIGHT 잠들기 (`src/terminal/main.cpp`)

**Files:** `firmware/src/terminal/main.cpp`

- [ ] **Step 1: 머리** — `#include <esp_sleep.h>`, `#include <driver/gpio.h>` 를 더하고:

```cpp
#ifndef SLEEP_MODE
#define SLEEP_MODE 0  // 0 = 깨어 있음(시연), 1 = LIGHT(v2 §6.7 1단계 검증). DEEP 은 3b
#endif
```
`FW_VER = 5`. 파일 머리 주석에 `- 절전: SLEEP_MODE=1 이면 할 일이 없을 때 light sleep, 무선은 수신 duty cycle(절전 3단계)` 한 줄.

- [ ] **Step 2: 같은 화면 건너뛰기** — 전역 `RenderModel g_shown{}; bool g_shownValid = false;`. `loop()` 의 렌더 블록(`if (g_dirty && millis() - g_lastRxMs > QUIET_MS) {` 안)에서 상태키·`g_layout` 갱신과 `rtcSeal` 은 지금처럼 하고, `render(m)` 직전에:

```cpp
    if (g_shownValid && nc::sameScreen(g_shown, m)) {
      Serial.printf("[node] 같은 화면 — 다시 그리지 않음 layout=%u\n", m.layout);
      return;
    }
```
`render(m)` 뒤에 `g_shown = m; g_shownValid = true;`.

- [ ] **Step 3: LIGHT 잠들기** — `#if SLEEP_MODE == 1` 블록으로 감싼 함수(익명 namespace, `listen()`·`clockValid()`·`g_status` 정의 뒤):

```cpp
#if SLEEP_MODE == 1
// v2 §6.7 LIGHT — RAM·RadioLib 객체·millis 는 그대로. 무선은 수신 duty cycle 로 웨이크 프리앰블을 기다린다
void lightSleep(uint32_t ms) {
  radio.standby();
  radio.setPreambleLength(RX_PREAMBLE_SYM);
  g_irq = false;
  const int st = radio.startReceiveDutyCycleAuto(RX_PREAMBLE_SYM, RP_RX_DUTY_MIN_SYM);
  if (st != RADIOLIB_ERR_NONE) {
    Serial.printf("[node] duty cycle 실패 %d — 자지 않음\n", st);
    listen();
    return;
  }
  radio.clearDio1Action();  // level 깨우기를 쓰는 동안 엣지 인터럽트를 뗀다(붙인 채면 깬 뒤 ISR 이 끝없이 돈다)
  gpio_wakeup_enable((gpio_num_t)LORA_DIO1, GPIO_INTR_HIGH_LEVEL);
  esp_sleep_enable_gpio_wakeup();
  esp_sleep_enable_timer_wakeup((uint64_t)ms * 1000ULL);
  Serial.flush();
  const uint32_t t0 = millis();
  esp_light_sleep_start();
  const esp_sleep_wakeup_cause_t why = esp_sleep_get_wakeup_cause();
  gpio_wakeup_disable((gpio_num_t)LORA_DIO1);
  esp_sleep_disable_wakeup_source(ESP_SLEEP_WAKEUP_ALL);
  radio.setDio1Action(onDio1);
  const bool fromRadio = digitalRead(LORA_DIO1) == HIGH;
  if (fromRadio) g_irq = true;  // 패킷은 pollRadio 가 읽고 그 뒤 listen() 으로 연속 수신
  else listen();
  Serial.printf("[node] 깸 cause=%s slept=%lums\n", fromRadio ? "radio" : (why == ESP_SLEEP_WAKEUP_TIMER ? "timer" : "other"),
                (unsigned long)(millis() - t0));
}

void maybeSleep() {
  if (g_irq || millis() - g_lastRxMs <= QUIET_MS) return;
  const bool clk = clockValid();
  const uint32_t now = (uint32_t)time(nullptr);
  const bool dayReady = clk && g_rtc.slotsDay == sch::toKst(now).weekday;
  if (g_dirty && dayReady) return;  // 그릴 것이 남았다 — 렌더 블록이 먼저
  uint32_t next = 0;
  if (dayReady) {
    next = sch::nextChangeAt(sch::ScheduleView{g_rtc.slots, g_rtc.nSlots, g_rtc.resv, g_rtc.nResv, g_rtc.exams,
                                               g_rtc.nExam},
                             now, g_rtc.nextStatusEpoch);
  } else if (clk) {
    next = now + nc::kSleepCapNoDayMs / 1000;
  }
  const uint32_t ms = nc::sleepMs(millis(), clk, now, next, dayReady, g_status);
  if (ms == 0) return;
  lightSleep(ms);
}
#endif
```
`loop()` 맨 끝(렌더 블록 뒤)과, 루프 앞쪽의 이른 `return`(시계 무효·오늘 슬롯 준비 전·1 s 틱 미달)을 지나도 잠들 수 있게 — `loop()` 를 `loopBody()` 로 이름을 바꾸고:

```cpp
void loop() {
  loopBody();
#if SLEEP_MODE == 1
  maybeSleep();
#endif
}
```
(`loopBody` 는 익명 namespace 밖이면 `static`. 기존 `loop()` 의 내용은 그대로 옮긴다 — 같은 화면 `return` 도 loopBody 안의 return 이 된다.)

- [ ] **Step 4: 빌드** — 두 모드 모두:
  - `cd firmware && pio run -e terminal` → SUCCESS
  - `PLATFORMIO_BUILD_FLAGS="-DSLEEP_MODE=1" pio run -e terminal` → SUCCESS
  - `pio test -e native -f test_node_core` PASS, clang-format clean
- [ ] **Step 5: Commit** — `feat(firmware): 같은 화면은 다시 그리지 않음, SLEEP_MODE=1 light sleep(수신 duty cycle·DIO1/타이머 깨우기), FW 5`

---

### Task 3: 실기 + 기록

E301 = LIGHT(`-DSLEEP_MODE=1`), E803 = 기본(대조군·시연 펌웨어).

| 확인 | 기대 |
|---|---|
| 부팅 | 부팅 STATUS → 타겟 TIME → 렌더 → 8 s 뒤 `깸`/잠 반복 로그(다음 변경까지) |
| 웨이크 미수신률 | 프레임 간격 12~16 s(노드가 잠든 뒤)로 SLOT_SET 100회(일요일 23:00 측정 슬롯, measure.py 변형) — **첫 시도 acked ≥ 95 %**, 지연 분포 |
| 같은 화면 | 측정 슬롯(오늘 아님) 변경 뒤 `같은 화면 — 다시 그리지 않음`, 30분 TIME 뒤에도 다시 그리지 않음 |
| 타이머 깨우기 | 다음 교시 경계(nextChangeAt)에 `깸 cause=timer` → 렌더 |
| FILE 재동기 | 잠든 상태에서 재전송 → 첫 FILE_BEGIN 으로 깬 뒤 세션 3건 acked |
| 전류 | (측정 장비가 있으면) USB 전류계로 깨어 있음 vs LIGHT 평균 — 없으면 다음 단계로 |

문서: v2 §6.7 끝 메모(LIGHT 구현·실측값), progress cw-14 비고. 결과가 나쁘면(미수신 > 5 %) 원인(깨는 지연·duty cycle 창)을 로그로 보고 `RP_PREAMBLE_WAKE_MS` 조정은 lockstep 이라 따로 결정한다.

## Self-Review

- §6.7 LIGHT 빌드 플래그·duty cycle·DIO1·타이머 깨우기, §6.3 상태키 + 같은 화면, 30 min 상한(30 분 TIME 과 같은 주기). deep sleep·버튼 깨우기·3.3 V 렌더 중단은 3b.
- 기본 빌드는 시연 그대로(같은 화면 건너뛰기만 — 화면이 같으니 눈에 보이는 차이 없음).

# 노드 저장·판정 교체 (절전 작업 0단계) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 노드 펌웨어의 임시 저장(`/state.bin` 통째 저장)·임시 판정(`nc::decide`)을 dh-08(#119)의 `lib/node_store`(NVS·LittleFS·RTC 캐시)와 `lib/schedule`(`determineLayout`·`nextChangeAt`)로 바꾼다. 화면·무선 동작은 그대로 두고, 1단계(상향 메시지)·3단계(딥슬립)가 기댈 RTC 캐시 기반을 만든다.

**Architecture:** `lib/node_core` 는 "프레임 → NodeStore 호출 → ACK 결정"과 "RtcState → RenderModel" 두 순수 함수만 남기고, 자체 상태 구조(`nc::State`)·판정(`nc::decide`)·KST 변환은 지운다. 저장의 원본은 `ns::NodeStore`(파일·NVS, RTC 는 오늘 슬롯 캐시)이고, 판정은 `sch::determineLayout`. `src/terminal/` 에는 NVS(Preferences)·LittleFS 어댑터와 `RTC_DATA_ATTR ns::RtcState` 만 더한다. 깨어 있는 모드(현재 루프)는 유지 — 잠들기는 3단계.

**Tech Stack:** C++17, PlatformIO(`[env:native]` Unity 테스트, `[env:terminal]` ESP32-S3), Arduino-ESP32 Preferences·LittleFS, RadioLib 7.1.2, GxEPD2 1.6.2

## Global Constraints

- `lora_proto/` 는 바꾸지 않는다(계약 변경 없음). 상수는 `LP_*`·`ns::kResvMax`·`ns::kExamMax` 만 쓴다 — `nc::kResvMax`·`nc::kExamMax` 는 지운다.
- `lib/node_store/`·`lib/schedule/` 은 dh·cw 공동 소유 — 이 계획에서는 **고치지 않는다**(쓰기만 한다).
- 판정 규칙은 v2 §5.3 · `lora_proto/room_state_vectors.json` 그대로(쉬는시간 틈 0 < g ≤ 15분, 예약 > 시험기간 수업 > 수업).
- 오늘 목록: 연속 교시 한 행(과목명 바이트 일치·type 같음·틈 0–15분), 현재 행 = cur 를 포함하는 행(#142·#143) — 그대로 유지.
- ACK 는 저장이 끝난 뒤 렌더 전에(v2 §6.4). lastTxn 은 저장 결과 OK·GAP 일 때만 기록(#74 10). TIME 은 DUP 판정 안 함.
- 화면은 시계가 유효(epoch > 1,700,000,000)할 때만 그린다.
- 펌웨어 버전 `FW_VER` 2 → 3.
- 커밋 형식 `feat(firmware):` / `refactor(firmware):`, Windows 로컬 `pio test` 는 Unity setUp/tearDown 링크 문제로 렌더 계열이 안 도는 것이 기존 상태(이 계획의 테스트 파일은 setUp/tearDown 을 정의하므로 로컬에서 돈다).

## 파일 구조

| 파일 | 변경 | 책임 |
|---|---|---|
| `firmware/lib/node_core/node_core.h` | 수정 | `isForMe`·`gap`·`FileRx`·`Outcome`·`handleFrame(NodeStore&…)`·`buildModel(RtcState…)` 만 |
| `firmware/lib/node_core/node_core.cpp` | 수정 | 위 구현. `State`·`decide`·`toKst`·`replaceKind`(자체) 삭제 |
| `firmware/test/test_node_core/test_main.cpp` | 재작성 | FakeKv·FakeFile·RtcState 위에서 수신·모델 시험 |
| `firmware/src/terminal/esp_store.h` | 신규 | `EspKv`(Preferences)·`LittleFsFiles`(원자 쓰기) |
| `firmware/src/terminal/main.cpp` | 수정 | `/state.bin` 저장 제거, NodeStore·RTC 캐시 연결, 날짜 바뀜 처리, ACK·렌더 키 |
| `docs/specs/2026-09-09-lora-v2-wor-design.md` | 수정(한 줄) | §5.1 "노드 펌웨어가 node_store 를 쓴다(2026-11)" 메모 |

---

### Task 1: 수신 처리를 NodeStore 위로 (`nc::handleFrame`)

**Files:**
- Modify: `firmware/lib/node_core/node_core.h`
- Modify: `firmware/lib/node_core/node_core.cpp:1-245`(수신 부분)
- Test: `firmware/test/test_node_core/test_main.cpp`(수신 시험 부분 재작성)

**Interfaces:**
- Consumes: `ns::NodeStore`(`applySlotSet/Del`·`applyDayClear`·`applyResvSet/Del`·`applyExamSet/Del`·`replaceKind`·`setLastTxn`·`state()`), `ns::Date`, `sch::toKst(uint32_t)` → `sch::KstTime`
- Produces:
  ```cpp
  namespace nc {
  constexpr uint8_t kNoAck = 0xFF;
  constexpr uint32_t kClockValidEpoch = 1700000000u;
  constexpr uint16_t kFileMax = ns::kSchedFileMax;  // 5,184 B — 가장 큰 FILE 본문
  constexpr uint8_t kFileChunksMax = kFileMax / LP_FILE_CHUNK_MAX + 1;
  struct Ident { uint8_t bld; uint16_t room; uint8_t unit; };
  struct FileRx { bool active; uint8_t kind, newVer, nChunks; uint16_t len; bool have[kFileChunksMax]; uint8_t buf[kFileMax]; };
  struct Outcome { uint8_t status = kNoAck; uint8_t detail = 0; bool changed = false; bool timeSet = false; uint32_t epoch = 0; };
  bool isForMe(const Ident&, const lc::Header&);
  bool gap(uint8_t oldVer, uint8_t newVer);
  ns::Date todayOf(uint32_t epochUtc);  // KST 날짜, ResvRec 와 같은 표현(y = year-2000)
  Outcome handleFrame(ns::NodeStore&, FileRx&, const lc::Header&, const uint8_t* payload, uint32_t nowEpoch);
  }
  ```

- [ ] **Step 1: 테스트 파일 머리·도우미를 새 저장 계층용으로 바꾼다**

`firmware/test/test_node_core/test_main.cpp` 맨 위(include 부터 `slotSet` 도우미까지)를 아래로 교체한다. 기존 `hdr()`·`run()`·`slot()`·`slotSet()` 이름은 유지해 아래 시험 본문 수정을 최소로 한다.

```cpp
// 노드 순수 로직 — 수신(v2 §3.4·3.5·6.4·6.6)은 ns::NodeStore 위에서, 화면 모델은 RtcState + sch 판정(§5.3).
#include <unity.h>

#include <cstring>
#include <memory>

#include "fake_store.h"
#include "kst_time.h"
#include "lora_codec.h"
#include "node_core.h"
#include "node_store.h"

using namespace nc;

static std::unique_ptr<ns::FakeKv> KV;
static std::unique_ptr<ns::FakeFile> FS;
static std::unique_ptr<ns::RtcState> R;
static std::unique_ptr<ns::NodeStore> ST;
static std::unique_ptr<FileRx> F;
// 2026-11-19(목) 13:30 KST — 수신 시험의 "지금". 목요일 = 4
static uint32_t NOW;

static uint32_t kstEpoch(int y, int mo, int d, int h, int mi) {
  return sch::kstMidnight((uint16_t)y, (uint8_t)mo, (uint8_t)d) + (uint32_t)(h * 3600 + mi * 60);
}

void setUp() {
  KV.reset(new ns::FakeKv());
  FS.reset(new ns::FakeFile());
  R.reset(new ns::RtcState());
  ns::rtcClear(*R);
  ST.reset(new ns::NodeStore(*KV, *FS, *R));
  ST->load(4);  // 목요일 슬롯을 RTC 에
  F.reset(new FileRx());
  std::memset(F.get(), 0, sizeof(FileRx));
  NOW = kstEpoch(2026, 11, 19, 13, 30);
}
void tearDown() {}

static lc::Header hdr(uint8_t type, uint8_t txn, uint8_t flags = LP_FLAG_ACK_REQ, uint8_t bld = 'E',
                      uint16_t room = 301, uint8_t unit = 1) {
  lc::Header h{};
  h.ver = LP_PROTO_VER;
  h.flags = flags;
  h.netId = RP_NET_ID;
  h.type = type;
  h.bld = bld;
  h.room = room;
  h.unit = unit;
  h.txn = txn;
  return h;
}

static uint8_t g_pl[256];
static Outcome run(lc::Header h, size_t n) {
  h.len = (uint8_t)n;
  return handleFrame(*ST, *F, h, g_pl, NOW);
}

static lc::SlotRec slot(uint8_t day, uint8_t sH, uint8_t sM, uint8_t eH, uint8_t eM, const char* subj,
                        uint8_t type = LP_SLOTTYPE_CLASS) {
  lc::SlotRec s{};
  s.day = day, s.sH = sH, s.sM = sM, s.eH = eH, s.eM = eM, s.type = type;
  std::strncpy(s.subj, subj, LP_SUBJ_MAX);
  std::strncpy(s.prof, "교수", LP_PROF_MAX);
  return s;
}

static Outcome slotSet(uint8_t txn, uint8_t ver, const lc::SlotRec& s) {
  return run(hdr(LP_TYPE_SLOT_SET, txn), lc::encSlotSet(ver, s, g_pl, sizeof g_pl));
}
```

- [ ] **Step 2: 수신 시험 본문을 RTC 상태로 고친다**

기존 시험에서 `S->nSlots`·`S->schedVer`·`S->lastTxn`·`S->slots[i]`·`S->nResv`·`S->resvVer`·`S->nExam`·`S->examVer` 를 각각 `R->nSlots`·`R->schedVer`·`R->lastTxn`·`R->slots[i]`·`R->nResv`·`R->resvVer`·`R->nExam`·`R->examVer` 로 바꾼다. RTC 는 **오늘(목, 4) 슬롯만** 담으므로, 다른 요일 슬롯을 세던 시험은 요일을 4 로 바꾸거나 `ST->refreshDay(day)` 뒤에 센다. 아래는 그렇게 바꾼 결과다(파일의 같은 이름 시험을 이것으로 교체).

```cpp
void test_slot_set_ok_then_gap_then_dup() {
  Outcome o = slotSet(10, 1, slot(4, 9, 0, 9, 50, "자료구조"));
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_OK, o.status);
  TEST_ASSERT_TRUE(o.changed);
  TEST_ASSERT_EQUAL_UINT8(1, R->nSlots);
  TEST_ASSERT_EQUAL_UINT8(1, R->schedVer);
  TEST_ASSERT_EQUAL_UINT8(10, R->lastTxn);
  o = slotSet(11, 3, slot(4, 10, 0, 10, 50, "운영체제"));
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_GAP, o.status);  // 2 를 건너뜀 — 적용은 하고 GAP
  TEST_ASSERT_EQUAL_UINT8(2, R->nSlots);
  TEST_ASSERT_EQUAL_UINT8(11, R->lastTxn);  // GAP 도 저장 OK 라 lastTxn 기록(#74 10)
  o = slotSet(11, 3, slot(4, 10, 0, 10, 50, "운영체제"));
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_DUP, o.status);
  TEST_ASSERT_FALSE(o.changed);
}

void test_slot_set_other_day_goes_to_file_not_rtc() {
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_OK, slotSet(1, 1, slot(2, 9, 0, 9, 50, "화요일")).status);
  TEST_ASSERT_EQUAL_UINT8(0, R->nSlots);  // 오늘(목)이 아님
  TEST_ASSERT_EQUAL_UINT8(1, R->schedVer);
  TEST_ASSERT_EQUAL(ns::StoreStatus::Ok, ST->refreshDay(2));
  TEST_ASSERT_EQUAL_UINT8(1, R->nSlots);
  TEST_ASSERT_EQUAL_STRING("화요일", R->slots[0].subj);
}

void test_store_fail_keeps_version_and_last_txn() {
  for (uint8_t i = 0; i < LP_SLOT_DAY_MAX; ++i)
    TEST_ASSERT_EQUAL_HEX8(LP_ACK_OK, slotSet((uint8_t)(i + 1), (uint8_t)(i + 1),
                                              slot(4, (uint8_t)(i % 24), (uint8_t)(i / 24), (uint8_t)(i % 24), 59,
                                                   "가득"))
                                          .status);
  Outcome o = slotSet(100, 25, slot(4, 23, 30, 23, 59, "넘침"));
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_STORE_FAIL, o.status);
  TEST_ASSERT_EQUAL_UINT8(LP_SLOT_DAY_MAX, R->schedVer);  // 실패는 버전을 안 바꾼다
  TEST_ASSERT_EQUAL_UINT8(LP_SLOT_DAY_MAX, R->lastTxn);   // 실패는 lastTxn 을 안 바꾼다(#74 10)
}

void test_file_write_failure_is_store_fail() {
  FS->failWritesAfter = 0;
  Outcome o = slotSet(1, 1, slot(4, 9, 0, 9, 50, "자료구조"));
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_STORE_FAIL, o.status);
  TEST_ASSERT_FALSE(o.changed);
  TEST_ASSERT_EQUAL_UINT8(0, R->nSlots);
}
```

`test_slot_set_same_key_replaces`·`test_slot_del_and_day_clear`·`test_resv_and_exam`·`test_time_*`·`test_no_ack_without_ack_req`·`test_bad_payload_and_unsupported`·`test_file_*`·`test_day_cap_*` 도 같은 치환(`S->` → `R->`, 슬롯 요일을 4 로, 다른 요일은 `refreshDay`)으로 고친다. `test_file_session_replaces_whole_kind` 는 60 슬롯을 7개 요일에 나눠 넣으므로 `R->nSlots` 대신 목요일 몫(`60 / 7` 반올림이 아닌, 시험이 만드는 목요일 개수)을 센다 — 시험의 슬롯 생성 식 `1 + i % 7` 에서 day 4 는 i % 7 == 3 인 것: 60개 중 9개. `test_room_state_vectors` 는 판정 벡터 대조가 `test_schedule` 로 옮겨 갔으므로 **삭제**한다.

- [ ] **Step 3: 시험을 돌려 컴파일 실패를 확인한다**

Run: `cd firmware && pio test -e native -f test_node_core`
Expected: FAIL — `handleFrame` 인자 수 불일치, `State` 미정의 등 컴파일 오류

- [ ] **Step 4: `node_core.h` 수신 부분을 새 인터페이스로 바꾼다**

`node_core.h` 의 `kResvMax`·`kExamMax`·`kFileMax`·`State`·`clear`·`Item`·`Decision`·`decide`·`Kst`·`toKst` 를 지우고, 위 **Interfaces → Produces** 블록 그대로 선언한다. include 에 `node_store.h` 를 더한다. `buildModel` 선언은 Task 2 에서 바꾸므로 일단 지운다.

- [ ] **Step 5: `node_core.cpp` 수신 구현**

`clear`·자체 `replaceKind`·`apply`·`handleFrame` 을 지우고 아래로 교체한다(`isForMe`·`gap` 은 그대로 둔다).

```cpp
ns::Date todayOf(uint32_t epochUtc) {
  const sch::KstTime k = sch::toKst(epochUtc);
  return ns::Date{(uint8_t)(k.year - 2000), k.month, k.day};
}

namespace {

// 저장 결과 → ACK. Ok 면 버전 연속성으로 OK/GAP(§12, #74 12)
uint8_t ackOf(ns::StoreStatus st, uint8_t oldVer, uint8_t newVer) {
  switch (st) {
    case ns::StoreStatus::Ok:
      return gap(oldVer, newVer) ? LP_ACK_GAP : LP_ACK_OK;
    case ns::StoreStatus::StoreFail:
      return LP_ACK_STORE_FAIL;
    case ns::StoreStatus::BadPayload:
      return LP_ACK_BAD_PAYLOAD;
    default:
      return LP_ACK_UNSUPPORTED;
  }
}

uint8_t apply(ns::NodeStore& st, FileRx& f, const lc::Header& h, const uint8_t* p, uint32_t now, Outcome& o) {
  const ns::RtcState& r = st.state();
  const bool clockOk = now > kClockValidEpoch;
  const ns::Date today = todayOf(now);
  uint8_t v = 0, rc;
  switch (h.type) {
    case LP_TYPE_TIME: {
      lc::Time t{};
      if (!lc::decTime(p, h.len, t)) return LP_ACK_BAD_PAYLOAD;
      o.timeSet = true;
      o.epoch = t.epoch;
      return LP_ACK_OK;
    }
    case LP_TYPE_SLOT_SET: {
      lc::SlotRec x{};
      if (!lc::decSlotSet(p, h.len, v, x)) return LP_ACK_BAD_PAYLOAD;
      const uint8_t old = r.schedVer;
      rc = ackOf(st.applySlotSet(v, x), old, v);
      break;
    }
    case LP_TYPE_SLOT_DEL: {
      lc::SlotDel x{};
      if (!lc::decSlotDel(p, h.len, v, x)) return LP_ACK_BAD_PAYLOAD;
      const uint8_t old = r.schedVer;
      rc = ackOf(st.applySlotDel(v, x), old, v);
      break;
    }
    case LP_TYPE_DAY_CLEAR: {
      lc::DayClear x{};
      if (!lc::decDayClear(p, h.len, v, x)) return LP_ACK_BAD_PAYLOAD;
      const uint8_t old = r.schedVer;
      rc = ackOf(st.applyDayClear(v, x), old, v);
      break;
    }
    case LP_TYPE_RESV_SET: {
      lc::ResvRec x{};
      if (!lc::decResvSet(p, h.len, v, x)) return LP_ACK_BAD_PAYLOAD;
      const uint8_t old = r.resvVer;
      rc = ackOf(st.applyResvSet(v, x, today, clockOk), old, v);
      break;
    }
    case LP_TYPE_RESV_DEL: {
      lc::ResvDel x{};
      if (!lc::decResvDel(p, h.len, v, x)) return LP_ACK_BAD_PAYLOAD;
      const uint8_t old = r.resvVer;
      rc = ackOf(st.applyResvDel(v, x), old, v);
      break;
    }
    case LP_TYPE_EXAM_SET: {
      lc::ExamRec x{};
      if (!lc::decExamSet(p, h.len, v, x)) return LP_ACK_BAD_PAYLOAD;
      const uint8_t old = r.examVer;
      rc = ackOf(st.applyExamSet(v, x), old, v);
      break;
    }
    case LP_TYPE_EXAM_DEL: {
      lc::ExamDel x{};
      if (!lc::decExamDel(p, h.len, v, x)) return LP_ACK_BAD_PAYLOAD;
      const uint8_t old = r.examVer;
      rc = ackOf(st.applyExamDel(v, x), old, v);
      break;
    }
    case LP_TYPE_FILE_BEGIN: {
      lc::FileBegin b{};
      if (!lc::decFileBegin(p, h.len, f.newVer, b) || b.totalLen > kFileMax || b.nChunks > kFileChunksMax ||
          (uint32_t)b.nChunks * LP_FILE_CHUNK_MAX < b.totalLen)
        return LP_ACK_BAD_PAYLOAD;
      f.active = true;
      f.kind = b.kind;
      f.len = b.totalLen;
      f.nChunks = b.nChunks;
      memset(f.have, 0, sizeof f.have);
      return LP_ACK_OK;
    }
    case LP_TYPE_FILE_DATA: {
      lc::FileData d{};
      if (!f.active || !lc::decFileData(p, h.len, d) || d.seq >= f.nChunks) return LP_ACK_BAD_PAYLOAD;
      const uint32_t off = (uint32_t)d.seq * LP_FILE_CHUNK_MAX;
      if (off + d.len > f.len) return LP_ACK_BAD_PAYLOAD;
      memcpy(f.buf + off, d.data, d.len);
      f.have[d.seq] = true;
      return LP_ACK_OK;
    }
    case LP_TYPE_FILE_END: {
      lc::FileEnd e{};
      if (!f.active || !lc::decFileEnd(p, h.len, e)) return LP_ACK_BAD_PAYLOAD;
      for (uint8_t i = 0; i < f.nChunks; ++i)
        if (!f.have[i]) {
          o.detail = i;
          return LP_ACK_FILE_MISSING;
        }
      if (lc::crc16(f.buf, f.len) != e.crc) return LP_ACK_BAD_CRC;
      const ns::StoreStatus s = st.replaceKind(f.kind, f.newVer, f.buf, f.len, today, clockOk);
      if (s != ns::StoreStatus::Ok) return ackOf(s, 0, 0);
      f.active = false;
      o.changed = true;
      return LP_ACK_OK;  // FILE 은 전체 교체 — GAP 없음(§3.3)
    }
    default:  // CMD·SET_ROOM·SET_PARAM 은 2단계(프로비저닝)
      return LP_ACK_UNSUPPORTED;
  }
  if (rc == LP_ACK_OK || rc == LP_ACK_GAP) o.changed = true;
  return rc;
}

}  // namespace

Outcome handleFrame(ns::NodeStore& st, FileRx& f, const lc::Header& h, const uint8_t* p, uint32_t nowEpoch) {
  Outcome o;
  uint8_t s;
  if (h.type != LP_TYPE_TIME && h.txn != 0 && h.txn == st.state().lastTxn) {
    s = LP_ACK_DUP;  // 재적용 없이 ACK 만(§3.5)
  } else {
    s = apply(st, f, h, p, nowEpoch, o);
    // lastTxn 은 저장 결과가 OK(GAP 포함)일 때만(#74 10). TIME 은 건드리지 않는다(§3.5)
    if (h.type != LP_TYPE_TIME && h.txn != 0 && (s == LP_ACK_OK || s == LP_ACK_GAP)) (void)st.setLastTxn(h.txn);
  }
  const bool wantAck = (h.flags & LP_FLAG_ACK_REQ) && !(h.flags & LP_FLAG_BROADCAST) && h.bld != LP_BLD_ALL;
  o.status = wantAck ? s : kNoAck;
  return o;
}
```

include 에 `#include "kst_time.h"` 를 더한다. `setLastTxn` 실패는 무시한다 — 데이터는 이미 저장됐고, lastTxn 을 놓치면 같은 프레임이 다시 와도 멱등 적용될 뿐이다(주석으로 남긴다).

- [ ] **Step 6: 수신 시험 통과 확인**

Run: `cd firmware && pio test -e native -f test_node_core`
Expected: 수신 시험 PASS(모델 시험은 Task 2 전이라 이 단계에서는 `#if 0` 으로 잠시 막아 둔다 — Step 2 에서 모델 시험 블록을 `#if 0 … #endif` 로 감싼다)

- [ ] **Step 7: Commit**

```bash
git add firmware/lib/node_core firmware/test/test_node_core
git commit -m "refactor(firmware): 노드 수신 처리를 ns::NodeStore 위로 — 자체 State·replaceKind 제거"
```

---

### Task 2: 화면 모델을 RtcState + `sch::determineLayout` 으로 (`nc::buildModel`)

**Files:**
- Modify: `firmware/lib/node_core/node_core.h`, `firmware/lib/node_core/node_core.cpp`(판정·모델 부분)
- Test: `firmware/test/test_node_core/test_main.cpp`(모델 시험)

**Interfaces:**
- Consumes: `ns::RtcState`, `sch::ScheduleView`, `sch::determineLayout`, `sch::LayoutDecision`(`layout`·`by`·`index`·`day`·`slotStartMin`), `sch::toKst`, Task 1 의 `nc::todayOf`
- Produces:
  ```cpp
  // r 의 정체성·오늘 슬롯(r.slotsDay 가 오늘 요일과 다르면 슬롯 없음으로 본다)·예약·시험으로 m 을 채운다.
  sch::LayoutDecision buildModel(const ns::RtcState& r, uint32_t epochUtc, RenderModel& m);
  ```

- [ ] **Step 1: 모델 시험을 새 시그니처로 쓴다**

Task 1 Step 2 에서 `#if 0` 으로 막은 모델 시험 블록을 풀고, `buildModel(ME, *S, epoch, m)` 호출을 `buildModel(*R, epoch, m)` 으로 바꾼다. 반환값 `d.until` 을 보던 `test_model_class_fills_cur_next_today` 는 `d.slotStartMin`·`d.by` 로 바꾼다. 아래 두 시험을 더한다.

```cpp
void test_model_identity_from_rtc() {
  R->bld = 'E';
  R->room = 803;
  R->unit = 1;
  RenderModel m;
  buildModel(*R, kstEpoch(2026, 11, 19, 13, 30), m);
  TEST_ASSERT_EQUAL('E', m.bld);
  TEST_ASSERT_EQUAL_UINT16(803, m.room);
  TEST_ASSERT_EQUAL_UINT8(1, m.unit);
  TEST_ASSERT_EQUAL_STRING("11.19", m.dateStr);
  TEST_ASSERT_EQUAL_UINT8(4, m.weekday);
}

void test_model_ignores_stale_rtc_day() {
  slotSet(1, 1, slot(4, 13, 0, 14, 50, "목요일 수업"));
  RenderModel m;
  // 금요일 13:30 — RTC 는 아직 목요일 슬롯(어댑터가 refreshDay 하기 전). 목요일 수업을 금요일에 보이면 안 된다
  sch::LayoutDecision d = buildModel(*R, kstEpoch(2026, 11, 20, 13, 30), m);
  TEST_ASSERT_EQUAL_UINT8(LP_LAYOUT_EMPTY, d.layout);
  TEST_ASSERT_EQUAL_UINT8(0, m.nToday);
}
```

`test_model_class_fills_cur_next_today` 는 다음처럼(목요일 슬롯 3개 + 수요일 1개):

```cpp
void test_model_class_fills_cur_next_today() {
  R->bld = 'E', R->room = 301, R->unit = 1;
  slotSet(1, 1, slot(4, 9, 0, 10, 50, "자료구조"));
  slotSet(2, 2, slot(4, 13, 0, 14, 50, "임베디드SW"));
  slotSet(3, 3, slot(4, 16, 0, 18, 50, "캡스톤디자인"));
  slotSet(4, 4, slot(3, 13, 0, 14, 50, "다른 요일"));
  RenderModel m;
  sch::LayoutDecision d = buildModel(*R, kstEpoch(2026, 11, 19, 13, 30), m);
  TEST_ASSERT_EQUAL_UINT8(LP_LAYOUT_CLASS, m.layout);
  TEST_ASSERT_EQUAL_UINT16(13 * 60, d.slotStartMin);
  TEST_ASSERT_EQUAL_STRING("임베디드SW", m.cur.subj);
  TEST_ASSERT_EQUAL_STRING("캡스톤디자인", m.next.subj);
  TEST_ASSERT_EQUAL_UINT8(3, m.nToday);
  TEST_ASSERT_EQUAL_STRING("자료구조", m.today[0].subj);
}
```

나머지 모델 시험(`test_model_break_cur_is_next`·`test_model_resv_today_beats_slot`·`test_model_exam_period`·`test_today_merges_periods_of_same_section_only`·`test_today_merge_keeps_break_per_period`·`test_today_merge_rules_gap_type_and_contiguous`)은 호출만 `buildModel(*R, epoch, m)` 으로 바꾸고 기대값은 그대로 둔다. `test_model_resv_today_beats_slot` 의 "다음날(금)" 확인은 금요일 epoch 를 그대로 쓰면 된다(RTC 가 목요일이라 위 stale 규칙으로 빈 강의실).

- [ ] **Step 2: 시험 실패 확인**

Run: `cd firmware && pio test -e native -f test_node_core`
Expected: FAIL — `buildModel(const ns::RtcState&, …)` 미정의

- [ ] **Step 3: `buildModel` 구현**

`node_core.cpp` 의 `typeToLayout`·`stateAt`·`decide`·`toKst`(자체)·기존 `buildModel` 을 지우고 아래로 교체한다. `fillSlot` 은 그대로 둔다.

```cpp
namespace {

struct Item {
  uint16_t s, e;  // 자정부터 분
  uint8_t type;
  bool resv;
  uint8_t idx;  // r.slots / r.resv 위치
};

}  // namespace

sch::LayoutDecision buildModel(const ns::RtcState& r, uint32_t epochUtc, RenderModel& m) {
  memset(&m, 0, sizeof m);
  m.bld = (char)r.bld;
  m.room = r.room;
  m.unit = r.unit;
  const sch::KstTime k = sch::toKst(epochUtc);
  char ds[12];
  snprintf(ds, sizeof ds, "%02u.%02u", k.month, k.day);
  memcpy(m.dateStr, ds, sizeof m.dateStr - 1);
  m.weekday = k.weekday;
  const uint16_t nowMin = sch::minuteOfDay(k);

  // RTC 슬롯이 오늘 요일 것일 때만 쓴다 — 자정 직후 어댑터가 refreshDay 하기 전엔 빈 것으로 본다
  const uint8_t nSlots = r.slotsDay == k.weekday ? r.nSlots : 0;
  const sch::ScheduleView v{r.slots, nSlots, r.resv, r.nResv, r.exams, r.nExam};
  const sch::LayoutDecision d = sch::determineLayout(v, epochUtc);
  m.layout = d.layout;

  static Item it[LP_SLOT_DAY_MAX + ns::kResvMax];
  int n = 0;
  for (uint8_t i = 0; i < nSlots; ++i)
    it[n++] = {(uint16_t)(r.slots[i].sH * 60 + r.slots[i].sM), (uint16_t)(r.slots[i].eH * 60 + r.slots[i].eM),
               r.slots[i].type, false, i};
  const ns::Date today = todayOf(epochUtc);
  for (uint8_t i = 0; i < r.nResv; ++i)
    if (r.resv[i].y == today.y && r.resv[i].m == today.m && r.resv[i].d == today.d)
      it[n++] = {(uint16_t)(r.resv[i].sH * 60 + r.resv[i].sM), (uint16_t)(r.resv[i].eH * 60 + r.resv[i].eM),
                 r.resv[i].type, true, i};
  int ord[LP_SLOT_DAY_MAX + ns::kResvMax];
  for (int i = 0; i < n; ++i) ord[i] = i;
  std::stable_sort(ord, ord + n, [&](int a, int b) { return it[a].s < it[b].s; });
  auto subjOf = [&](const Item& x) { return x.resv ? r.resv[x.idx].subj : r.slots[x.idx].subj; };
  auto profOf = [&](const Item& x) { return x.resv ? r.resv[x.idx].prof : r.slots[x.idx].prof; };

  // 오늘 목록 — 연속 교시 한 행(terminal-epaper.md 「오늘 목록」, #143). 판정은 교시 단위 그대로
  for (int j = 0; j < n; ++j) {
    const Item& x = it[ord[j]];
    if (m.nToday > 0) {
      TodaySlot& p = m.today[m.nToday - 1];
      const int pe = p.eH * 60 + p.eM;
      const int g = (int)x.s - pe;
      if (p.type == x.type && g >= 0 && g <= LP_BREAK_GAP_MAX_MIN &&
          strncmp(p.subj, subjOf(x), sizeof p.subj) == 0) {
        if ((int)x.e > pe) p.eH = (uint8_t)(x.e / 60), p.eM = (uint8_t)(x.e % 60);
        continue;
      }
    }
    if (m.nToday >= 24) break;
    TodaySlot& t = m.today[m.nToday++];
    t.sH = (uint8_t)(x.s / 60), t.sM = (uint8_t)(x.s % 60), t.eH = (uint8_t)(x.e / 60),
    t.eM = (uint8_t)(x.e % 60);
    strncpy(t.subj, subjOf(x), sizeof t.subj - 1);
    t.type = x.type;
  }

  // cur: 판정한 항목(쉬는시간이면 곧 시작할 수업 — cur = next, #89). next: 그 뒤 처음 시작하는 항목
  int curIt = -1;
  for (int i = 0; i < n; ++i) {
    const bool isResv = d.by == sch::Decider::Resv;
    const bool isSlot = d.by == sch::Decider::Slot || d.by == sch::Decider::ExamSlot || d.by == sch::Decider::Break;
    if ((isResv && it[i].resv && it[i].idx == d.index) || (isSlot && !it[i].resv && it[i].idx == d.index)) {
      curIt = i;
      break;
    }
  }
  if (curIt >= 0) fillSlot(m.cur, subjOf(it[curIt]), profOf(it[curIt]), it[curIt].s, it[curIt].e, it[curIt].type);
  if (d.layout == LP_LAYOUT_BREAK) {
    m.next = m.cur;
  } else {
    const uint16_t after = curIt >= 0 ? it[curIt].e : nowMin;
    for (int j = 0; j < n; ++j) {
      const Item& x = it[ord[j]];
      if (ord[j] != curIt && (curIt >= 0 ? x.s >= after : x.s > after)) {
        fillSlot(m.next, subjOf(x), profOf(x), x.s, x.e, x.type);
        break;
      }
    }
  }
  return d;
}
```

include 에 `#include "schedule.h"` 를 더한다. `node_core.h` 에 Interfaces 의 선언을 넣는다.

- [ ] **Step 4: 시험 통과 확인**

Run: `cd firmware && pio test -e native -f test_node_core -f test_schedule -f test_node_store`
Expected: 모두 PASS

- [ ] **Step 5: clang-format·정적 분석 확인**

Run: `cd firmware && clang-format --dry-run --Werror lib/node_core/*.cpp lib/node_core/*.h test/test_node_core/test_main.cpp && pio check -e native --skip-packages`
Expected: 출력 없음 / 결함 0

- [ ] **Step 6: Commit**

```bash
git add firmware/lib/node_core firmware/test/test_node_core
git commit -m "refactor(firmware): 노드 화면 모델을 RtcState + sch::determineLayout 으로 — 자체 decide·toKst 제거"
```

---

### Task 3: ESP 저장 어댑터 (`EspKv`·`LittleFsFiles`)

**Files:**
- Create: `firmware/src/terminal/esp_store.h`

**Interfaces:**
- Consumes: `ns::KvStore`·`ns::FileStore`·`ns::ReadResult`(store_port.h)
- Produces: `class EspKv : public ns::KvStore`, `class LittleFsFiles : public ns::FileStore` — 기본 생성자, `LittleFS.begin()` 은 호출자가 먼저 한다

실기 전용(Arduino 헤더)이라 호스트 단위 시험 대상이 아니다. 계약은 `fake_store.h` 와 같고, 검증은 Task 5 실기.

- [ ] **Step 1: 어댑터 작성**

```cpp
// ns::KvStore·ns::FileStore 의 실기 어댑터 — NVS(Preferences)·LittleFS. 계약은 lib/node_store/store_port.h,
// 동작 기준은 fake_store.h(테스트 fake)와 같다.
#pragma once

#include <LittleFS.h>
#include <Preferences.h>

#include "store_port.h"

class EspKv : public ns::KvStore {
 public:
  bool get(const char* space, const char* key, uint32_t& out) override {
    Preferences p;
    if (!p.begin(space, true)) return false;  // 이름공간이 아직 없으면 false — "없음"과 같다
    const bool has = p.isKey(key);
    if (has) out = p.getUInt(key, 0);
    p.end();
    return has;
  }
  bool set(const char* space, const char* key, uint32_t v) override {
    Preferences p;
    if (!p.begin(space, false)) return false;
    const bool ok = p.putUInt(key, v) == sizeof(uint32_t);
    p.end();
    return ok;
  }
  bool eraseSpace(const char* space) override {
    Preferences p;
    if (!p.begin(space, false)) return false;
    const bool ok = p.clear();
    p.end();
    return ok;
  }
};

class LittleFsFiles : public ns::FileStore {
 public:
  ns::ReadResult read(const char* path, uint8_t* buf, size_t cap, size_t& len) override {
    if (!LittleFS.exists(path)) return ns::ReadResult::NotFound;
    File f = LittleFS.open(path, "r");
    if (!f) return ns::ReadResult::Fail;
    const size_t sz = f.size();
    if (sz > cap) {
      f.close();
      return ns::ReadResult::Fail;
    }
    len = f.read(buf, sz);
    f.close();
    return len == sz ? ns::ReadResult::Ok : ns::ReadResult::Fail;
  }
  // 임시 파일에 쓰고 rename — 중간에 끊기면 옛 파일이 그대로 남는다(LittleFS rename 은 대상을 덮는다)
  bool writeAtomic(const char* path, const uint8_t* data, size_t len) override {
    char tmp[40];
    snprintf(tmp, sizeof tmp, "%s.tmp", path);
    File f = LittleFS.open(tmp, "w");
    if (!f) return false;
    const bool ok = f.write(data, len) == len;
    f.close();
    return ok && LittleFS.rename(tmp, path);
  }
  bool remove(const char* path) override { return !LittleFS.exists(path) || LittleFS.remove(path); }
};
```

- [ ] **Step 2: 빌드만 확인**

Run: `cd firmware && pio run -e terminal`
Expected: Task 4 전이라 main.cpp 가 아직 `nc::State` 를 써서 실패 — 이 단계는 Task 4 와 함께 빌드한다(커밋은 Task 4 와 같이)

---

### Task 4: 노드 어댑터 연결 (`src/terminal/main.cpp`)

**Files:**
- Modify: `firmware/src/terminal/main.cpp`

**Interfaces:**
- Consumes: Task 1·2 의 `nc::handleFrame`·`nc::buildModel`·`nc::todayOf`, Task 3 의 `EspKv`·`LittleFsFiles`, `ns::NodeStore`·`ns::RtcState`·`ns::Identity`, `sch::toKst`
- Produces: 동작 — RTC 캐시가 소프트 리셋을 넘어 산다(`RTC_DATA_ATTR`), 날짜가 바뀌면 오늘 슬롯을 다시 채운다, 화면 상태키를 `RtcState.lastLayout/lastDay/lastSlotStartMin` 에 둔다(3단계 딥슬립이 그대로 쓴다)

- [ ] **Step 1: 전역 상태 교체**

`nc::State g_state, g_backup;`·`StateFileHead`·`saveState()`·`loadState()` 를 지우고 아래를 넣는다. `FW_VER` 를 3 으로 올린다.

```cpp
#include "esp_store.h"
#include "kst_time.h"
#include "node_store.h"

RTC_DATA_ATTR ns::RtcState g_rtc;  // 소프트 리셋·딥슬립을 넘어 산다. 매직·CRC 가 맞지 않으면 load() 가 재구축
EspKv g_kv;
LittleFsFiles g_fs;
ns::NodeStore g_store(g_kv, g_fs, g_rtc);
nc::FileRx g_file;

nc::Ident me() {
  return nc::Ident{g_rtc.bld, g_rtc.room, g_rtc.unit};
}
```

- [ ] **Step 2: 날짜 맞추기 함수**

```cpp
// 시계가 유효하면 RTC 의 오늘 슬롯이 오늘 요일 것인지 맞추고, 지난 예약을 정리한다. TIME 수신·매초 루프에서 부른다.
void syncDay() {
  if (!clockValid()) return;
  const uint32_t now = (uint32_t)time(nullptr);
  const uint8_t wd = sch::toKst(now).weekday;
  if (g_rtc.slotsDay != wd) {
    const ns::StoreStatus s = g_store.refreshDay(wd);
    Serial.printf("[node] 요일 %u 슬롯 다시 채움 st=%u n=%u\n", wd, (unsigned)s, g_rtc.nSlots);
    (void)g_store.purgePast(nc::todayOf(now), true);
    g_dirty = true;
  }
}
```

- [ ] **Step 3: 수신 처리 교체**

`pollRadio()` 안의 `g_backup = g_state; … saveState() …` 블록을 아래로 바꾼다(NodeStore 는 실패하면 상태를 바꾸지 않으므로 되돌리기가 필요 없다).

```cpp
  if (ok && nc::isForMe(me(), h)) {
    g_lastRxMs = millis();
    const uint32_t ts = millis();
    nc::Outcome o = nc::handleFrame(g_store, g_file, h, p, (uint32_t)time(nullptr));
    const uint32_t saveMs = millis() - ts;
    if (o.timeSet) {
      timeval tv{(time_t)o.epoch, 0};
      settimeofday(&tv, nullptr);
      g_rtc.lastTimeSyncEpoch = o.epoch;
      syncDay();
      g_dirty = true;
    }
    if (o.changed) g_dirty = true;
    if (o.status != nc::kNoAck) sendAck(h, o.status, o.detail);
    Serial.printf("[node] type=0x%02x txn=%u ACK=%d ver S%u/R%u/E%u today=%u save=%lums RSSI %.0f SNR %.1f\n",
                  h.type, h.txn, o.status == nc::kNoAck ? -1 : o.status, g_rtc.schedVer, g_rtc.resvVer,
                  g_rtc.examVer, g_rtc.nSlots, (unsigned long)saveMs, rssi, snr);
  }
```

`sendAck` 의 `g_state.schedVer/resvVer/examVer` 를 `g_rtc.` 로 바꾼다.

- [ ] **Step 4: 부팅 교체**

`setup()` 의 `loadState();` 를 아래로 바꾸고, 부팅 로그의 `ME.`·`g_state.` 를 `g_rtc.` 로 바꾼다.

```cpp
  const LoadSource src = g_store.load(clockValid() ? sch::toKst((uint32_t)time(nullptr)).weekday : 0);
  // 0단계: 정체성은 아직 빌드 플래그(NODE_*). 2단계(프로비저닝)에서 SET_ROOM 으로 바뀐다
  if (!g_rtc.provisioned || g_rtc.room != NODE_ROOM || g_rtc.bld != NODE_BLD || g_rtc.unit != NODE_UNIT)
    (void)g_store.setIdentity(ns::Identity{NODE_BLD, NODE_ROOM, NODE_UNIT}, 0);
  (void)LittleFS.remove("/state.bin");  // 0단계 전(임시 형식) 파일 — 버전 0 으로 시작해 서버가 재동기
  ns::rtcSeal(g_rtc);
  Serial.printf("[node] 저장 %s\n", src == ns::LoadSource::RtcCache ? "RTC 캐시" : "재구축");
```

`using ns::LoadSource;` 대신 위처럼 `ns::` 를 붙인다. `ME` 상수는 지운다(`me()` 로 대체).

- [ ] **Step 5: 루프 교체**

`loop()` 의 시계 확인 뒤 부분을 아래로 바꾼다.

```cpp
  if (!clockValid()) return;  // 시계 전엔 그리지 않는다 — 마지막 화면 유지
  syncDay();
  static RenderModel m;
  const uint32_t now = (uint32_t)time(nullptr);
  const sch::LayoutDecision d = nc::buildModel(g_rtc, now, m);
  m.battMv = BATT_MV_USB;
  // 상태키(v2 §6.3) — 레이아웃·요일·상태를 정한 항목의 시작. 다르면 다시 그린다
  const bool keyChanged =
      d.layout != g_rtc.lastLayout || d.day != g_rtc.lastDay || d.slotStartMin != g_rtc.lastSlotStartMin;
  if (keyChanged) g_dirty = true;
  if (g_dirty && millis() - g_lastRxMs > QUIET_MS) {
    g_dirty = false;
    g_rtc.lastLayout = d.layout;
    g_rtc.lastDay = d.day;
    g_rtc.lastSlotStartMin = d.slotStartMin;
    ns::rtcSeal(g_rtc);
    g_layout = m.layout;
    Serial.printf("[node] 렌더 layout=%u today=%u next=%lu\n", m.layout, m.nToday,
                  (unsigned long)sch::nextChangeAt(
                      sch::ScheduleView{g_rtc.slots, g_rtc.nSlots, g_rtc.resv, g_rtc.nResv, g_rtc.exams, g_rtc.nExam},
                      now, g_rtc.nextStatusEpoch));
    const uint32_t t0 = millis();
    render(m);
    Serial.printf("[node] 렌더 끝 %lu ms\n", (unsigned long)(millis() - t0));
  }
```

`#include "schedule.h"` 를 더한다. `[env:terminal]` 의 `lib_ignore` 는 그대로(node_store·schedule 은 LDF 가 include 로 찾는다).

- [ ] **Step 6: 빌드 확인**

Run: `cd firmware && pio run -e terminal`
Expected: SUCCESS, RAM·Flash 사용률 출력(기존 37.5 %·43.1 % 근처)

- [ ] **Step 7: Commit**

```bash
git add firmware/src/terminal
git commit -m "feat(firmware): 노드가 ns::NodeStore(NVS·LittleFS·RTC 캐시)와 sch 판정을 쓴다 — /state.bin 임시 저장 제거, FW 3"
```

---

### Task 5: 두 노드 실기 회귀 + 기록

**Files:**
- Modify: `docs/specs/2026-09-09-lora-v2-wor-design.md`(§5.1 끝에 한 줄)
- Modify: `docs/progress.html`(cw-14 비고)

- [ ] **Step 1: 두 노드 굽기**

Run:
```bash
cd firmware
pio run -e terminal -t upload --upload-port <E301 포트>
PLATFORMIO_BUILD_FLAGS="-DNODE_ROOM=803" pio run -e terminal -t upload --upload-port <E803 포트>
```
Expected: 부팅 로그 `[node] 저장 재구축`, `ver S0/R0/E0`(옛 `/state.bin` 은 버림)

- [ ] **Step 2: 재동기**

관리자 웹 노드 상태 → 두 방 **재전송**(또는 모뎀Pi 재시작으로 TIME 후 재전송). Expected: FILE 3건씩 첫 시도 `acked`, 부팅 로그 다음에 `요일 N 슬롯 다시 채움`, 화면 렌더

- [ ] **Step 3: 회귀 확인표**

| 확인 | 기대 |
|---|---|
| 803 오늘 목록 | 같은 반 연속 교시 한 행, 반이 다르면 두 행 |
| 수업 중 → 쉬는시간 → 다음 교시 | 화면이 경계마다 바뀜(상태키) |
| 노드 RST(소프트 리셋) 후 | 로그 `저장 RTC 캐시`, 시각 받기 전 화면 유지, TIME 후 바로 그림 |
| 전원 분리 후 재부팅 | 로그 `저장 재구축`, 버전 그대로(파일·NVS), 재동기 없이 화면 |
| 시간표 한 칸 바꾸기(웹) | `acked`, 지연 기존과 같은 수준(≈4.5 s) |
| 저장 시간 | 로그 `save=` 가 수십~수백 ms |

- [ ] **Step 4: 문서**

v2 §5.1 끝에 추가: `- 노드 펌웨어는 2026-11 부터 lib/node_store(파일·NVS·RTC 캐시)와 lib/schedule(판정)을 쓴다(#119, 절전 0단계). 옛 /state.bin 은 부팅 때 지운다.` progress.html cw-14 비고에 이 PR 번호를 더한다.

- [ ] **Step 5: Commit · PR**

```bash
git add docs
git commit -m "docs: 노드가 node_store·schedule 을 쓴다(절전 0단계) — v2 §5.1·진행도"
```
PR 본문에 회귀 확인표 결과와 RAM·Flash 를 붙인다.

---

## Self-Review

- **스펙 대조:** 저장(§5.1 write-through·RTC 캐시) → Task 1·4, 판정(§5.3) → Task 2, 상태키(§6.3) → Task 4 Step 5, 재부팅 복원 → Task 4·5. 딥슬립·상향 메시지·프로비저닝은 범위 밖(1·3·2단계).
- **이름 일치:** `handleFrame(ns::NodeStore&, FileRx&, const lc::Header&, const uint8_t*, uint32_t)`, `buildModel(const ns::RtcState&, uint32_t, RenderModel&) → sch::LayoutDecision`, `todayOf(uint32_t) → ns::Date` 를 Task 1·2·4 에서 같게 썼다.
- **알려진 영향:** 펌웨어 갱신 직후 버전이 0 이라 첫 변경은 GAP → 서버가 FILE 재동기(또는 Step 2 재전송). 쉬는시간 상태키가 "다음 슬롯 시작"으로 바뀌어 갱신 직후 한 번 더 그릴 수 있다(#119 리뷰). 오늘 목록이 RTC 의 오늘 슬롯(최대 24)만 본다 — 기존과 같음(하루 상한 24).

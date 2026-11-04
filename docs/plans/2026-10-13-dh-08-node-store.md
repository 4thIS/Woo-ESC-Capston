# dh-08 — S8 노드 저장 계층 + `determineLayout`·`nextChangeAt` — 구현 계획 (plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

- 생성일시: 2026-10-13, 최종 갱신: 2026-11-04
- 상태: **완성 — 구현 진행 중, cw 리뷰 대기.** 이슈 #74의 결정(cw 댓글 2026-10-12·10-14·11-03·11-04 반영표)과 PR #78·#79·#103·#109·#111 머지본 기준.
- 기준 spec: `docs/specs/2026-09-09-lora-v2-wor-design.md` §3.3·§3.4·§3.5·§5.1–§5.4·§6.3·§6.4·§10.1 (`main` `842ef8d`, #111 개정본), 로드맵 §5 S8, `docs/design/screens/terminal-epaper.md`(쉬는시간 `cur` = `next`, #109)
- 결정 근거: 이슈 #74(코드 위치·저장 인터페이스·쉬는시간 틈 규칙·담당·RTC 분담·ACK 순서·상한·추가 질문 7–12), #14(쉬는시간 — #74로 닫힘), #34(`lib/` 배치 선례), #89(쉬는시간 `cur` = 다음 슬롯)
- 표기: `[확인]` 이 작업에서 직접 실행·열람 / `[계산]` 확인한 값으로 계산 / `[추정]` 확인 안 함 / ⚠️ 플랜이 정함 — 검토 대상

**Goal:** ESP노드가 받은 시간표·예약·시험기간·정체성·버전을 NVS·LittleFS·RTC 캐시에 보관하는 저장 계층과, 그 데이터로 현재 화면 상태(`determineLayout`)와 다음 웨이크 시각(`nextChangeAt`)을 계산하는 순수 함수를 `firmware/lib/`에 만들고 `[env:native]` Unity 테스트(판정 벡터 포함)로 고정한다.

**Architecture:** 두 모듈. (1) `lib/node_store/` — `KvStore`(NVS)·`FileStore`(LittleFS) 포트 뒤에서 레코드 파일·NVS 키·RTC 캐시를 관리하는 `NodeStore`. 한 주 슬롯(최대 96)은 `/schedule.bin`, RTC 캐시에는 오늘 슬롯(최대 24)만 둔다. cw-14 수신 처리는 `NodeStore`의 저장 함수만 부르고 결과를 같은 이름의 ACK 코드로 보낸다. (2) `lib/schedule/` — 고정 +9 h 시각 변환, 틈 규칙의 `determineLayout`, `until` 기준 `nextChangeAt`. 두 모듈은 서로 include하지 않고 `lora_codec.h`의 `lc::SlotRec`·`ResvRec`·`ExamRec`을 공유한다. 실기 어댑터(Preferences·LittleFS·`RTC_DATA_ATTR` 배치·잠들기 전 seal 호출)는 `[env:terminal]`이 생길 때 cw가 `src/terminal/`에 둔다 — 이 plan 범위 밖.

**Tech Stack:** PlatformIO `[env:native]`, C++17, Unity, ArduinoJson(벡터 읽기, S1에서 도입), `lib/lora_codec`(cw 보호 계층 — 읽기·호출만)

## Global Constraints

- `lib/node_store/`·`lib/schedule/`에는 Arduino·ESP 헤더를 include하지 않는다. 표준 C++과 `lora_codec.h`(→ `proto.h`)만.
- `lora_proto/`·`lib/lora_codec/`는 수정하지 않는다. 상수는 `proto.h`의 것을 쓴다: `LP_SLOT_WEEK_MAX`(96), `LP_SLOT_DAY_MAX`(24), `LP_BREAK_GAP_MAX_MIN`(15), `LP_TYPE_*`, `LP_SLOTTYPE_*`, `LP_LAYOUT_*`, `LP_FILEKIND_*`, `LP_ACK_*`, `LP_CMD_*`. 로컬로 복사하지 않는다(`firmware/CLAUDE.md`).
- 예약 상한 24, 시험 상한 8은 v2 §5.1의 수치이고 `proto.h`에 상수가 없다 — `node_store` 안에 `kResvMax = 24`, `kExamMax = 8`로 둔다 ⚠️(서버 `NODE_RESV_MAX`와 한 곳으로 모을지는 cw 몫).
- 레코드 파일 형식 = v2 §3.3 FILE 본문: `[recType u8][recLen u8][recPayload]` 반복. 경로 `/schedule.bin`·`/resv.bin`·`/exam.bin`.
- 파싱은 `lc::nextRecord`·`lc::decSlotBody`·`decResvBody`·`decExamBody`, 직렬화는 `lc::encSlotBody`·`encResvBody`·`encExamBody`.
- 저장 결과 4종(v2 §5.1, #74 11): `Ok`·`StoreFail`(용량 초과·쓰기 실패)·`BadPayload`(CRC를 통과한 본문이 레코드로 안 풀림)·`Unsupported`(모르는 `SET_PARAM` id). cw-14가 같은 이름의 ACK 코드로 옮긴다.
- 파일 쓰기는 원자 교체 — 실패하면 옛 내용 유지(fake도 같게). 파일이 손상되면 그 kind를 비우고 버전 0.
- 지난 날짜 예약 삭제는 예약 용량 검사 **전에**, 시계가 무효면 건너뛴다 — 유효 여부는 따로 넘긴다(`purgePast(today, clockValid)`, #74 9).
- `lastTxn`은 cw-14가 저장 결과 `Ok`일 때만 기록한다(#74 10). GAP도 저장은 `Ok`다(v2 §6.4). `NodeStore`는 값만 보관한다. GAP 판정(`mod 255`)도 cw-14.
- 지난 예약 정리(`purgePast`)는 `/resv.bin`만 다시 쓰고 **버전은 바꾸지 않는다** ⚠️ — 서버는 이 정리에 버전을 올리지 않는다(v2 §5.1 "서버 일일 작업이 이 전제로 계산"). `applyResvSet`·`replaceKind(RESV)` 안에서 정리하면 버전은 그 명령의 `newVer` 하나만 기록한다.
- 시각은 epoch + 9 h 고정 정수 계산. `localtime`·`TZ`·`<ctime>`을 쓰지 않는다(v2 §5.2).
- 판정 규칙의 원본은 `lora_proto/room_state_vectors.json`(cw). 벡터와 다르면 벡터가 이긴다.
- 게이트(`firmware/`에서):
  ```bash
  pio test -e native
  pio check -e native --fail-on-defect medium --fail-on-defect high
  ```
- NUL 바이트 검사(`'\0'`이 실제 NUL 바이트로 들어간 사례 2회, #89 작업 중) — 태스크마다 새·수정 파일에 실행, 결과 모두 0:
  ```bash
  for f in $(git diff --name-only HEAD; git ls-files --others --exclude-standard); do printf '%s ' "$f"; tr -cd '\000' < "$f" | wc -c; done
  ```
- PlatformIO는 테스트 실패 시 요약 줄 총수를 1 크게 표시한다(통과 시 정상). Windows 로컬 통과는 Linux CI 통과를 보장하지 않는다 — CI 결과까지 본다.
- 문서·주석에서 범위는 `–`로 쓴다. `~` 두 개가 한 문단에 있으면 GitHub가 취소선으로 바꾼다.

## Review Focus

1. 파일이 레코드 경계에서 잘려 형식 오류 없이 짧아진 경우 — 원자 교체로만 막는다. fake가 "쓰기 실패 시 옛 내용 유지"를 지키는지(Task 1), `NodeStore`가 실패를 `StoreFail`로 올리고 RTC·NVS를 안 바꾸는지(Task 4) 고정한다.
2. 상한이 꽉 찬 상태에서 **이미 있는 키**를 다시 `SET` → 교체라 `Ok`. Task 4 `test_set_existing_key_when_full_is_ok`.
3. 같은 `SLOT_SET` 두 번(멱등) → 개수 그대로. Task 4 `test_slot_set_idempotent`.
4. 주간 합계는 96 이하인데 한 요일이 25개 → `StoreFail`(하루 상한). Task 4 `test_day_cap_25_storefail`.
5. 연도 전환(12-31 23:59:59 → 01-01)·윤일(2028-02-29). Task 6 리터럴 테스트.

---

## 파일

| 파일 | 책임 |
|---|---|
| `firmware/lib/node_store/store_port.h` | `KvStore`·`FileStore` 포트 |
| `firmware/lib/node_store/fake_store.h` | 테스트용 메모리 fake(헤더 전용, 실패·손상 주입) |
| `firmware/lib/node_store/record_file.h/.cpp` | 표 ↔ 레코드 스트림, 요일 추출 |
| `firmware/lib/node_store/rtc_state.h/.cpp` | `RtcState`(v2 §5.1 `rtc_state_t`), magic·CRC 봉인·검증 |
| `firmware/lib/node_store/node_store.h/.cpp` | `NodeStore` — cw-14가 부르는 저장 API |
| `firmware/lib/schedule/kst_time.h/.cpp` | epoch ↔ KST 날짜·시각 |
| `firmware/lib/schedule/schedule.h/.cpp` | `ScheduleView`, `LayoutDecision`, `determineLayout`, `nextChangeAt` |
| `firmware/test/test_node_store_port/` · `test_record_file/` · `test_rtc_state/` · `test_node_store/` · `test_kst_time/` · `test_schedule/` | Unity |

의존: CODEOWNERS에 `lib/node_store/`·`lib/schedule/` 항목이 아직 없다 `[확인: main 842ef8d]` — cw가 추가하기로 함(#74 결정 1). 그전에는 `/firmware/ @ssenu`만 걸린다.

---

### Task 1: 저장 포트 + 메모리 fake

**Files:** Create `lib/node_store/store_port.h`, `lib/node_store/fake_store.h` · Test `test/test_node_store_port/test_main.cpp`

**Interfaces — Produces:**
```cpp
namespace ns {
enum class ReadResult : uint8_t { Ok, NotFound, Fail };

struct KvStore {  // NVS. 값은 u32 하나로 담는다(u8·u16·bool 수용)
  virtual ~KvStore() = default;
  virtual bool get(const char* space, const char* key, uint32_t& out) = 0;  // 없으면 false
  virtual bool set(const char* space, const char* key, uint32_t v) = 0;     // 실패 false
  virtual bool eraseSpace(const char* space) = 0;
};

struct FileStore {  // LittleFS. 파일 통째 읽기·원자 쓰기
  virtual ~FileStore() = default;
  virtual ReadResult read(const char* path, uint8_t* buf, size_t cap, size_t& len) = 0;  // cap 초과면 Fail
  virtual bool writeAtomic(const char* path, const uint8_t* data, size_t len) = 0;     // 실패 시 옛 내용 유지
  virtual bool remove(const char* path) = 0;  // 없는 파일도 true
};

class FakeKv : public KvStore {
 public:
  int failSetsAfter = -1;  // n번째 set부터 실패(0 = 다음 set), -1 = 안 함
  // get/set/eraseSpace — std::map<std::string, uint32_t>, 키 "space/key"
};
class FakeFile : public FileStore {
 public:
  int failWritesAfter = -1;
  int reads = 0;                                       // read 호출 수(캐시 사용 검증용)
  void truncate(const char* path, size_t keepBytes);   // 앞 keepBytes만 남김
  void putRaw(const char* path, std::vector<uint8_t> bytes);
};
}
```
NVS 키는 v2 §5.1 이름을 그대로 쓴다(최장 `sessionWindowMs` 15자 `[확인]`). fake는 16자 이상 키를 `set` false로 거부한다 — ESP-IDF NVS 키 상한 15자는 `[추정]`, 실기 어댑터 작성 때 문서로 확인한다.

- [ ] **Step 1: 테스트** — 케이스:
  - `test_kv_get_missing_false`, `test_kv_set_get_roundtrip`(`set("ver","schedVer",7)` → `get` 7)
  - `test_kv_long_key_rejected`(16자 → `set` false, 15자 `sessionWindowMs` → true)
  - `test_kv_fail_injection`(`failSetsAfter=0` → 첫 `set` false, 값 그대로)
  - `test_file_missing_notfound`, `test_file_write_read_roundtrip`
  - `test_file_write_fail_keeps_old`(`{1,2,3}` 쓴 뒤 `failWritesAfter=0`, `{9}` → false, 읽으면 `{1,2,3}`) — Review Focus 1
  - `test_file_read_over_cap_fail`, `test_file_truncate`, `test_file_remove_missing_true`
- [ ] **Step 2: 실패 확인** — `pio test -e native -f test_node_store_port` → 컴파일 실패
- [ ] **Step 3: 구현** — 헤더 전용, `std::map` 기반
- [ ] **Step 4: 통과 확인** — 같은 명령 PASS, 전체 게이트·NUL 검사

---

### Task 2: 레코드 파일 ↔ 표, 요일 추출

**Files:** Create `lib/node_store/record_file.h/.cpp` · Test `test/test_record_file/test_main.cpp`

**Interfaces — Consumes:** `lc::nextRecord`, `lc::dec*Body`, `lc::enc*Body`. **Produces:**
```cpp
namespace ns {
constexpr uint8_t kResvMax = 24;  // v2 §5.1
constexpr uint8_t kExamMax = 8;   // v2 §5.1
// 레코드 최대 = 2(헤더) + 본문(슬롯 40·예약 44·시험 8 B) — [계산] 본문 최대: 슬롯 6+1+20+1+12, 예약 2+8+1+20+1+12
constexpr size_t kSchedFileMax = LP_SLOT_WEEK_MAX * (2 + 40);  // 4,032 B
constexpr size_t kResvFileMax  = kResvMax * (2 + 44);         // 1,104 B
constexpr size_t kExamFileMax  = kExamMax * (2 + 8);          //    80 B

enum class ParseResult : uint8_t { Ok, Corrupt, OverCapacity };

// 슬롯: 주간 상한 LP_SLOT_WEEK_MAX, 한 요일 상한 LP_SLOT_DAY_MAX — 둘 중 하나라도 넘으면 OverCapacity
ParseResult parseSlots(const uint8_t* body, uint16_t n, lc::SlotRec* out, uint8_t& count);
ParseResult parseResv (const uint8_t* body, uint16_t n, lc::ResvRec* out, uint8_t& count);
ParseResult parseExams(const uint8_t* body, uint16_t n, lc::ExamRec* out, uint8_t& count);
size_t writeSlots(const lc::SlotRec* in, uint8_t count, uint8_t* out, size_t cap);  // cap 부족 0
size_t writeResv (const lc::ResvRec* in, uint8_t count, uint8_t* out, size_t cap);
size_t writeExams(const lc::ExamRec* in, uint8_t count, uint8_t* out, size_t cap);
// 주간 표에서 weekday(1=월..7=일) 슬롯만 시작 시각 순으로 out 에. 반환 = 개수(≤ LP_SLOT_DAY_MAX)
uint8_t slotsOfDay(const lc::SlotRec* week, uint8_t n, uint8_t weekday, lc::SlotRec* out);
}
```
`Corrupt` 판정 — `nextRecord`는 정상 종료면 `pos >= n`에서 false, 형식 오류면 `pos < n`에서 `pos = n`으로 바꾸고 false(`lora_codec.cpp` `nextRecord` `[확인]`). 그래서:
```cpp
uint16_t pos = 0, before = 0;
while (before = pos, lc::nextRecord(body, n, pos, t, rec, len)) { /* t 가 kind 의 타입인지, dec*Body, 상한 */ }
if (before != n) return ParseResult::Corrupt;  // 정상 종료면 before == n
```
`recType`이 그 kind의 타입(`LP_TYPE_SLOT_SET`/`RESV_SET`/`EXAM_SET`)이 아니거나 `dec*Body` 실패도 `Corrupt`.

- [ ] **Step 1: 테스트** — 케이스:
  - `test_slots_roundtrip`: 화 12:00–12:50 "자료구조"/"김", 화 13:00–13:50, 수 09:00–09:50 → write → parse, 필드 동일, count 3
  - `test_empty_body_ok_zero`(n=0 → Ok, 0)
  - `test_truncated_header_corrupt`(정상 1개 + 1 B → Corrupt), `test_truncated_payload_corrupt`(마지막 본문 1 B 잘림 → Corrupt)
  - `test_wrong_rectype_corrupt`(schedule 파일에 `LP_TYPE_RESV_SET` → Corrupt)
  - `test_week_cap_97_over`(서로 다른 요일에 고르게 97개 → OverCapacity), `test_week_96_ok`
  - `test_day_cap_25_over`(화요일 25개 → OverCapacity) — Review Focus 4
  - `test_resv_roundtrip`, `test_exam_roundtrip`, `test_resv_25_over`
  - `test_write_cap_too_small_zero`
  - `test_slots_of_day_sorted`(주간 표 [수 09:00, 화 13:00, 화 12:00] → 화요일 [12:00, 13:00])
- [ ] **Step 2: 실패 확인** — `-f test_record_file`
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인** — PASS, 전체 게이트·NUL 검사

---

### Task 3: RTC 캐시 구조체

**Files:** Create `lib/node_store/rtc_state.h/.cpp` · Test `test/test_rtc_state/test_main.cpp`

**Interfaces — Produces:** v2 §5.1 `rtc_state_t` 그대로 + 아래 스펙 변경 제안 1필드.
```cpp
namespace ns {
constexpr uint32_t kRtcMagicBase = 0x52544300u;  // 'R''T''C' + 하위 바이트 = 레이아웃 버전 ⚠️ 값은 플랜이 정함
constexpr uint32_t kRtcLayoutVer = 1;            // 구조를 바꾸면 +1 → 옛 캐시 자동 무효화
constexpr uint32_t kRtcMagic = kRtcMagicBase | kRtcLayoutVer;

struct RtcState {
  uint32_t magic;
  uint8_t bld; uint16_t room; uint8_t unit; uint8_t provisioned;
  uint8_t schedVer, resvVer, examVer, identVer, lastTxn;
  uint8_t lastLayout; uint8_t lastDay; uint16_t lastSlotStartMin;  // 상태키 — cw-14
  uint32_t lastTimeSyncEpoch; uint32_t nextStatusEpoch;              // cw-14
  uint8_t slotsDay;                                                  // 스펙 변경 제안 — slots[] 가 어느 요일 것인지(0 = 비어 있음)
  uint8_t nSlots; lc::SlotRec slots[LP_SLOT_DAY_MAX];               // 오늘 슬롯만
  uint8_t nResv;  lc::ResvRec resv[kResvMax];
  uint8_t nExam;  lc::ExamRec exams[kExamMax];
  uint16_t crc;  // lc::crc16, [0, offsetof(crc)) 범위
};
static_assert(sizeof(RtcState) <= 4096, "RTC 캐시 4 KB 예산(#74)");

void rtcClear(RtcState& s);        // memset 0 — 패딩까지 0이라야 CRC가 결정적
void rtcSeal(RtcState& s);         // magic·crc 기록. cw가 잠들기 직전 호출
bool rtcValid(const RtcState& s);  // magic == kRtcMagic && crc 일치
}
```
**스펙 변경 제안 — `slotsDay`:** v2 구조체에는 `slots[]`가 어느 요일 것인지 담는 칸이 없다. `lastDay`는 cw-14의 상태키라 저장 계층이 쓰면 두 쪽이 한 값을 다르게 쓰게 된다. 날짜가 바뀌었는지(다시 채울지) 판단하려면 별도 칸이 필요하다 — 구조체 정의는 dh-08 몫(#74 결정 5)이라 plan이 넣고, cw 리뷰에서 확인한다.

`[계산]` 레코드 합계 24×40 + 24×44 + 8×8 = 2,080 B(호스트 sizeof 측정값 SlotRec 40·ResvRec 44·ExamRec 8 기준 `[확인]`). 실제 크기는 테스트가 출력한다. ESP32에서의 크기는 실기 빌드 때 확인 `[추정: 같을 것]`.

- [ ] **Step 1: 테스트** — 케이스:
  - `test_cleared_is_invalid`, `test_seal_then_valid`
  - `test_flip_byte_invalid`(seal 뒤 `slots[0].sH ^= 1` → false)
  - `test_old_layout_magic_invalid`(`magic = kRtcMagicBase | (kRtcLayoutVer + 1)`, crc 다시 계산 → false)
  - `test_size_within_budget`(`TEST_ASSERT_LESS_OR_EQUAL(4096, sizeof(RtcState))`, 실제 값 `TEST_MESSAGE`)
- [ ] **Step 2: 실패 확인** — `-f test_rtc_state`
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인** — PASS, 전체 게이트·NUL 검사

---

### Task 4: `NodeStore` — 데이터 적용·교체·지난 예약 정리

**Files:** Create `lib/node_store/node_store.h/.cpp` · Test `test/test_node_store/test_main.cpp`

**Interfaces — Consumes:** Task 1–3. **Produces:**
```cpp
namespace ns {
enum class StoreStatus : uint8_t { Ok, StoreFail, BadPayload, Unsupported };  // v2 §5.1, #74 11
struct Date { uint8_t y, m, d; };  // y = year-2000 (ResvRec·ExamRec 과 같은 표현)

class NodeStore {
 public:
  NodeStore(KvStore& kv, FileStore& fs, RtcState& rtc);
  const RtcState& state() const;

  // 시간표: 한 주 표는 /schedule.bin, RTC 는 slotsDay 요일만 write-through
  StoreStatus applySlotSet (uint8_t newVer, const lc::SlotRec&);
  StoreStatus applySlotDel (uint8_t newVer, const lc::SlotDel&);
  StoreStatus applyDayClear(uint8_t newVer, const lc::DayClear&);
  // 예약: 지난 예약 정리(clockValid 일 때만) 뒤 용량 검사
  StoreStatus applyResvSet (uint8_t newVer, const lc::ResvRec&, Date today, bool clockValid);
  StoreStatus applyResvDel (uint8_t newVer, const lc::ResvDel&);
  StoreStatus applyExamSet (uint8_t newVer, const lc::ExamRec&);
  StoreStatus applyExamDel (uint8_t newVer, const lc::ExamDel&);
  // FILE_END CRC 검증 뒤. body 가 안 풀리면 BadPayload, 상한 초과면 StoreFail. 버전은 무조건 newVer(v2 §3.3)
  StoreStatus replaceKind(uint8_t kind, uint8_t newVer, const uint8_t* body, uint16_t len,
                          Date today, bool clockValid);
  StoreStatus purgePast(Date today, bool clockValid);  // clockValid 거짓이면 아무것도 안 하고 Ok
  // Task 5: load, refreshDay, setLastTxn, setIdentity, setParam, param, factoryReset
};
}
```
공통 쓰기 순서(write-through) ⚠️:
```text
1. 변경을 임시 사본에 적용 → 상한 검사(주간 96·하루 24·예약 24·시험 8) → 넘으면 StoreFail, 아무것도 안 바꿈
2. 직렬화 → fs.writeAtomic(path)            실패 → StoreFail, RTC·NVS 그대로
3. kv.set("ver", "<kind>Ver", newVer)        실패 → StoreFail (파일은 새 내용, 버전은 옛 값 → 서버 STATUS 비교가 재동기를 건다)
4. RTC 확정: 시간표면 slotsDay 요일만 slotsOfDay 로 다시 채움, 버전 갱신
```
파일을 먼저 쓰는 이유: 버전을 먼저 쓰고 파일이 실패하면 서버는 동기화됐다고 믿고 노드는 옛 시간표를 계속 보인다(복구 경로 없음). 파일을 먼저 쓰면 어긋나도 서버가 버전 차이로 재동기를 건다(v2 §5.1 손상 규칙과 같은 경로).
멱등 키(v2 §3.5): SLOT=(day,sH,sM), RESV=resvId, EXAM=examId — 같은 키면 교체. 없는 키 삭제 → `Ok` + 버전 갱신 ⚠️(서버는 삭제에도 버전을 올린다 — `server/app/lora_service/api.py` `KIND_OF` `[확인]`. 노드가 버전을 안 올리면 다음 변경이 GAP으로 보인다). 주간 표는 (day, sH, sM) 오름차순 유지 ⚠️.

- [ ] **Step 1: 테스트** — `FakeKv`·`FakeFile`·`RtcState`(slotsDay = 2, 화요일) 위에서. 케이스:
  - `test_slot_set_writes_file_ver_and_today`: `applySlotSet(5, 화 12:00–12:50)` → Ok, `/schedule.bin` 1개, kv `ver/schedVer` 5, `state().nSlots` 1, `schedVer` 5
  - `test_slot_set_other_day_not_in_rtc`: 수요일 슬롯 → 파일 1개, `nSlots` 0
  - `test_slot_set_idempotent` — Review Focus 3
  - `test_week_cap_storefail`: 96개 채운 뒤 새 키 → StoreFail, 파일·버전·RTC 그대로
  - `test_day_cap_25_storefail` — Review Focus 4
  - `test_set_existing_key_when_full_is_ok` — Review Focus 2
  - `test_slot_del_missing_ok_ver_bumped`, `test_day_clear_only_that_day`
  - `test_file_write_fail_storefail_keeps_all`(`failWritesAfter=0`) — Review Focus 1
  - `test_ver_write_fail_storefail`(`failSetsAfter=0` → StoreFail, 파일 새 내용, RTC 버전 옛 값)
  - `test_replace_kind_sets_ver_even_if_lower`: schedVer 9 → `replaceKind(SCHEDULE, 3, …)` → Ok, schedVer 3
  - `test_replace_corrupt_body_badpayload`(잘린 body → BadPayload, 옛 데이터·버전 유지)
  - `test_replace_over_capacity_storefail_keeps_old`
  - `test_resv_purge_before_cap`: 예약 24개 중 3개가 26-10-12(어제) → `applyResvSet(…, today={26,10,13}, true)` 새 예약 → Ok, nResv 22
  - `test_resv_purge_skipped_when_clock_invalid`(`clockValid=false` → 어제 예약 남음, 24개면 새 예약 StoreFail)
  - `test_purge_past_keeps_today`(오늘 날짜 예약은 남김)
  - `test_purge_past_keeps_version`(resvVer 7 → `purgePast` 로 2개 지움 → resvVer 7, kv `ver/resvVer` 7, `/resv.bin` 은 줄어듦)
  - `test_exam_set_del`
- [ ] **Step 2: 실패 확인** — `-f test_node_store`
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인** — PASS, 전체 게이트·NUL 검사

---

### Task 5: `NodeStore` — 부팅 적재·요일 전환·정체성·TXN·파라미터·초기화

**Files:** Modify `lib/node_store/node_store.h/.cpp` · Test `test/test_node_store/test_main.cpp`(케이스 추가)

**Interfaces — Produces:**
```cpp
struct Identity { uint8_t bld; uint16_t room; uint8_t unit; };
enum class LoadSource : uint8_t { RtcCache, Rebuilt };
// NodeStore 멤버
LoadSource load(uint8_t weekday);           // 부팅 시. rtcValid 면 RTC 그대로(단 slotsDay != weekday 이고 weekday != 0 이면 refreshDay), 아니면 NVS·파일에서 재구축(+ weekday 슬롯) 후 seal
StoreStatus refreshDay(uint8_t weekday);    // 날짜가 바뀌면 cw 가 부른다 — /schedule.bin 에서 그 요일 슬롯을 RTC 에 다시 채움
StoreStatus setLastTxn(uint8_t txn);        // cw-14 는 저장 결과 Ok 일 때만 부른다(#74 10)
StoreStatus setIdentity(const Identity&, uint8_t identVer);  // provisioned = 1
StoreStatus setParam(uint8_t paramId, uint32_t value);       // 1 statusHourUtc · 2 sessionWindowMs, 그 밖 Unsupported
bool param(uint8_t paramId, uint32_t& out);                   // NVS 에서 읽음(RTC 구조체에 없음)
StoreStatus factoryReset();                 // cfg·ver 지움, 파일 3개 삭제, RTC 비움(provisioned 0)
```
`weekday`를 모를 때(시계 무효) cw는 `0`을 넘긴다 → `slotsDay = 0`, `nSlots = 0` ⚠️.
NVS 키(v2 §5.1 그대로): `cfg` — `bld` `room` `unit` `identVer` `provisioned` `statusHourUtc` `sessionWindowMs` / `ver` — `schedVer` `resvVer` `examVer` `lastTxn`.
재구축: 파일별 결과가 `Corrupt`·`OverCapacity`·`ReadResult::Fail`이면 그 kind를 비우고 버전 0(NVS에도 0) — v2 §5.1. `NotFound`는 빈 표 + NVS 버전 그대로 ⚠️(처음 켠 노드·FILE 수신 전).

- [ ] **Step 1: 테스트** — 케이스:
  - `test_load_uses_valid_rtc`(seal된 RTC → `RtcCache`, `FakeFile::reads == 0`)
  - `test_load_rebuilds_when_invalid`: NVS·파일에 데이터 → RTC clear → `load(2)` == `Rebuilt`, 화요일 슬롯·예약·시험·버전·정체성 복원, `rtcValid` true
  - `test_load_corrupt_schedule_empties_ver0`: `/schedule.bin` 손상 → nSlots 0, schedVer 0, kv schedVer 0, 예약은 정상
  - `test_load_weekday_zero_no_slots`
  - `test_load_valid_rtc_other_day_refreshes`(화요일로 seal된 RTC → `load(3)` == `RtcCache`, `slotsDay` 3, 수요일 슬롯)
  - `test_refresh_day_switches`: 화→수 `refreshDay(3)` → 수요일 슬롯, `slotsDay` 3
  - `test_identity_persists`, `test_last_txn_persists`
  - `test_set_param_known_and_unknown`(1 → Ok·`param` 읽힘, 9 → Unsupported)
  - `test_factory_reset_clears_all`
  - `test_write_through_matches_rebuild`: 임의 적용 10회 뒤 RTC 사본 vs `rtcClear` → `load(같은 요일)` 결과, seal 뒤 바이트 동일
- [ ] **Step 2: 실패 확인**
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인** — PASS, 전체 게이트·NUL 검사

---

### Task 6: KST 시각 변환

**Files:** Create `lib/schedule/kst_time.h/.cpp` · Test `test/test_kst_time/test_main.cpp`

**Interfaces — Produces:**
```cpp
namespace sch {
constexpr int32_t kKstOffsetSec = 9 * 3600;  // v2 §5.2 — 서머타임 없음
struct KstTime { uint16_t year; uint8_t month, day, weekday /*1=월..7=일, SlotRec.day 와 같음*/, hour, minute, second; };
KstTime toKst(uint32_t epoch);
uint32_t kstMidnight(uint16_t year, uint8_t month, uint8_t day);  // 그 날 00:00 KST 의 epoch
uint16_t minuteOfDay(const KstTime&);                            // hour*60 + minute
}
```
날짜 계산은 days-from-civil 정수 알고리즘(H. Hinnant). `<ctime>` 금지.

- [ ] **Step 1: 테스트** — 리터럴 `[확인: Git Bash TZ=KST-9 date]`:
  ```cpp
  // 1791817200 → 2026-10-13 00:00:00 화(2)
  // 1791866998 → 2026-10-13 13:49:58 화(2)
  // 1798729199 → 2026-12-31 23:59:59 목(4)
  // 1798729200 → 2027-01-01 00:00:00 금(5)   — Review Focus 5
  // 1835362800 → 2028-02-29 00:00:00 화(2)   — Review Focus 5
  // 1700000000 → 2023-11-15 07:13:20 수(3)
  TEST_ASSERT_EQUAL_UINT32(1791817200u, sch::kstMidnight(2026, 10, 13));
  TEST_ASSERT_EQUAL_UINT32(1835362800u, sch::kstMidnight(2028, 2, 29));
  ```
- [ ] **Step 2: 실패 확인** — `-f test_kst_time`
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인** — PASS, 전체 게이트·NUL 검사

---

### Task 7: `determineLayout` · `nextChangeAt`

**Files:** Create `lib/schedule/schedule.h/.cpp` · Test `test/test_schedule/test_main.cpp`

**Interfaces — Consumes:** Task 6, `lc::SlotRec`·`ResvRec`·`ExamRec`, `LP_LAYOUT_*`, `LP_SLOTTYPE_CLASS`, `LP_BREAK_GAP_MAX_MIN`. **Produces** (시그니처는 v2 §5.3·§5.4 그대로):
```cpp
namespace sch {
struct ScheduleView {
  const lc::SlotRec* slots; uint8_t nSlots;  // 오늘 요일 슬롯(RTC slots[]). 다른 요일은 무시
  const lc::ResvRec* resv;  uint8_t nResv;   // 전체 — 오늘 날짜만 본다
  const lc::ExamRec* exams; uint8_t nExam;
};
enum class Decider : uint8_t { Resv, ExamSlot, Slot, Break, Free };
constexpr uint16_t kNoSlot = 0xFFFF;
struct LayoutDecision {
  uint8_t layout;
  Decider by;
  uint8_t index;         // Resv: resv[] 위치 · ExamSlot/Slot: slots[] 위치 · Break: 다음 슬롯의 slots[] 위치 · Free: 0xFF
  uint8_t day;           // 상태키 day (1..7)
  uint16_t slotStartMin; // 상태키 curSlotStart — 결정 항목의 시작(분). Break = 다음 슬롯 시작, Free = kNoSlot
};
LayoutDecision determineLayout(const ScheduleView& v, uint32_t nowEpoch);
uint32_t nextChangeAt(const ScheduleView& v, uint32_t nowEpoch, uint32_t nextStatusEpoch);
}
```
판정(v2 §5.3, `test_room_state_vectors.py` `_ref`와 같은 순서):
```text
1. 예약: 날짜 == 오늘 && s <= now < e → typeToLayout(type), Resv
2. 슬롯 [s,e) 안: 시험기간(d1 <= 오늘 <= d2, 양끝 포함) → 5 ExamSlot / 아니면 typeToLayout(type) Slot
3. 시작 순 인접 슬롯 a,b: a.type == b.type == 수업 && 0 < b.s − a.e <= LP_BREAK_GAP_MAX_MIN && a.e <= now < b.s → 2 Break(index = b)
4. 그 밖 → 4 Free
typeToLayout: 1→1 2→5 3→3 4→4 5→6 6→7
```
쉬는시간의 `index`·`slotStartMin`이 다음 슬롯인 이유: 쉬는시간에는 RenderModel `cur` = `next` = 다음 슬롯이다(v2 §5.3, #89). 상태키 `curSlotStart`도 그 `cur`의 시작이 된다 ⚠️. RenderModel을 채우는 일은 cw-14.

`nextChangeAt`(v2 §5.4):
```text
now_state = (layout, by, index)
for b in 오늘 슬롯·오늘 예약의 시작·끝(분) 중 now 보다 뒤, 오름차순:
    if state(b) != now_state: 후보 = kstMidnight(오늘) + b*60; break       // 벡터 until
후보 += 다음 자정, 시험 시작일 00:00(> now), 시험 종료일 다음날 00:00(> now), nextStatusEpoch(> now)
return min(후보) + 2
```
v2의 "없으면 now + 24 h"는 다음 자정이 항상 후보라 도달하지 않는다 — 분기를 두지 않는다 ⚠️.

- [ ] **Step 1: 테스트**
  - (a) `test_room_state_vectors`: `../lora_proto/room_state_vectors.json`(25건 `[확인]`)을 ArduinoJson으로 읽는다(`test_codec`의 파일 읽기 방식). 기준일 화 2026-10-13, 00:00 = `1791817200` `[확인]`. `slots[]` → `SlotRec{day=2}`, `resvs[]` → `ResvRec{26,10,13}`, `in_exam` → `ExamRec{26,10,13 – 26,10,13}`. 각 벡터:
    ```cpp
    uint32_t now = 1791817200u + at * 60;
    TEST_ASSERT_EQUAL_UINT8_MESSAGE(layout, sch::determineLayout(v, now).layout, name);
    uint32_t want = (until is null ? 1791903600u : 1791817200u + until * 60) + 2;  // 다음 자정 = 1791903600
    TEST_ASSERT_EQUAL_UINT32_MESSAGE(want, sch::nextChangeAt(v, now, 0xFFFFFFFFu), name);
    ```
  - (b) 벡터 밖 케이스:
    ```cpp
    // test_next_status_wins:      빈 view, now 01:00 = 1791820800, nextStatus 02:00 = 1791824400 → 1791824402
    // test_resv_other_date_ignored: 예약 26-10-14 09:00–10:00 type 6, 빈 슬롯, now 화 09:30 = 1791851400 → layout 4, 1791903602
    // test_exam_starts_tomorrow:  시험 26-10-14–26-10-15, now 화 09:30 → nextChangeAt 1791903602 (자정 = 시험 시작)
    // test_other_weekday_slot_ignored: 수요일(day=3) 슬롯 09:00–09:50, now 화 09:30 → layout 4
    // test_break_decider_is_next_slot: 벡터 slots, at 590(09:50) → by Break, index = 10:00 슬롯 위치, slotStartMin 600
    ```
- [ ] **Step 2: 실패 확인** — `-f test_schedule`
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인** — PASS, 전체 게이트·NUL 검사

---

### Task 8: 전체 게이트 + 진행표 + PR + #74 닫기

- [ ] **Step 1:** 전체 게이트 — `test` 전부 PASS, `check` HIGH 0 / MEDIUM 0, NUL 검사 전부 0.
- [ ] **Step 2:** `docs/progress.html` dh-08 체크·PR 번호(파일 상단 안내의 "현재 상태를 HTML로 복사" 절차).
- [ ] **Step 3:** PR 본문에 스펙 변경 제안(`slotsDay`)과 ⚠️ 항목을 cw 리뷰 대상으로 적는다. 게시 후 재조회해 원문과 대조한다.
- [ ] **Step 4:** Linux CI 결과 확인 뒤에야 "통과"로 보고.
- [ ] **Step 5:** #74 닫기 — "plan 완성 시점에 직접 닫는다"(#74 댓글 2026-10-14·11-03). plan 문서를 올리는 시점에 dh가 닫는다.

---

## 남은 확인 (구현을 막지 않음)

- `slotsDay` 스펙 변경 제안 — cw 리뷰(Task 3).
- ⚠️ 항목 목록(Self-Review 끝) — cw 리뷰.
- ESP-IDF NVS 키 상한 15자 — 실기 어댑터(cw) 작성 때 확인.
- CODEOWNERS `lib/node_store/`·`lib/schedule/` — cw.

## Self-Review

- 스펙 시그니처: v2 §5.3 `LayoutDecision determineLayout(const ScheduleView& v, uint32_t nowEpoch)`, §5.4 `uint32_t nextChangeAt(const ScheduleView& v, uint32_t nowEpoch, uint32_t nextStatusEpoch)` — 2개 중 일치 2. §5.1 예시 `purgePast(today, clockValid)` — 이름·인자 순서 일치(`Date`, `bool`). §5.1 저장 결과 4종 — `StoreStatus` 일치. `rtc_state_t` 필드 — 전부 일치 + `slotsDay` 1개 추가(스펙 변경 제안으로 명시). `lc::nextRecord`·`dec*Body`·`enc*Body` 그대로 사용.
- 스펙 절 대응: §5.1 → Task 1–5, §5.2 → Task 6, §5.3·§5.4 → Task 7(벡터 25건), §3.3 FILE 무조건 버전 → Task 4, §3.5 멱등 키 → Task 4, §10.1 경계값 → Task 6·7. 미대응(범위 밖, cw-14): §5.2 `clockValid` 판정·`CLOCK_STALE`, §6.3 상태키 비교·렌더 여부, §6.4 dispatch·ACK 송신·`lastTxn` 기록 시점, RenderModel 채우기.
- cw 확인 항목(스펙 미명시 — 플랜이 정함): `kRtcMagicBase` 값, `slotsDay`, 없는 키 삭제 → Ok + 버전 갱신, 주간 표 정렬, 쓰기 순서(파일 → 버전), `NotFound`는 버전 유지, `purgePast`는 버전 유지, `load`가 요일이 다르면 `refreshDay`, weekday 0 = 슬롯 비움, 쉬는시간 상태키 = 다음 슬롯 시작, "없으면 +24 h" 분기 생략, `kResvMax`·`kExamMax` 로컬 상수.

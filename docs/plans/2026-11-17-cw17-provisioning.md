# 노드 프로비저닝·CMD·버튼 (절전 작업 2단계) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 정체성이 없는 노드가 설정 대기 화면(layout 8, `NEW-xxxx`)을 띄우고 HELLO 를 보내며, 관리자 웹의 대기 노드 배정(SET_ROOM)으로 정체성을 받는다(v2 §6.2·§6.4·§6.6). CMD(TEST_RENDER·REBOOT·SET_PARAM·FACTORY_RESET·FORCE_RENDER)와 PRG 버튼(짧게 = 다시 그리기 + STATUS, 5 s = 공장 초기화, §6.5)을 처리한다. 서버·웹은 이미 HELLO → 대기 노드 → `/pending/{mac}/provision` → SET_ROOM 을 갖고 있다 — 바꾸는 곳은 노드뿐.

**Architecture:** 판단(대상 필터·SET_ROOM·CMD·설정 화면 모델·버튼 눌림 분류)은 `lib/node_core` 순수 로직 + 호스트 시험. `main.cpp` 는 MAC·HELLO 송신·재부팅·초기화·버튼 GPIO·잠들기 깨우기만. 3b(deep sleep, `feature/cw16-3b-deep-sleep`) 위에 쌓는다.

## Global Constraints

- `lora_proto/`·`lib/lora_codec/`·`lib/node_store/`·`lib/schedule/`·`lib/render*` 은 바꾸지 않는다. 코덱은 `lc::decSetRoom`·`lc::encHello`·`lc::decCmd`, 상수는 `LP_CMD_*`·`LP_BLD_UNPROVISIONED`·`LP_LAYOUT_SETUP`.
- 대상 필터(§6.6): BROADCAST·BLD_ALL → 수락. `BLD == LP_BLD_UNPROVISIONED`(0) → 미설정 노드만, TYPE == SET_ROOM 일 때만. MAC 이 다르거나 이미 설정된 노드면 **응답하지 않는다**(ACK 없음, lastTxn 안 씀).
- SET_ROOM 적용 = `NodeStore::setIdentity({bld, room, unit}, NEW_VER)` → OK 면 ACK OK(정체성 버전 = NEW_VER). 서버는 이 ACK 의 버전 0 을 보고 FILE 재동기를 스스로 건다.
- CMD(§3.3): `TEST_RENDER [layout 1..8]` → 그 레이아웃으로 한 번 그림, `REBOOT` → ACK 뒤 재시작, `SET_PARAM [paramId u8][value u32 BE]` → `NodeStore::setParam`(1 statusHourUtc · 2 sessionWindowMs, 모르는 id = UNSUPPORTED), `REQUEST_STATUS`(있음), `FACTORY_RESET` → ACK 뒤 `factoryReset` + 재시작, `FORCE_RENDER` → 같은 화면이어도 다시 그림. 인자 길이가 틀리면 BAD_PAYLOAD.
- 설정 화면 모델: layout 8, `newTag = "NEW-%02X%02X"`(MAC 마지막 2 바이트, 대문자), 나머지 0.
- HELLO(§3.3 `[mac 6B][fw u8][batt_mV u16 BE]`, 헤더 BLD/ROOM/UNIT 0·TXN 0): 미설정 노드가 부팅 1~4 s 뒤, 이후 10 min 마다(시계와 무관). 미설정이면 STATUS 는 보내지 않는다.
- 정체성 빌드 플래그: `NODE_ROOM` 을 **빌드 플래그로 줬을 때만** 지금처럼 그 정체성을 강제(시연·실험용, `NODE_BLD` 기본 'E', `NODE_UNIT` 기본 1). 안 주면 NVS 정체성을 쓰고, 없으면 미설정(layout 8 + HELLO).
- 버튼(PRG = GPIO0, 눌림 LOW): 50 ms 이상 1 s 미만 눌렀다 떼면 짧게(다시 그리기 + STATUS 0.3 s 뒤), 누른 채 5 s 가 되면 길게(공장 초기화 + 재시작) — 길게는 한 번만, 1~5 s 에 떼면 아무것도 안 함. LIGHT 는 GPIO0 LOW 로도 깨고(gpio wakeup), DEEP 은 ext1(GPIO0 ANY_LOW).
- `FW_VER` 5 → 6. 커밋 `feat(firmware):`.

---

### Task 1: 판단 로직 (`lib/node_core`)

**Files:** `firmware/lib/node_core/node_core.h`·`.cpp`, `firmware/test/test_node_core/test_main.cpp`

**Interfaces — Produces:**
```cpp
struct Ident {
  uint8_t bld;
  uint16_t room;
  uint8_t unit;
  bool provisioned = true;
  uint8_t mac[6] = {};
};
// Outcome 에 추가
  bool ignored = false;      // 대상이 아니었다(SET_ROOM MAC 불일치·설정된 노드) — ACK 없음
  bool provisionedNow = false;
  bool reboot = false;
  bool factoryReset = false;
  bool forceRender = false;
  uint8_t testLayout = 0;    // TEST_RENDER — 0 이면 없음
// handleFrame 에 myMac 인자 추가(기본 nullptr — SET_ROOM 은 무시됨)
Outcome handleFrame(ns::NodeStore&, FileRx&, const lc::Header&, const uint8_t* payload, uint32_t nowEpoch,
                    const uint8_t* myMac = nullptr);
void setupModel(const uint8_t mac[6], RenderModel& m);
class Button {
 public:
  enum Action : uint8_t { kNone, kShort, kLong };
  Action update(uint32_t nowMs, bool pressed);
 private:
  bool down_ = false, longFired_ = false;
  uint32_t since_ = 0;
};
constexpr uint32_t kButtonDebounceMs = 50, kButtonShortMaxMs = 1000, kButtonLongMs = 5000;
```

- [ ] **Step 1: 실패하는 시험**

```cpp
// ---------------- 프로비저닝(§6.6·SET_ROOM) ----------------
static const uint8_t MAC[6] = {0x3c, 0x0f, 0x02, 0xee, 0x47, 0x10};

void test_is_for_me_unprovisioned() {
  Ident un{0, 0, 0, false, {}};
  TEST_ASSERT_TRUE(isForMe(un, hdr(LP_TYPE_SET_ROOM, 1, LP_FLAG_ACK_REQ, LP_BLD_UNPROVISIONED, 0, 0)));
  TEST_ASSERT_FALSE(isForMe(un, hdr(LP_TYPE_SLOT_SET, 1, LP_FLAG_ACK_REQ, LP_BLD_UNPROVISIONED, 0, 0)));
  TEST_ASSERT_TRUE(isForMe(un, hdr(LP_TYPE_TIME, 0, LP_FLAG_BROADCAST, LP_BLD_ALL, 0xFFFF, 0xFF)));
  TEST_ASSERT_FALSE(isForMe(ME, hdr(LP_TYPE_SET_ROOM, 1, LP_FLAG_ACK_REQ, LP_BLD_UNPROVISIONED, 0, 0)));  // 설정됨
}

static Outcome setRoom(uint8_t txn, uint8_t ver, const uint8_t* mac, uint16_t room, const uint8_t* myMac) {
  lc::SetRoom sr{};
  std::memcpy(sr.mac, mac, 6);
  sr.bld = 'E', sr.room = room, sr.unit = 1;
  lc::Header h = hdr(LP_TYPE_SET_ROOM, txn, LP_FLAG_ACK_REQ, LP_BLD_UNPROVISIONED, 0, 0);
  h.len = (uint8_t)lc::encSetRoom(ver, sr, g_pl, sizeof g_pl);
  return handleFrame(*ST, *F, h, g_pl, NOW, myMac);
}

void test_set_room_provisions_matching_mac() {
  ST->factoryReset();
  ST->load(4);
  TEST_ASSERT_EQUAL_UINT8(0, R->provisioned);
  Outcome o = setRoom(9, 3, MAC, 803, MAC);
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_OK, o.status);
  TEST_ASSERT_TRUE(o.provisionedNow);
  TEST_ASSERT_TRUE(o.changed);
  TEST_ASSERT_EQUAL_UINT8(1, R->provisioned);
  TEST_ASSERT_EQUAL_UINT8('E', R->bld);
  TEST_ASSERT_EQUAL_UINT16(803, R->room);
  TEST_ASSERT_EQUAL_UINT8(1, R->unit);
  TEST_ASSERT_EQUAL_UINT8(3, R->identVer);
}

void test_set_room_ignores_other_mac_and_provisioned() {
  ST->factoryReset();
  ST->load(4);
  const uint8_t other[6] = {1, 2, 3, 4, 5, 6};
  Outcome o = setRoom(9, 3, other, 803, MAC);
  TEST_ASSERT_EQUAL_HEX8(kNoAck, o.status);  // 응답하지 않는다(§6.6)
  TEST_ASSERT_TRUE(o.ignored);
  TEST_ASSERT_EQUAL_UINT8(0, R->provisioned);
  TEST_ASSERT_EQUAL_UINT8(0, R->lastTxn);
  Outcome n = setRoom(10, 3, MAC, 803, nullptr);  // 내 MAC 을 모르면 무시
  TEST_ASSERT_TRUE(n.ignored);
  setRoom(11, 3, MAC, 803, MAC);  // 설정됨
  Outcome again = setRoom(12, 4, MAC, 301, MAC);
  TEST_ASSERT_TRUE(again.ignored);
  TEST_ASSERT_EQUAL_UINT16(803, R->room);
}

// ---------------- CMD(§3.3) ----------------
static Outcome cmd(uint8_t txn, uint8_t c, const uint8_t* args, uint8_t n) {
  lc::CmdMsg m{c, args, n};
  return run(hdr(LP_TYPE_CMD, txn), lc::encCmd(m, g_pl, sizeof g_pl));
}

void test_cmd_actions() {
  Outcome r = cmd(20, LP_CMD_REBOOT, nullptr, 0);
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_OK, r.status);
  TEST_ASSERT_TRUE(r.reboot);
  Outcome f = cmd(21, LP_CMD_FACTORY_RESET, nullptr, 0);
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_OK, f.status);
  TEST_ASSERT_TRUE(f.factoryReset);
  TEST_ASSERT_EQUAL_UINT8(1, R->provisioned);  // 초기화는 ACK 뒤 main 이 한다
  Outcome fr = cmd(22, LP_CMD_FORCE_RENDER, nullptr, 0);
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_OK, fr.status);
  TEST_ASSERT_TRUE(fr.forceRender);
  const uint8_t lay = LP_LAYOUT_RENTAL;
  Outcome t = cmd(23, LP_CMD_TEST_RENDER, &lay, 1);
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_OK, t.status);
  TEST_ASSERT_EQUAL_UINT8(LP_LAYOUT_RENTAL, t.testLayout);
  const uint8_t bad = 9;
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_BAD_PAYLOAD, cmd(24, LP_CMD_TEST_RENDER, &bad, 1).status);
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_BAD_PAYLOAD, cmd(25, LP_CMD_TEST_RENDER, nullptr, 0).status);
}

void test_cmd_set_param() {
  const uint8_t a[5] = {1, 0, 0, 0, 20};  // statusHourUtc = 20
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_OK, cmd(30, LP_CMD_SET_PARAM, a, 5).status);
  uint32_t v = 0;
  TEST_ASSERT_TRUE(ST->param(1, v));
  TEST_ASSERT_EQUAL_UINT32(20, v);
  const uint8_t unk[5] = {99, 0, 0, 0, 1};
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_UNSUPPORTED, cmd(31, LP_CMD_SET_PARAM, unk, 5).status);
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_BAD_PAYLOAD, cmd(32, LP_CMD_SET_PARAM, a, 4).status);
}

// ---------------- 설정 화면·버튼 ----------------
void test_setup_model() {
  RenderModel m{};
  m.layout = 1;
  setupModel(MAC, m);
  TEST_ASSERT_EQUAL_UINT8(LP_LAYOUT_SETUP, m.layout);
  TEST_ASSERT_EQUAL_STRING("NEW-4710", m.newTag);
  TEST_ASSERT_EQUAL_UINT8(0, m.nToday);
}

void test_button_short_long() {
  Button b;
  TEST_ASSERT_EQUAL(Button::kNone, b.update(0, false));
  TEST_ASSERT_EQUAL(Button::kNone, b.update(100, true));
  TEST_ASSERT_EQUAL(Button::kShort, b.update(400, false));  // 300 ms
  TEST_ASSERT_EQUAL(Button::kNone, b.update(500, true));
  TEST_ASSERT_EQUAL(Button::kNone, b.update(520, false));   // 20 ms — 튐
  TEST_ASSERT_EQUAL(Button::kNone, b.update(1000, true));
  TEST_ASSERT_EQUAL(Button::kNone, b.update(3000, false));  // 2 s — 아무것도
  TEST_ASSERT_EQUAL(Button::kNone, b.update(4000, true));
  TEST_ASSERT_EQUAL(Button::kNone, b.update(8999, true));
  TEST_ASSERT_EQUAL(Button::kLong, b.update(9000, true));   // 5 s
  TEST_ASSERT_EQUAL(Button::kNone, b.update(9500, true));   // 한 번만
  TEST_ASSERT_EQUAL(Button::kNone, b.update(9600, false));  // 떼도 짧게 아님
}
```
`main()` 에 9개 등록. 기존 `test_is_for_me` 의 마지막 줄(설정된 `ME` 가 SET_ROOM 을 안 받음)은 그대로 통과해야 한다. `setUp` 의 `ST->load(4)` 뒤 R 은 정체성이 없을 수 있다 — 시험이 필요한 곳에서 `ST->setIdentity` 를 직접 부른다(위 `test_cmd_actions` 의 `R->provisioned == 1` 은 그 전에 `ST->setIdentity(ns::Identity{'E', 301, 1}, 0)` 을 부른다).

- [ ] **Step 2: 실패 확인** — `pio test -e native -f test_node_core` 컴파일 실패
- [ ] **Step 3: 구현**

`isForMe`:
```cpp
bool isForMe(const Ident& me, const lc::Header& h) {
  if (h.flags & LP_FLAG_BROADCAST) return true;
  if (h.bld == LP_BLD_ALL) return true;
  if (h.bld == LP_BLD_UNPROVISIONED) return !me.provisioned && h.type == LP_TYPE_SET_ROOM;  // MAC 은 handleFrame
  if (!me.provisioned) return false;
  return h.bld == me.bld && h.room == me.room && (h.unit == LP_UNIT_ALL || h.unit == me.unit);
}
```
`apply()` 에 `const uint8_t* myMac` 인자를 더하고 분기 추가:
```cpp
    case LP_TYPE_SET_ROOM: {
      lc::SetRoom sr{};
      uint8_t nv = 0;
      if (!lc::decSetRoom(p, h.len, nv, sr)) return LP_ACK_BAD_PAYLOAD;
      if (!myMac || std::memcmp(sr.mac, myMac, 6) != 0 || r.provisioned) {
        o.ignored = true;
        return kNoAck;
      }
      const ns::StoreStatus s = st.setIdentity(ns::Identity{sr.bld, sr.room, sr.unit}, nv);
      if (s != ns::StoreStatus::Ok) return ackOf(s, 0, 1);
      o.provisionedNow = true;
      o.changed = true;
      return LP_ACK_OK;
    }
```
CMD 분기를 바꾼다:
```cpp
    case LP_TYPE_CMD: {
      lc::CmdMsg c{};
      if (!lc::decCmd(p, h.len, c)) return LP_ACK_BAD_PAYLOAD;
      switch (c.cmd) {
        case LP_CMD_REQUEST_STATUS:
          o.statusReq = true;
          return LP_ACK_OK;
        case LP_CMD_REBOOT:
          o.reboot = true;
          return LP_ACK_OK;
        case LP_CMD_FACTORY_RESET:
          o.factoryReset = true;
          return LP_ACK_OK;
        case LP_CMD_FORCE_RENDER:
          o.forceRender = true;
          return LP_ACK_OK;
        case LP_CMD_TEST_RENDER:
          if (c.argsLen != 1 || c.args[0] < 1 || c.args[0] > LP_LAYOUT_SETUP) return LP_ACK_BAD_PAYLOAD;
          o.testLayout = c.args[0];
          return LP_ACK_OK;
        case LP_CMD_SET_PARAM: {
          if (c.argsLen != 5) return LP_ACK_BAD_PAYLOAD;
          const uint32_t v = (uint32_t)c.args[1] << 24 | (uint32_t)c.args[2] << 16 | (uint32_t)c.args[3] << 8 | c.args[4];
          return ackOf(st.setParam(c.args[0], v), 0, 1);
        }
        default:
          return LP_ACK_UNSUPPORTED;
      }
    }
```
(`ackOf(s, 0, 1)` = Ok → OK, 나머지는 같은 이름 ACK.) `default:` 주석은 `// 그 밖의 TYPE`. `handleFrame` 은 `myMac` 을 받아 `apply` 에 넘기고, `o.ignored` 면 `o.status = kNoAck` 로 끝낸다(lastTxn 안 씀). `decCmd` 가 SET_PARAM 인자 길이를 먼저 막으면 그 결과(BAD_PAYLOAD)를 그대로 쓴다.

`setupModel`:
```cpp
void setupModel(const uint8_t mac[6], RenderModel& m) {
  m = RenderModel{};
  m.layout = LP_LAYOUT_SETUP;
  std::snprintf(m.newTag, sizeof m.newTag, "NEW-%02X%02X", mac[4], mac[5]);
}
```
`Button::update`:
```cpp
Button::Action Button::update(uint32_t nowMs, bool pressed) {
  if (pressed) {
    if (!down_) {
      down_ = true;
      longFired_ = false;
      since_ = nowMs;
      return kNone;
    }
    if (!longFired_ && nowMs - since_ >= kButtonLongMs) {
      longFired_ = true;
      return kLong;
    }
    return kNone;
  }
  if (!down_) return kNone;
  down_ = false;
  const uint32_t held = nowMs - since_;
  if (longFired_ || held < kButtonDebounceMs || held >= kButtonShortMaxMs) return kNone;
  return kShort;
}
```
- [ ] **Step 4: 통과** — `pio test -e native -f test_node_core` PASS, clang-format clean.
- [ ] **Step 5: Commit** — `feat(firmware): 프로비저닝·CMD·버튼 판단 로직 — SET_ROOM(MAC 일치·미설정만), CMD 6종, 설정 화면 모델, 버튼 짧게/길게`

---

### Task 2: 노드 연결 (`src/terminal/main.cpp`) — 컨트롤러가 실기와 함께

- MAC(`ESP.getEfuseMac`, 바이트 0 = 첫 옥텟) 을 전역에 두고 `me()` 에 provisioned·mac 을 싣는다. `handleFrame(..., g_mac)`.
- 정체성: `#ifdef NODE_ROOM` 일 때만 강제(지금 동작). 아니면 NVS.
- 미설정: 화면 = `setupModel`(시계와 무관하게 그림), HELLO 예약(부팅 1~4 s, 이후 10 min), STATUS 안 보냄.
- SET_ROOM 적용(`o.provisionedNow`) → 다시 그림(시계가 있으면 정규 화면), 부팅 STATUS 대신 0.3 s 뒤 STATUS.
- CMD: `reboot`·`factoryReset` 은 ACK 를 보낸 뒤 0.5 s 기다렸다 실행(`factoryReset` → `esp_restart`). `forceRender` → 같은 화면 비교를 한 번 건너뜀. `testLayout` → 지금 모델의 layout 만 바꿔 한 번 그림.
- SET_PARAM 값 사용: 부팅·적용 때 `param(1)` 이 있으면 하루 STATUS 시각에, `param(2)` 가 있으면 조용함 창(QUIET)에 쓴다(없으면 18·8000).
- 버튼: `loop` 에서 `Button::update(millis(), digitalRead(0) == LOW)`. LIGHT 는 `gpio_wakeup_enable(GPIO0, LOW_LEVEL)`, DEEP 은 `esp_sleep_enable_ext1_wakeup(1ULL << 0, ESP_EXT1_WAKEUP_ANY_LOW)`. 버튼으로 깨면 떼기까지 잠들지 않는다.
- FW 6, 세 모드 빌드.

### Task 3: 실기

| 확인 | 기대 |
|---|---|
| 공장 초기화(버튼 5 s) | 재시작 → layout 8 `NEW-xxxx` → HELLO → 관리자 웹 대기 노드에 나타남 |
| 배정(웹) | SET_ROOM acked → 노드가 정체성 저장 → 서버가 FILE 재동기 → 정규 화면 |
| 버튼 짧게 | 다시 그림 + STATUS |
| CMD | 서버 컨테이너에서 `api._enqueue(..., "CMD", ...)` 로 FORCE_RENDER·REQUEST_STATUS·REBOOT |
| 깊은 잠 + 버튼 | DEEP 빌드에서 버튼으로 깸 |

끝나면 두 노드를 기본 빌드(정체성은 NVS)로 되돌린다.

# 노드 STATUS 업링크·부팅 시각 요청·배터리 측정 (절전 작업 1단계) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 노드가 STATUS(v2 §3.3)를 보낸다 — 부팅 직후(시계 없음 → `CLOCK_STALE` → 모뎀Pi 가 타겟 TIME 을 보내 몇 초 안에 시계가 맞는다), 하루 1회, TIME `REQUEST_STATUS`·CMD `REQUEST_STATUS` 를 받았을 때. ACK·STATUS 의 `batt_mV` 를 실측값으로 바꾼다.

**Architecture:** 서버·모뎀Pi 는 이미 STATUS 를 처리한다(`modempi/lora/uplink.py` — CLOCK_STALE 이면 타겟 TIME, 서버 `api.on_uplink` — 버전 비교 → FILE 재동기). 그래서 바꾸는 곳은 노드뿐이다. 판단(플래그·다음 시각·예약)은 `lib/node_core` 의 순수 함수·작은 클래스(`StatusPlan`)로 두고 호스트에서 시험한다. `src/terminal/main.cpp` 는 송신·배터리 ADC·millis/epoch 연결만 한다. 깨어 있는 모드 유지(잠들기는 3단계).

**Tech Stack:** C++17, PlatformIO(`[env:native]` Unity, `[env:terminal]` ESP32-S3 Heltec V3.2), RadioLib 7.1.2

## Global Constraints

- `lora_proto/`·`lib/lora_codec/`·`lib/node_store/`·`lib/schedule/` 은 바꾸지 않는다. STATUS 인코딩은 기존 `lc::encStatus`, 플래그는 `LP_STATUSFLAG_*`, TIME 플래그는 `LP_TIMEFLAG_REQUEST_STATUS`, CMD 는 `LP_CMD_REQUEST_STATUS`.
- STATUS 페이로드 = ACK 페이로드 + `[rssiLast i8][snrLast_x4 i8][flags u8][uptime_h u16 BE]`(v2 §3.3). ACK 부분의 status = `LP_ACK_OK`, detail = 0.
- 플래그: `CLOCK_STALE` = 시계 무효(epoch ≤ 1,700,000,000) 또는 TIME 을 받은 적 없음(`lastTimeSyncEpoch == 0`) 또는 마지막 TIME 뒤 25 h 초과(§5.2). `UNPROVISIONED` = `provisioned == 0`. `LOW_BATT` = 0 < batt < 3,500 mV(§3.3, 0 = 측정 못 함).
- 헤더: TYPE `LP_TYPE_STATUS`, BLD/ROOM/UNIT = 자기 정체성, TXN 0, flags 0, NET_ID `RP_NET_ID`. 송신은 ACK 와 같은 규칙 — normal 프리앰블, 송신 전 CAD 1회·busy 면 30~120 ms 뒤 1회 더(§6.8).
- 시각: 부팅 보고 = 부팅 1~4 s 뒤 1회(§6.2). 하루 1회 = `nextDailyStatus(now, 18, hash(mac) % 1800)` — 18 = 서버 `STATUS_HOUR_UTC` 기본값(KST 03:00), `SET_PARAM` 은 2단계. TIME `REQUEST_STATUS` = 0~300 s 임의 지연(§3.3). CMD `REQUEST_STATUS` = ACK 뒤 곧바로(0.3 s).
- 재시도: CAD busy 로 못 보냈으면 5 s 뒤 다시. 보냈는데 시계가 아직 없으면 10 min 뒤 다시(§9 "10 min 마다"), 그 사이 시계가 맞으면 건너뛴다.
- 배터리: Heltec V3.2 — GPIO37(ADC_Ctrl)로 분압을 켜고 GPIO1 을 `analogReadMilliVolts` 8회 평균, × 4.9(390 k/100 k). ADC_Ctrl 극성은 Task 3 실기로 정한다. 60 s 마다 다시 잰다.
- 펌웨어 버전 `FW_VER` 3 → 4.
- 커밋 형식 `feat(firmware):`. 로컬 `pio test -e native -f test_node_core` 는 setUp/tearDown 을 정의하므로 Windows 에서도 돈다.

## 파일 구조

| 파일 | 변경 | 책임 |
|---|---|---|
| `firmware/lib/node_core/node_core.h` | 수정 | `Outcome.statusReq/statusSpreadMs`, STATUS 상수, `buildAck`·`statusFlags`·`buildStatus`·`nextDailyStatus`·`macSpread`·`StatusPlan` |
| `firmware/lib/node_core/node_core.cpp` | 수정 | 위 구현, TIME 플래그·CMD REQUEST_STATUS 처리 |
| `firmware/test/test_node_core/test_main.cpp` | 수정 | 시험 추가 |
| `firmware/src/terminal/main.cpp` | 수정 | 업링크 송신 공용화, STATUS 송신·예약, 배터리 측정, FW 4 |
| `docs/specs/2026-09-09-lora-v2-wor-design.md` | 수정(짧게) | §6.2·§6.3 깨어 있는 모드 메모 |

---

### Task 1: STATUS 판단 로직 (`lib/node_core`)

**Files:**
- Modify: `firmware/lib/node_core/node_core.h`
- Modify: `firmware/lib/node_core/node_core.cpp`
- Test: `firmware/test/test_node_core/test_main.cpp`

**Interfaces:**
- Consumes: `ns::RtcState`(`schedVer resvVer examVer identVer provisioned lastTimeSyncEpoch`), `lc::Ack`·`lc::Status`·`lc::Time`·`lc::CmdMsg`·`lc::decCmd`
- Produces(Task 2 가 쓴다):
  ```cpp
  struct Outcome { ...; bool statusReq = false; uint32_t statusSpreadMs = 0; };
  constexpr uint32_t kClockStaleSec = 25u * 3600u;
  constexpr uint16_t kLowBattMv = 3500;
  constexpr uint8_t kStatusHourUtc = 18;
  constexpr uint32_t kStatusSpreadSec = 1800;
  constexpr uint32_t kReqStatusSpreadMs = 300000;
  constexpr uint32_t kStaleRetryMs = 600000;
  constexpr uint32_t kBusyRetryMs = 5000;
  struct LinkInfo { int8_t rssiLast; int8_t snrLastX4; uint16_t uptimeH; };
  lc::Ack buildAck(const ns::RtcState&, uint8_t status, uint8_t detail, uint16_t battMv, uint8_t fw, uint8_t layout);
  uint8_t statusFlags(const ns::RtcState&, uint32_t nowEpoch, uint16_t battMv);
  lc::Status buildStatus(const ns::RtcState&, uint32_t nowEpoch, uint16_t battMv, uint8_t fw, uint8_t layout, const LinkInfo&);
  uint32_t nextDailyStatus(uint32_t nowEpoch, uint8_t hourUtc, uint32_t offsetSec);
  uint32_t macSpread(const uint8_t mac[6], uint32_t mod);
  class StatusPlan { public: void request(uint32_t nowMs, uint32_t delayMs);
                     bool due(uint32_t nowMs, bool clockOk, uint32_t nowEpoch, uint32_t nextStatusEpoch) const;
                     void sent(uint32_t nowMs, bool ok, bool clockOk); };
  ```

- [ ] **Step 1: 실패하는 시험 추가** — `test_main.cpp` 의 `// ---------------- FILE 세션` 앞에 넣고 `main()` 의 `RUN_TEST` 목록 끝에 등록한다.

```cpp
// ---------------- STATUS 요청(§3.3 TIME flags·CMD REQUEST_STATUS) ----------------
void test_time_request_status_flag() {
  lc::Time t{1793156768, LP_TIMEFLAG_REQUEST_STATUS};
  Outcome o = run(hdr(LP_TYPE_TIME, 0, LP_FLAG_BROADCAST, LP_BLD_ALL, 0xFFFF, 0xFF),
                  lc::encTime(t, g_pl, sizeof g_pl));
  TEST_ASSERT_TRUE(o.timeSet);
  TEST_ASSERT_TRUE(o.statusReq);
  TEST_ASSERT_EQUAL_UINT32(kReqStatusSpreadMs, o.statusSpreadMs);
  lc::Time t0{1793156768, 0};
  Outcome o0 = run(hdr(LP_TYPE_TIME, 0, LP_FLAG_BROADCAST, LP_BLD_ALL, 0xFFFF, 0xFF),
                   lc::encTime(t0, g_pl, sizeof g_pl));
  TEST_ASSERT_FALSE(o0.statusReq);
}

void test_cmd_request_status_acks_ok() {
  lc::CmdMsg c{LP_CMD_REQUEST_STATUS, nullptr, 0};
  Outcome o = run(hdr(LP_TYPE_CMD, 7), lc::encCmd(c, g_pl, sizeof g_pl));
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_OK, o.status);
  TEST_ASSERT_TRUE(o.statusReq);
  TEST_ASSERT_EQUAL_UINT32(0, o.statusSpreadMs);
  TEST_ASSERT_FALSE(o.changed);  // 화면은 그대로
  // 같은 TXN 재송 = DUP, 다시 요청하지 않는다
  Outcome d = run(hdr(LP_TYPE_CMD, 7), lc::encCmd(c, g_pl, sizeof g_pl));
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_DUP, d.status);
  TEST_ASSERT_FALSE(d.statusReq);
}

// ---------------- STATUS 내용(§3.3·5.2) ----------------
void test_status_flags() {
  R->provisioned = 1;
  R->lastTimeSyncEpoch = NOW - 3600;
  TEST_ASSERT_EQUAL_HEX8(0, statusFlags(*R, NOW, 4000));
  TEST_ASSERT_EQUAL_HEX8(LP_STATUSFLAG_CLOCK_STALE, statusFlags(*R, 1000, 4000));  // 시계 무효
  R->lastTimeSyncEpoch = 0;
  TEST_ASSERT_EQUAL_HEX8(LP_STATUSFLAG_CLOCK_STALE, statusFlags(*R, NOW, 4000));  // TIME 받은 적 없음
  R->lastTimeSyncEpoch = NOW - kClockStaleSec;
  TEST_ASSERT_EQUAL_HEX8(0, statusFlags(*R, NOW, 4000));  // 딱 25 h 는 아직
  R->lastTimeSyncEpoch = NOW - kClockStaleSec - 1;
  TEST_ASSERT_EQUAL_HEX8(LP_STATUSFLAG_CLOCK_STALE, statusFlags(*R, NOW, 4000));
  R->lastTimeSyncEpoch = NOW;
  TEST_ASSERT_EQUAL_HEX8(LP_STATUSFLAG_LOW_BATT, statusFlags(*R, NOW, 3499));
  TEST_ASSERT_EQUAL_HEX8(0, statusFlags(*R, NOW, 3500));
  TEST_ASSERT_EQUAL_HEX8(0, statusFlags(*R, NOW, 0));  // 0 = 측정 못 함
  R->provisioned = 0;
  TEST_ASSERT_EQUAL_HEX8(LP_STATUSFLAG_UNPROVISIONED, statusFlags(*R, NOW, 4000));
}

void test_build_status_fields() {
  R->provisioned = 1;
  R->schedVer = 12, R->resvVer = 3, R->examVer = 4, R->identVer = 5;
  R->lastTimeSyncEpoch = 0;
  lc::Status s = buildStatus(*R, NOW, 4012, 4, LP_LAYOUT_CLASS, LinkInfo{-56, 44, 7});
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_OK, s.ack.status);
  TEST_ASSERT_EQUAL_UINT8(0, s.ack.detail);
  TEST_ASSERT_EQUAL_UINT16(4012, s.ack.battMv);
  TEST_ASSERT_EQUAL_UINT8(12, s.ack.schedVer);
  TEST_ASSERT_EQUAL_UINT8(3, s.ack.resvVer);
  TEST_ASSERT_EQUAL_UINT8(4, s.ack.examVer);
  TEST_ASSERT_EQUAL_UINT8(5, s.ack.identVer);
  TEST_ASSERT_EQUAL_UINT8(4, s.ack.fw);
  TEST_ASSERT_EQUAL_UINT8(LP_LAYOUT_CLASS, s.ack.layout);
  TEST_ASSERT_EQUAL_INT8(-56, s.rssiLast);
  TEST_ASSERT_EQUAL_INT8(44, s.snrLastX4);
  TEST_ASSERT_EQUAL_UINT16(7, s.uptimeH);
  TEST_ASSERT_EQUAL_HEX8(LP_STATUSFLAG_CLOCK_STALE, s.flags);
  uint8_t out[32];
  TEST_ASSERT_EQUAL(15, lc::encStatus(s, out, sizeof out));  // ACK 10 B + 5 B
}

void test_build_ack_carries_ident_ver() {
  R->schedVer = 9, R->identVer = 2;
  lc::Ack a = buildAck(*R, LP_ACK_GAP, 1, 3900, 4, LP_LAYOUT_EMPTY);
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_GAP, a.status);
  TEST_ASSERT_EQUAL_UINT8(1, a.detail);
  TEST_ASSERT_EQUAL_UINT16(3900, a.battMv);
  TEST_ASSERT_EQUAL_UINT8(9, a.schedVer);
  TEST_ASSERT_EQUAL_UINT8(2, a.identVer);
  TEST_ASSERT_EQUAL_UINT8(LP_LAYOUT_EMPTY, a.layout);
}

// ---------------- STATUS 시각(§6.3) ----------------
void test_next_daily_status() {
  const uint32_t day = 1794873600u;  // 2026-11-17 00:00 UTC
  TEST_ASSERT_EQUAL_UINT32(day + 18 * 3600, nextDailyStatus(day + 4 * 3600, 18, 0));
  TEST_ASSERT_EQUAL_UINT32(day + 86400 + 18 * 3600, nextDailyStatus(day + 18 * 3600, 18, 0));  // 같은 초면 다음 날
  TEST_ASSERT_EQUAL_UINT32(day + 18 * 3600 + 1799, nextDailyStatus(day + 18 * 3600 + 100, 18, 1799));
  TEST_ASSERT_EQUAL_UINT32(day + 86400 + 1000, nextDailyStatus(day + 23 * 3600 + 1800, 23, 3600 + 1000));  // 자정 넘김
}

void test_mac_spread_deterministic() {
  const uint8_t a[6] = {0x3c, 0x0f, 0x02, 0xee, 0x47, 0x10};
  const uint8_t b[6] = {0xac, 0xa7, 0x04, 0x3c, 0x3f, 0x80};
  TEST_ASSERT_EQUAL_UINT32(macSpread(a, 1800), macSpread(a, 1800));
  TEST_ASSERT_TRUE(macSpread(a, 1800) < 1800);
  TEST_ASSERT_TRUE(macSpread(b, 1800) < 1800);
  TEST_ASSERT_NOT_EQUAL(macSpread(a, 1800), macSpread(b, 1800));
  TEST_ASSERT_EQUAL_UINT32(0, macSpread(a, 0));
}

void test_status_plan_request_and_sent() {
  StatusPlan p;
  TEST_ASSERT_FALSE(p.due(1000, false, 0, 0));
  p.request(1000, 2000);
  TEST_ASSERT_FALSE(p.due(2999, false, 0, 0));
  TEST_ASSERT_TRUE(p.due(3000, false, 0, 0));
  p.request(1500, 60000);  // 더 늦은 요청은 이른 예약을 밀지 않는다
  TEST_ASSERT_TRUE(p.due(3000, false, 0, 0));
  p.sent(3000, false, false);  // CAD busy → 5 s 뒤
  TEST_ASSERT_FALSE(p.due(7999, false, 0, 0));
  TEST_ASSERT_TRUE(p.due(8000, false, 0, 0));
  p.sent(8000, true, false);  // 보냈지만 시계 없음 → 10 min 뒤
  TEST_ASSERT_FALSE(p.due(8000 + kStaleRetryMs - 1, false, 0, 0));
  TEST_ASSERT_TRUE(p.due(8000 + kStaleRetryMs, false, 0, 0));
  TEST_ASSERT_FALSE(p.due(8000 + kStaleRetryMs, true, NOW, 0));  // 그 사이 시계가 맞으면 건너뜀
  p.request(9000, 300);  // 새 요청은 시계 재시도 예약을 대신한다
  TEST_ASSERT_TRUE(p.due(9300, true, NOW, 0));
  p.sent(9300, true, true);
  TEST_ASSERT_FALSE(p.due(9300 + kStaleRetryMs, true, NOW, 0));
}

void test_status_plan_daily_and_wrap() {
  StatusPlan p;
  TEST_ASSERT_FALSE(p.due(0, true, NOW, 0));  // 하루 시각이 아직 없음
  TEST_ASSERT_FALSE(p.due(0, true, NOW, NOW + 1));
  TEST_ASSERT_TRUE(p.due(0, true, NOW, NOW));
  TEST_ASSERT_FALSE(p.due(0, false, NOW, NOW));  // 시계 무효면 하루 STATUS 없음
  p.request(0xFFFFF000u, 0x2000);  // millis 넘어감
  TEST_ASSERT_FALSE(p.due(0xFFFFFFFFu, false, 0, 0));
  TEST_ASSERT_TRUE(p.due(0x1000u, false, 0, 0));
}
```

`main()` 에 추가:
```cpp
  RUN_TEST(test_time_request_status_flag);
  RUN_TEST(test_cmd_request_status_acks_ok);
  RUN_TEST(test_status_flags);
  RUN_TEST(test_build_status_fields);
  RUN_TEST(test_build_ack_carries_ident_ver);
  RUN_TEST(test_next_daily_status);
  RUN_TEST(test_mac_spread_deterministic);
  RUN_TEST(test_status_plan_request_and_sent);
  RUN_TEST(test_status_plan_daily_and_wrap);
```
(기존 `test_bad_payload_and_unsupported` 의 CMD 1 = UNSUPPORTED 는 그대로 통과해야 한다.)

- [ ] **Step 2: 실패 확인**

Run: `cd firmware && pio test -e native -f test_node_core`
Expected: 컴파일 실패(`statusReq`·`statusFlags`·`StatusPlan` 없음)

- [ ] **Step 3: 구현** — `node_core.h`

`Outcome` 에 두 필드를 더한다:
```cpp
  bool statusReq = false;       // STATUS 를 보내라(TIME REQUEST_STATUS·CMD REQUEST_STATUS, §3.3)
  uint32_t statusSpreadMs = 0;  // statusReq 일 때 0~이 값 ms 임의 지연(0 = 곧바로)
```
`buildModel` 선언 뒤에:
```cpp
// ---- STATUS 업링크 (v2 §3.3·5.2·6.2·6.3, 절전 1단계) ----
constexpr uint32_t kClockStaleSec = 25u * 3600u;  // §5.2 — 마지막 TIME 뒤 이보다 길면 CLOCK_STALE
constexpr uint16_t kLowBattMv = 3500;             // §3.3 LOW_BATT
constexpr uint8_t kStatusHourUtc = 18;            // 서버 STATUS_HOUR_UTC 기본(KST 03:00). SET_PARAM 은 2단계
constexpr uint32_t kStatusSpreadSec = 1800;       // 하루 STATUS 분산 hash(mac) % 1800 (§6.3)
constexpr uint32_t kReqStatusSpreadMs = 300000;   // TIME REQUEST_STATUS → 0~300 s 임의 지연(§3.3)
constexpr uint32_t kStaleRetryMs = 600000;        // 보냈는데 시계가 안 오면 10 min 뒤 다시(§9)
constexpr uint32_t kBusyRetryMs = 5000;           // CAD busy 로 못 보냈으면 5 s 뒤 다시

struct LinkInfo {
  int8_t rssiLast;   // 마지막으로 받은 내 프레임의 RSSI(dBm)
  int8_t snrLastX4;  // 같은 프레임의 SNR × 4
  uint16_t uptimeH;
};

lc::Ack buildAck(const ns::RtcState& r, uint8_t status, uint8_t detail, uint16_t battMv, uint8_t fw, uint8_t layout);
uint8_t statusFlags(const ns::RtcState& r, uint32_t nowEpoch, uint16_t battMv);
lc::Status buildStatus(const ns::RtcState& r, uint32_t nowEpoch, uint16_t battMv, uint8_t fw, uint8_t layout,
                       const LinkInfo& l);
// now 보다 뒤인 가장 이른 (hourUtc:00 + offsetSec) UTC 시각
uint32_t nextDailyStatus(uint32_t nowEpoch, uint8_t hourUtc, uint32_t offsetSec);
uint32_t macSpread(const uint8_t mac[6], uint32_t mod);  // FNV-1a % mod (mod 0 → 0)

// 깨어 있는 모드의 STATUS 예약. 한 번짜리 예약(millis)과 하루 1회(epoch, RtcState.nextStatusEpoch) 둘을 본다.
// 호출자 몫: 시계가 있을 때 보내기를 시도했으면(성공·실패 모두) nextStatusEpoch 를 nextDailyStatus 로 옮긴다.
class StatusPlan {
 public:
  void request(uint32_t nowMs, uint32_t delayMs);  // nowMs+delayMs 에 한 번. 더 이른 일반 예약이 있으면 그대로
  bool due(uint32_t nowMs, bool clockOk, uint32_t nowEpoch, uint32_t nextStatusEpoch) const;
  // ok=false(채널 사용 중) → kBusyRetryMs 뒤 다시. ok·시계 없음 → kStaleRetryMs 뒤 다시(그 사이 시계가 맞으면
  // 건너뜀). ok·시계 있음 → 예약을 비운다
  void sent(uint32_t nowMs, bool ok, bool clockOk);

 private:
  bool pending_ = false;
  bool onlyIfStale_ = false;
  uint32_t dueMs_ = 0;
};
```

- [ ] **Step 4: 구현** — `node_core.cpp`

`apply()` 의 TIME 분기:
```cpp
    case LP_TYPE_TIME: {
      lc::Time t{};
      if (!lc::decTime(p, h.len, t)) return LP_ACK_BAD_PAYLOAD;
      o.timeSet = true;
      o.epoch = t.epoch;
      if (t.flags & LP_TIMEFLAG_REQUEST_STATUS) {
        o.statusReq = true;
        o.statusSpreadMs = kReqStatusSpreadMs;
      }
      return LP_ACK_OK;
    }
```
`default:` 앞에 CMD 분기를 넣고 default 주석을 고친다:
```cpp
    case LP_TYPE_CMD: {
      lc::CmdMsg c{};
      if (!lc::decCmd(p, h.len, c)) return LP_ACK_BAD_PAYLOAD;
      if (c.cmd != LP_CMD_REQUEST_STATUS) return LP_ACK_UNSUPPORTED;  // 나머지 CMD 는 2단계
      o.statusReq = true;
      return LP_ACK_OK;
    }
    default:  // SET_ROOM 은 2단계(프로비저닝)
      return LP_ACK_UNSUPPORTED;
```
파일 끝(`}  // namespace nc` 앞)에:
```cpp
lc::Ack buildAck(const ns::RtcState& r, uint8_t status, uint8_t detail, uint16_t battMv, uint8_t fw, uint8_t layout) {
  lc::Ack a{};
  a.status = status;
  a.detail = detail;
  a.battMv = battMv;
  a.schedVer = r.schedVer;
  a.resvVer = r.resvVer;
  a.examVer = r.examVer;
  a.identVer = r.identVer;
  a.fw = fw;
  a.layout = layout;
  return a;
}

uint8_t statusFlags(const ns::RtcState& r, uint32_t now, uint16_t battMv) {
  uint8_t f = 0;
  const bool clockOk = now > kClockValidEpoch;
  const bool stale = !clockOk || r.lastTimeSyncEpoch == 0 ||
                     (now > r.lastTimeSyncEpoch && now - r.lastTimeSyncEpoch > kClockStaleSec);
  if (stale) f |= LP_STATUSFLAG_CLOCK_STALE;
  if (!r.provisioned) f |= LP_STATUSFLAG_UNPROVISIONED;
  if (battMv != 0 && battMv < kLowBattMv) f |= LP_STATUSFLAG_LOW_BATT;
  return f;
}

lc::Status buildStatus(const ns::RtcState& r, uint32_t now, uint16_t battMv, uint8_t fw, uint8_t layout,
                       const LinkInfo& l) {
  lc::Status s{};
  s.ack = buildAck(r, LP_ACK_OK, 0, battMv, fw, layout);
  s.rssiLast = l.rssiLast;
  s.snrLastX4 = l.snrLastX4;
  s.flags = statusFlags(r, now, battMv);
  s.uptimeH = l.uptimeH;
  return s;
}

uint32_t nextDailyStatus(uint32_t now, uint8_t hourUtc, uint32_t offsetSec) {
  const uint32_t at = (hourUtc * 3600u + offsetSec) % 86400u;
  uint32_t t = now - now % 86400u + at;
  if (t <= now) t += 86400u;
  return t;
}

uint32_t macSpread(const uint8_t mac[6], uint32_t mod) {
  if (mod == 0) return 0;
  uint32_t h = 2166136261u;
  for (int i = 0; i < 6; ++i) {
    h ^= mac[i];
    h *= 16777619u;
  }
  return h % mod;
}

void StatusPlan::request(uint32_t nowMs, uint32_t delayMs) {
  const uint32_t t = nowMs + delayMs;
  if (pending_ && !onlyIfStale_ && (int32_t)(dueMs_ - t) <= 0) return;
  pending_ = true;
  onlyIfStale_ = false;
  dueMs_ = t;
}

bool StatusPlan::due(uint32_t nowMs, bool clockOk, uint32_t nowEpoch, uint32_t nextStatusEpoch) const {
  if (pending_ && (int32_t)(nowMs - dueMs_) >= 0 && !(onlyIfStale_ && clockOk)) return true;
  return clockOk && nextStatusEpoch != 0 && nowEpoch >= nextStatusEpoch;
}

void StatusPlan::sent(uint32_t nowMs, bool ok, bool clockOk) {
  if (!ok) {
    pending_ = true;
    onlyIfStale_ = false;
    dueMs_ = nowMs + kBusyRetryMs;
    return;
  }
  if (!clockOk) {
    pending_ = true;
    onlyIfStale_ = true;
    dueMs_ = nowMs + kStaleRetryMs;
    return;
  }
  pending_ = false;
  onlyIfStale_ = false;
}
```

- [ ] **Step 5: 통과 확인**

Run: `cd firmware && pio test -e native -f test_node_core` 와 `pio test -e native -f test_node_store -f test_schedule`
Expected: 모두 PASS(기존 시험 포함). `clang-format --dry-run --Werror` 로 바꾼 세 파일 확인.

- [ ] **Step 6: Commit**

```bash
git add firmware/lib/node_core firmware/test/test_node_core
git commit -m "feat(firmware): STATUS 판단 로직 — 플래그·하루 시각·예약(StatusPlan), TIME/CMD REQUEST_STATUS"
```

---

### Task 2: 노드 연결 (`src/terminal/main.cpp`)

**Files:**
- Modify: `firmware/src/terminal/main.cpp`

**Interfaces:**
- Consumes: Task 1 의 전부, `lc::encStatus`, `lc::encAck`

실기 전용(Arduino) — 호스트 시험 없음. 검증은 빌드 + Task 3.

- [ ] **Step 1: 상수·전역** — `BATT_MV_USB` 를 지우고:

```cpp
constexpr uint8_t FW_VER = 4;
// 배터리(Heltec V3.2): GPIO37 로 분압(390 k/100 k)을 켜고 GPIO1 을 잰다. 극성은 Task 3 실기에서 확정
constexpr int VBAT_ADC = 1, VBAT_CTRL = 37;
constexpr uint8_t VBAT_CTRL_ON = HIGH;
constexpr float VBAT_DIVIDER = 4.9f;
constexpr uint32_t BATT_PERIOD_MS = 60000;
```
`g_layout` 근처에:
```cpp
uint16_t g_battMv = 0;    // 0 = 아직 못 잼
int8_t g_rssiLast = 0;    // 마지막으로 받은 내 프레임
int8_t g_snrX4 = 0;
uint32_t g_spread = 0;    // 하루 STATUS 분산(초) = hash(mac) % 1800
nc::StatusPlan g_status;
```

- [ ] **Step 2: 배터리 측정**

```cpp
uint16_t readBattMv() {
  pinMode(VBAT_CTRL, OUTPUT);
  digitalWrite(VBAT_CTRL, VBAT_CTRL_ON);
  delay(10);
  uint32_t sum = 0;
  for (int i = 0; i < 8; ++i) sum += analogReadMilliVolts(VBAT_ADC);
  digitalWrite(VBAT_CTRL, VBAT_CTRL_ON == HIGH ? LOW : HIGH);
  return (uint16_t)(sum / 8 * VBAT_DIVIDER);
}
```

- [ ] **Step 3: 업링크 송신 공용화** — `sendAck` 의 송신 부분을 떼어 `txUplink` 로:

```cpp
// §6.8 업링크 송신(ACK·STATUS 공용). 채널이 바쁘면 false
bool txUplink(const lc::Header& h, const uint8_t* pl, size_t pn, const char* what) {
  uint8_t out[64];
  size_t n = lc::encodeFrame(h, pl, (uint8_t)pn, out, sizeof out);
  delay(20);  // 모뎀이 송신 → 수신으로 넘어갈 틈
  if (!channelFree()) {
    Serial.printf("[node] %s 포기 — 채널 사용 중\n", what);
    listen();
    return false;
  }
  g_irq = false;
  uint32_t t0 = millis();
  radio.setPreambleLength(RP_PREAMBLE_NORMAL);  // 업링크는 짧은 프리앰블(§6.8)
  int st = radio.startTransmit(out, n);
  bool done = st == RADIOLIB_ERR_NONE && waitIrq(2000);
  radio.finishTransmit();
  Serial.printf("[node] %s 송신 st=%d done=%d %lums\n", what, st, done, (unsigned long)(millis() - t0));
  listen();
  return done;
}

void sendAck(const lc::Header& req, uint8_t status, uint8_t detail) {
  const lc::Ack a = nc::buildAck(g_rtc, status, detail, g_battMv, FW_VER, g_layout);
  uint8_t pl[32];
  size_t pn = lc::encAck(a, pl, sizeof pl);
  lc::Header h{};
  h.ver = LP_PROTO_VER;
  h.netId = req.netId;
  h.type = LP_TYPE_ACK;
  h.bld = req.bld;
  h.room = req.room;
  h.unit = req.unit;
  h.txn = req.txn;
  (void)txUplink(h, pl, pn, "ACK");
}

bool sendStatus(uint32_t now) {
  const uint32_t up = millis() / 3600000UL;
  const lc::Status s = nc::buildStatus(g_rtc, now, g_battMv, FW_VER, g_layout,
                                       nc::LinkInfo{g_rssiLast, g_snrX4, (uint16_t)(up > 65535 ? 65535 : up)});
  uint8_t pl[32];
  size_t pn = lc::encStatus(s, pl, sizeof pl);
  lc::Header h{};
  h.ver = LP_PROTO_VER;
  h.netId = RP_NET_ID;
  h.type = LP_TYPE_STATUS;
  h.bld = g_rtc.bld;
  h.room = g_rtc.room;
  h.unit = g_rtc.unit;
  h.txn = 0;
  const bool done = txUplink(h, pl, pn, "STATUS");
  Serial.printf("[node] STATUS flags=0x%02x batt=%umV ver S%u/R%u/E%u\n", s.flags, g_battMv, g_rtc.schedVer,
                g_rtc.resvVer, g_rtc.examVer);
  return done;
}
```
`pollRadio()` 끝의 `listen()` 은 그대로 둔다(txUplink 도 listen 하지만 ACK 없이 끝나는 경로가 있다).

- [ ] **Step 4: pollRadio 연결** — 내 프레임이면 링크 값을 남기고, TIME·STATUS 요청을 처리:

```cpp
  if (ok && nc::isForMe(me(), h)) {
    g_lastRxMs = millis();
    g_rssiLast = (int8_t)constrain((int)lroundf(rssi), -128, 127);
    g_snrX4 = (int8_t)constrain((int)lroundf(snr * 4), -128, 127);
    ...
    if (o.timeSet) {
      ... (기존)
      if (g_rtc.nextStatusEpoch == 0) g_rtc.nextStatusEpoch = nc::nextDailyStatus(o.epoch, nc::kStatusHourUtc, g_spread);
    }
    if (o.statusReq) g_status.request(millis(), 300 + (o.statusSpreadMs ? esp_random() % o.statusSpreadMs : 0));
```

- [ ] **Step 5: 예약 실행** — `loop()` 의 1 s 틱 안, `if (!clockValid()) return;` **앞**에:

```cpp
  maybeMeasureBatt();
  maybeSendStatus();
```
```cpp
void maybeMeasureBatt() {
  static uint32_t last = 0;
  if (g_battMv != 0 && millis() - last < BATT_PERIOD_MS) return;
  last = millis();
  g_battMv = readBattMv();
}

void maybeSendStatus() {
  const uint32_t ms = millis();
  const uint32_t now = (uint32_t)time(nullptr);
  const bool clk = clockValid();
  if (!g_status.due(ms, clk, now, g_rtc.nextStatusEpoch)) return;
  const bool done = sendStatus(now);
  g_status.sent(ms, done, clk);
  if (clk) {
    g_rtc.nextStatusEpoch = nc::nextDailyStatus(now, nc::kStatusHourUtc, g_spread);
    ns::rtcSeal(g_rtc);
  }
}
```

- [ ] **Step 6: setup** — `radioBegin()` 뒤:

```cpp
  const uint64_t efuse = ESP.getEfuseMac();
  uint8_t mac[6];
  for (int i = 0; i < 6; ++i) mac[i] = (uint8_t)(efuse >> (8 * i));
  g_spread = nc::macSpread(mac, nc::kStatusSpreadSec);
  g_battMv = readBattMv();
  if (g_rtc.provisioned) g_status.request(millis(), 1000 + esp_random() % 3000);  // 부팅 보고(§6.2)
```
부팅 로그에 `batt=%umV` 를 더한다. `m.battMv = BATT_MV_USB;` → `m.battMv = g_battMv;`. 파일 머리 주석의 "배터리 측정은 S9" 류 문구를 "STATUS(부팅·하루 1회·요청)·배터리 실측 — 절전 1단계" 로 고친다.

- [ ] **Step 7: 빌드**

Run: `cd firmware && pio run -e terminal`
Expected: SUCCESS. `clang-format --dry-run --Werror firmware/src/terminal/main.cpp` clean.

- [ ] **Step 8: Commit**

```bash
git add firmware/src/terminal/main.cpp
git commit -m "feat(firmware): 노드가 STATUS 를 보낸다 — 부팅 보고(시계 요청)·하루 1회·REQUEST_STATUS, 배터리 실측, FW 4"
```

---

### Task 3: 두 노드 실기 + 기록

**Files:**
- Modify: `firmware/src/terminal/main.cpp`(배터리 극성 확정 시)
- Modify: `docs/specs/2026-09-09-lora-v2-wor-design.md`(§6.2 끝에 메모)
- Modify: `docs/progress.html`(cw-14 비고)

- [ ] **Step 1: 배터리 극성** — 임시로 부팅 때 두 극성(HIGH·LOW) 값을 모두 찍어 4.9 배 값이 3.0~4.3 V 인 쪽을 `VBAT_CTRL_ON` 으로 정한다(USB 충전 중이면 4.1~4.2 V 근처). 임시 로그는 지운다.
- [ ] **Step 2: 굽기** — E301·E803(빌드 플래그) 둘 다.
- [ ] **Step 3: 확인표**

| 확인 | 기대 |
|---|---|
| RST 뒤 | 1~4 s 안 `STATUS 송신 done=1`, flags=0x01 → 모뎀Pi 로그 타겟 TIME → **모뎀Pi 재시작 없이** 수 초 안 렌더 |
| 서버 terminal_status | batt_mv 실측값, 최근 응답 갱신 |
| 저장 비우고 부팅(`pio run -t erase` 후 굽기, E301) | 부팅 STATUS 의 ver 0 → 서버가 FILE 재동기를 스스로 건다(0단계 알려진 한계 해결) |
| 하루 STATUS | 로그의 nextStatusEpoch(= 18:00 UTC + 분산) 확인 |
| ACK | batt 실측값, 기존 지연 그대로 |

- [ ] **Step 4: 문서** — v2 §6.2 끝: `- 깨어 있는 모드(절전 1단계, 2026-11)도 부팅 보고·하루 1회·REQUEST_STATUS STATUS 를 보낸다. 보냈는데 시계가 안 오면 10 min, CAD busy 면 5 s 뒤 다시.` progress.html cw-14 비고에 PR 번호.
- [ ] **Step 5: Commit · PR**

## Self-Review

- 스펙 대응: §3.3 STATUS 형식·플래그(Task 1 buildStatus·statusFlags), §5.2 CLOCK_STALE 25 h, §6.2 부팅 보고(Task 2 setup), §6.3 하루 1회 hash(mac)%1800(nextDailyStatus·macSpread), §3.3 TIME REQUEST_STATUS 0~300 s, CMD REQUEST_STATUS, §6.8 CAD(txUplink 재사용), §9 10 min 재시도. 배터리 3.3 V 렌더 중단은 3단계(절전) 몫.
- 서버·모뎀Pi 변경 없음 — CLOCK_STALE → 타겟 TIME(uplink.py `_queue_time`), 버전 비교 재동기(api.py) 이미 있음.

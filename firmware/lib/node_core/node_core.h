#pragma once
// S8 노드 펌웨어(깨어 있는 모드)의 순수 로직 — 수신 프레임 적용(v2 §3.4·3.5·6.4·6.6)은 ns::NodeStore 위에서
// 한다. 하드웨어 없음: 저장(LittleFS·NVS)·라디오·패널은 src/terminal/ 어댑터가 한다.
#include <stddef.h>
#include <stdint.h>

#include "lora_codec.h"
#include "node_store.h"
#include "render_model.h"
#include "schedule.h"

namespace nc {

constexpr uint8_t kNoAck = 0xFF;                    // ACK 를 보내지 않는다(ACK_REQ 없음·브로드캐스트)
constexpr uint32_t kClockValidEpoch = 1700000000u;  // §5.2 clockValid
constexpr uint16_t kFileMax = ns::kSchedFileMax;    // 5,184 B — 가장 큰 FILE 본문
constexpr uint8_t kFileChunksMax = kFileMax / LP_FILE_CHUNK_MAX + 1;

struct Ident {
  uint8_t bld;
  uint16_t room;
  uint8_t unit;
};

// FILE 세션 수신 버퍼 — 영속 아님(재부팅하면 서버가 다시 보낸다).
struct FileRx {
  bool active;
  uint8_t kind, newVer, nChunks;
  uint16_t len;
  bool have[kFileChunksMax];
  uint8_t buf[kFileMax];
};

struct Outcome {
  uint8_t status = kNoAck;  // 보낼 ACK status, kNoAck 면 보내지 않음
  uint8_t detail = 0;
  bool changed = false;  // 저장 상태가 바뀌었다(다시 그리기 필요)
  bool timeSet = false;
  uint32_t epoch = 0;           // timeSet 이면 맞출 UTC epoch
  bool statusReq = false;       // STATUS 를 보내라(TIME REQUEST_STATUS·CMD REQUEST_STATUS, §3.3)
  uint32_t statusSpreadMs = 0;  // statusReq 일 때 0~이 값 ms 임의 지연(0 = 곧바로)
};

bool isForMe(const Ident&, const lc::Header&);  // §6.6
bool gap(uint8_t oldVer, uint8_t newVer);       // (new − old) mod 255 ≠ 1 (§12, #74 12)
ns::Date todayOf(uint32_t epochUtc);            // KST 날짜, ResvRec 와 같은 표현(y = year-2000)
// §6.4 dispatch. DUP 판정·버전·lastTxn(결과 OK/GAP 일 때만, #74 10) 까지 한다. nowEpoch = 노드 시계(UTC)
Outcome handleFrame(ns::NodeStore&, FileRx&, const lc::Header&, const uint8_t* payload, uint32_t nowEpoch);

// r 의 정체성·오늘 슬롯(r.slotsDay 가 오늘 요일과 다르면 슬롯 없음으로 본다)·예약·시험으로 m 을 채운다.
sch::LayoutDecision buildModel(const ns::RtcState& r, uint32_t epochUtc, RenderModel& m);

// ---- STATUS 업링크 (v2 §3.3·5.2·6.2·6.3, 절전 1단계) ----
constexpr uint32_t kClockStaleSec = 25u * 3600u;  // §5.2 — 마지막 TIME 뒤 이보다 길면 CLOCK_STALE
constexpr uint16_t kLowBattMv = 3500;             // §3.3 LOW_BATT
constexpr uint8_t kStatusHourUtc = 18;            // 서버 STATUS_HOUR_UTC 기본(KST 03:00). SET_PARAM 은 2단계
constexpr uint32_t kStatusSpreadSec = 1800;       // 하루 STATUS 분산 hash(mac) % 1800 (§6.3)
constexpr uint32_t kReqStatusSpreadMs = 300000;   // TIME REQUEST_STATUS → 0~300 s 임의 지연(§3.3)
constexpr uint32_t kStaleRetryMs = 600000;        // 보냈는데 시계가 안 오면 10 min 뒤 다시(§9)
constexpr uint32_t kBusyRetryMs = 5000;           // CAD busy 로 못 보냈으면 5 s 뒤 다시
constexpr uint32_t kAfterTimeStatusMs =
    3000;  // CLOCK_STALE 로 알린 뒤 시각을 받으면 이만큼 뒤 STATUS 한 번 더

struct LinkInfo {
  int8_t rssiLast;   // 마지막으로 받은 내 프레임의 RSSI(dBm)
  int8_t snrLastX4;  // 같은 프레임의 SNR × 4
  uint16_t uptimeH;
};

lc::Ack buildAck(const ns::RtcState& r, uint8_t status, uint8_t detail, uint16_t battMv, uint8_t fw,
                 uint8_t layout);
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
  // nowMs+delayMs 에 한 번. 더 이른 일반 예약이 있으면 그대로
  void request(uint32_t nowMs, uint32_t delayMs);
  bool due(uint32_t nowMs, bool clockOk, uint32_t nowEpoch, uint32_t nextStatusEpoch) const;
  // ok=false(채널 사용 중) → kBusyRetryMs 뒤 다시. ok·시계 없음 → kStaleRetryMs 뒤 다시(그 사이 시계가 맞으면
  // 건너뜀). ok·시계 있음 → 예약을 비운다. flags = 보낸 STATUS 의 플래그(CLOCK_STALE 기억용)
  void sent(uint32_t nowMs, bool ok, bool clockOk, uint8_t flags = 0);
  // TIME 으로 시계를 맞췄다. 마지막으로 보낸 STATUS 가 CLOCK_STALE 이었으면 kAfterTimeStatusMs 뒤 한 번 더 —
  // 서버의 clock_stale 표시는 다음 STATUS 까지 남기 때문(부팅 보고 뒤 하루 내내 "시계 이상"으로 보이지 않게)
  void onTimeSet(uint32_t nowMs);

 private:
  bool pending_ = false;
  bool onlyIfStale_ = false;
  bool staleSent_ = false;
  uint32_t dueMs_ = 0;
};

}  // namespace nc

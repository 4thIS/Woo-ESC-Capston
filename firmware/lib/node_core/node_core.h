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
  uint32_t epoch = 0;  // timeSet 이면 맞출 UTC epoch
};

bool isForMe(const Ident&, const lc::Header&);  // §6.6
bool gap(uint8_t oldVer, uint8_t newVer);       // (new − old) mod 255 ≠ 1 (§12, #74 12)
ns::Date todayOf(uint32_t epochUtc);            // KST 날짜, ResvRec 와 같은 표현(y = year-2000)
// §6.4 dispatch. DUP 판정·버전·lastTxn(결과 OK/GAP 일 때만, #74 10) 까지 한다. nowEpoch = 노드 시계(UTC)
Outcome handleFrame(ns::NodeStore&, FileRx&, const lc::Header&, const uint8_t* payload, uint32_t nowEpoch);

// r 의 정체성·오늘 슬롯(r.slotsDay 가 오늘 요일과 다르면 슬롯 없음으로 본다)·예약·시험으로 m 을 채운다.
sch::LayoutDecision buildModel(const ns::RtcState& r, uint32_t epochUtc, RenderModel& m);

}  // namespace nc

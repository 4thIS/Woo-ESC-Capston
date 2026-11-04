#pragma once
// S8 노드 펌웨어(깨어 있는 모드)의 순수 로직 — 수신 프레임 적용(v2 §3.4·3.5·6.4·6.6)과 상태 판단(§5.3) →
// RenderModel. 하드웨어 없음: 저장(LittleFS·NVS)·라디오·패널은 src/terminal/ 어댑터가 한다.
//
// 임시 구현 주의(2026-11-04, 경진대회 시연용): 상태 판단(decide)·저장 구조(State)는
// dh-08(lib/schedule·lib/node_store, #74)이 들어오면 그쪽 determineLayout·KvStore/FileStore 로 바꿔 끼운다.
// 규칙·벡터는 v2 §5.3 과 lora_proto/room_state_vectors.json 그대로라, 바꿔 끼워도 같은 테스트를 통과해야
// 한다.
#include <stddef.h>
#include <stdint.h>

#include "lora_codec.h"
#include "render_model.h"

namespace nc {

constexpr uint8_t kNoAck = 0xFF;  // ACK 를 보내지 않는다(ACK_REQ 없음·브로드캐스트)
constexpr uint8_t kResvMax = 24, kExamMax = 8;
constexpr uint16_t kFileMax = 8192;  // 주간 96 슬롯 × (레코드 머리 2 + 본문 ≤ 40) ≈ 4 KB 에 여유
constexpr uint8_t kFileChunksMax = kFileMax / LP_FILE_CHUNK_MAX + 1;

struct Ident {
  uint8_t bld;
  uint16_t room;
  uint8_t unit;
};

// 영속 상태 — 어댑터가 통째로 저장한다(저장 계층 dh-08 전까지의 임시 형식).
struct State {
  uint8_t schedVer, resvVer, examVer, lastTxn;
  uint8_t nSlots;
  lc::SlotRec slots[LP_SLOT_WEEK_MAX];
  uint8_t nResv;
  lc::ResvRec resv[kResvMax];
  uint8_t nExam;
  lc::ExamRec exams[kExamMax];
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
  bool changed = false;  // State 가 바뀌었다(저장·다시 그리기 필요)
  bool timeSet = false;
  uint32_t epoch = 0;  // timeSet 이면 맞출 UTC epoch
};

void clear(State&);
bool isForMe(const Ident&, const lc::Header&);  // §6.6
bool gap(uint8_t oldVer, uint8_t newVer);       // (new − old) mod 255 ≠ 1 (§12, #74 12)
// §6.4 dispatch. DUP 판정·버전·lastTxn(결과 OK/GAP 일 때만, #74 10) 까지 한다.
Outcome handleFrame(State&, FileRx&, const lc::Header&, const uint8_t* payload);

// ---------- 상태 판단 (§5.3) ----------
struct Item {
  uint16_t s, e;  // 자정부터 분
  uint8_t type;   // lora_proto SlotType
  bool resv;
  uint8_t idx;  // State.slots / State.resv 의 위치
};
struct Decision {
  uint8_t layout;
  int8_t src;     // 상태를 정한 항목(items 안 위치), 쉬는시간이면 다음 수업, 없으면 -1
  int16_t until;  // 상태가 처음 바뀌는 분, 없으면 -1(자정까지)
};
// items: 그날의 정규 슬롯(resv=false)과 승인 예약(resv=true). 순서는 상관없다.
Decision decide(const Item* items, int n, bool inExam, uint16_t atMin);

// KST(epoch + 9 h) 변환 — §5.2
struct Kst {
  uint8_t y2k, mon, mday, wday;  // y2k = year − 2000, wday 1=월..7=일
  uint16_t min;                  // 자정부터 분
};
Kst toKst(uint32_t epochUtc);
constexpr uint32_t kClockValidEpoch = 1700000000u;  // §5.2 clockValid

// 화면 모델을 채우고 판정을 돌려준다. battMv 는 어댑터가 넣는다.
Decision buildModel(const Ident&, const State&, uint32_t epochUtc, RenderModel&);

}  // namespace nc

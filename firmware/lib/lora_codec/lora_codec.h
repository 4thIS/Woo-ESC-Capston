#pragma once
// 공중 프레임 v2 codec — 하드웨어 의존 없음. 상수는 lora_proto/proto.h 가 원본.
#include <stddef.h>
#include <stdint.h>

#include "proto.h"
#include "radio_params.h"

namespace lc {

uint8_t crc8(const uint8_t* d, size_t n);    // poly 0x07 init 0
uint16_t crc16(const uint8_t* d, size_t n);  // CCITT-FALSE

struct Header {
  uint8_t ver, flags, netId, type, bld;
  uint16_t room;
  uint8_t unit, txn, len;
};

// 성공 시 총 길이(헤더+페이로드+CRC), 실패 시 0. cap 은 out 버퍼 크기.
size_t encodeFrame(const Header& h, const uint8_t* payload, uint8_t len, uint8_t* out, size_t cap);
// 성공 시 h 채우고 payload 는 buf 안을 가리킴(복사 없음).
bool decodeFrame(const uint8_t* buf, size_t n, Header& h, const uint8_t*& payload, uint8_t netId = RP_NET_ID);
// v2 §4.4: NET_ID·TYPE==ACK·BLD/ROOM/UNIT/TXN 일치
bool matchesAck(const Header& req, const Header& rx);

// ---------- §3.3 페이로드 구조체 ----------
struct Time {
  uint32_t epoch;
  uint8_t flags;
};
struct SlotRec {
  uint8_t day, sH, sM, eH, eM, type;
  char subj[LP_SUBJ_MAX + 1];
  char prof[LP_PROF_MAX + 1];
};
struct SlotDel {
  uint8_t day, sH, sM;
};
struct DayClear {
  uint8_t day;
};
struct ResvRec {
  uint16_t resvId;
  uint8_t y, m, d, sH, sM, eH, eM, type;  // y = year-2000 (wire)
  char subj[LP_SUBJ_MAX + 1];
  char prof[LP_PROF_MAX + 1];
};
struct ResvDel {
  uint16_t resvId;
};
struct ExamRec {
  uint16_t examId;
  uint8_t y1, m1, d1, y2, m2, d2;  // y1, y2 = year-2000 (wire)
};
struct ExamDel {
  uint16_t examId;
};
struct FileBegin {
  uint8_t kind;
  uint16_t totalLen;
  uint8_t nChunks;
};
struct FileData {
  uint8_t seq;
  const uint8_t* data;
  uint8_t len;
};
struct FileEnd {
  uint16_t crc;
};
struct CmdMsg {
  uint8_t cmd;
  const uint8_t* args;
  uint8_t argsLen;
};
struct SetRoom {
  uint8_t mac[6];
  uint8_t bld;
  uint16_t room;
  uint8_t unit;
};
struct Ack {
  uint8_t status, detail;
  uint16_t battMv;
  uint8_t schedVer, resvVer, examVer, identVer, fw, layout;
};
struct Status {
  Ack ack;
  int8_t rssiLast, snrLastX4;
  uint8_t flags;
  uint16_t uptimeH;
};
struct Hello {
  uint8_t mac[6];
  uint8_t fw;
  uint16_t battMv;
};

// enc*: 성공 시 길이, 실패(범위·cap) 시 0.  dec*: 길이·범위·잔여 바이트 검사, 실패 시 false.
size_t encTime(const Time&, uint8_t* out, size_t cap);
bool decTime(const uint8_t* p, uint8_t n, Time&);
size_t encSlotSet(uint8_t newVer, const SlotRec&, uint8_t* out, size_t cap);
bool decSlotSet(const uint8_t* p, uint8_t n, uint8_t& newVer, SlotRec&);
size_t encSlotDel(uint8_t newVer, const SlotDel&, uint8_t* out, size_t cap);
bool decSlotDel(const uint8_t* p, uint8_t n, uint8_t& newVer, SlotDel&);
size_t encDayClear(uint8_t newVer, const DayClear&, uint8_t* out, size_t cap);
bool decDayClear(const uint8_t* p, uint8_t n, uint8_t& newVer, DayClear&);
size_t encResvSet(uint8_t newVer, const ResvRec&, uint8_t* out, size_t cap);
bool decResvSet(const uint8_t* p, uint8_t n, uint8_t& newVer, ResvRec&);
size_t encResvDel(uint8_t newVer, const ResvDel&, uint8_t* out, size_t cap);
bool decResvDel(const uint8_t* p, uint8_t n, uint8_t& newVer, ResvDel&);
size_t encExamSet(uint8_t newVer, const ExamRec&, uint8_t* out, size_t cap);
bool decExamSet(const uint8_t* p, uint8_t n, uint8_t& newVer, ExamRec&);
size_t encExamDel(uint8_t newVer, const ExamDel&, uint8_t* out, size_t cap);
bool decExamDel(const uint8_t* p, uint8_t n, uint8_t& newVer, ExamDel&);
size_t encFileBegin(uint8_t newVer, const FileBegin&, uint8_t* out, size_t cap);
bool decFileBegin(const uint8_t* p, uint8_t n, uint8_t& newVer, FileBegin&);
size_t encFileData(const FileData&, uint8_t* out, size_t cap);
bool decFileData(const uint8_t* p, uint8_t n, FileData&);
size_t encFileEnd(const FileEnd&, uint8_t* out, size_t cap);
bool decFileEnd(const uint8_t* p, uint8_t n, FileEnd&);
size_t encCmd(const CmdMsg&, uint8_t* out, size_t cap);
bool decCmd(const uint8_t* p, uint8_t n, CmdMsg&);
size_t encSetRoom(uint8_t newVer, const SetRoom&, uint8_t* out, size_t cap);
bool decSetRoom(const uint8_t* p, uint8_t n, uint8_t& newVer, SetRoom&);
size_t encAck(const Ack&, uint8_t* out, size_t cap);
bool decAck(const uint8_t* p, uint8_t n, Ack&);
size_t encStatus(const Status&, uint8_t* out, size_t cap);
bool decStatus(const uint8_t* p, uint8_t n, Status&);
size_t encHello(const Hello&, uint8_t* out, size_t cap);
bool decHello(const uint8_t* p, uint8_t n, Hello&);

// FILE 본문(레코드 스트림) 순회 — 노드가 /schedule.bin 등을 읽을 때 사용.
// pos 는 0 에서 시작해 호출마다 전진. 끝이면 false. 형식 오류면 false + pos 를 n 으로 설정.
bool nextRecord(const uint8_t* body, uint16_t n, uint16_t& pos, uint8_t& recType, const uint8_t*& rec,
                uint8_t& recLen);
// 레코드 본문(NEW_VER 없음) 디코더 — SLOT_SET/RESV_SET/EXAM_SET 페이로드의 NEW_VER 뒤와 같은 형식
// 문자열은 UTF-8 유효성 검사 없이 바이트 그대로 복사한다 (Python codec 은 검사함) — 노드는 opaque bytes 로
// 취급
bool decSlotBody(const uint8_t* p, uint8_t n, SlotRec&);
bool decResvBody(const uint8_t* p, uint8_t n, ResvRec&);
bool decExamBody(const uint8_t* p, uint8_t n, ExamRec&);
size_t encSlotBody(const SlotRec&, uint8_t* out, size_t cap);
size_t encResvBody(const ResvRec&, uint8_t* out, size_t cap);
size_t encExamBody(const ExamRec&, uint8_t* out, size_t cap);

}  // namespace lc

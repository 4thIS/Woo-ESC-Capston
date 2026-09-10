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

}  // namespace lc

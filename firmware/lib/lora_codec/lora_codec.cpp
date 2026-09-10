#include "lora_codec.h"

namespace lc {

uint8_t crc8(const uint8_t* d, size_t n) {
  uint8_t c = 0;
  for (size_t i = 0; i < n; ++i) {
    c ^= d[i];
    for (int b = 0; b < 8; ++b) c = (c & 0x80) ? (uint8_t)((c << 1) ^ 0x07) : (uint8_t)(c << 1);
  }
  return c;
}

uint16_t crc16(const uint8_t* d, size_t n) {
  uint16_t c = 0xFFFF;
  for (size_t i = 0; i < n; ++i) {
    c ^= (uint16_t)d[i] << 8;
    for (int b = 0; b < 8; ++b) c = (c & 0x8000) ? (uint16_t)((c << 1) ^ 0x1021) : (uint16_t)(c << 1);
  }
  return c;
}

size_t encodeFrame(const Header& h, const uint8_t* payload, uint8_t len, uint8_t* out, size_t cap) {
  if (len > LP_MAX_PAYLOAD || (h.flags & 0xF0) || h.ver > 15) return 0;
  size_t total = LP_HEADER_LEN + len + 1;
  if (cap < total) return 0;
  out[0] = (uint8_t)((h.ver << 4) | (h.flags & 0x0F));
  out[1] = h.netId;
  out[2] = h.type;
  out[3] = h.bld;
  out[4] = (uint8_t)(h.room >> 8);
  out[5] = (uint8_t)(h.room & 0xFF);
  out[6] = h.unit;
  out[7] = h.txn;
  out[8] = len;
  for (uint8_t i = 0; i < len; ++i) out[LP_HEADER_LEN + i] = payload[i];
  out[total - 1] = crc8(out, total - 1);
  return total;
}

bool decodeFrame(const uint8_t* buf, size_t n, Header& h, const uint8_t*& payload, uint8_t netId) {
  if (n < LP_HEADER_LEN + 1) return false;
  if ((buf[0] >> 4) != LP_PROTO_VER) return false;
  if (buf[1] != netId) return false;
  uint8_t len = buf[8];
  if (n != (size_t)LP_HEADER_LEN + len + 1) return false;
  if (crc8(buf, n - 1) != buf[n - 1]) return false;
  h.ver = buf[0] >> 4;
  h.flags = buf[0] & 0x0F;
  h.netId = buf[1];
  h.type = buf[2];
  h.bld = buf[3];
  h.room = (uint16_t)((buf[4] << 8) | buf[5]);
  h.unit = buf[6];
  h.txn = buf[7];
  h.len = len;
  payload = buf + LP_HEADER_LEN;
  return true;
}

bool matchesAck(const Header& req, const Header& rx) {
  return rx.type == LP_TYPE_ACK && rx.netId == req.netId && rx.bld == req.bld && rx.room == req.room &&
         rx.unit == req.unit && rx.txn == req.txn;
}

}  // namespace lc

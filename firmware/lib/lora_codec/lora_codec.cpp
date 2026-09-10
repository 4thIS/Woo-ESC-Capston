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

// ---------- 바이트 커서 ----------
namespace {

struct W {
  uint8_t* o;
  size_t cap, i = 0;
  bool ok = true;
  W(uint8_t* out, size_t c) : o(out), cap(c) {}
  void u8(unsigned v, unsigned lo = 0, unsigned hi = 255) {
    if (v < lo || v > hi || i >= cap) {
      ok = false;
      return;
    }
    o[i++] = (uint8_t)v;
  }
  void u16(unsigned v) {
    u8(v >> 8);
    u8(v & 0xFF);
  }
  void u32(uint32_t v) {
    u16(v >> 16);
    u16(v & 0xFFFF);
  }
  void raw(const uint8_t* p, size_t n) {
    if (i + n > cap) {
      ok = false;
      return;
    }
    for (size_t k = 0; k < n; ++k) o[i++] = p[k];
  }
  void str(const char* s, size_t maxLen) {
    size_t n = 0;
    while (s[n] && n <= maxLen) ++n;
    if (n > maxLen) {
      ok = false;
      return;
    }
    u8((unsigned)n);
    raw((const uint8_t*)s, n);
  }
  size_t done() const { return ok ? i : 0; }
};

struct R {
  const uint8_t* p;
  size_t n, i = 0;
  bool ok = true;
  R(const uint8_t* b, size_t len) : p(b), n(len) {}
  uint8_t u8(unsigned lo = 0, unsigned hi = 255) {
    if (i >= n) {
      ok = false;
      return 0;
    }
    uint8_t v = p[i++];
    if (v < lo || v > hi) ok = false;
    return v;
  }
  uint16_t u16() {
    uint16_t a = u8();
    return (uint16_t)((a << 8) | u8());
  }
  uint32_t u32() {
    uint32_t a = u16();
    return (a << 16) | u16();
  }
  const uint8_t* raw(size_t k) {
    if (i + k > n) {
      ok = false;
      return nullptr;
    }
    const uint8_t* q = p + i;
    i += k;
    return q;
  }
  void str(char* dst, size_t maxLen) {
    uint8_t len = u8();
    if (!ok || len > maxLen) {
      ok = false;
      dst[0] = 0;
      return;
    }
    const uint8_t* s = raw(len);
    if (!ok) {
      dst[0] = 0;
      return;
    }
    for (uint8_t k = 0; k < len; ++k) dst[k] = (char)s[k];
    dst[len] = 0;
  }
  bool done() const { return ok && i == n; }
};

void hm(W& w, uint8_t h, uint8_t m) {
  w.u8(h, 0, 23);
  w.u8(m, 0, 59);
}

}  // namespace

// ---------- 본문(NEW_VER 없음) — FILE 레코드와 공유 ----------
size_t encSlotBody(const SlotRec& s, uint8_t* out, size_t cap) {
  W w(out, cap);
  w.u8(s.day, 1, 7);
  hm(w, s.sH, s.sM);
  hm(w, s.eH, s.eM);
  w.u8(s.type, 1, 6);
  w.str(s.subj, LP_SUBJ_MAX);
  w.str(s.prof, LP_PROF_MAX);
  return w.done();
}
bool decSlotBody(const uint8_t* p, uint8_t n, SlotRec& s) {
  R r(p, n);
  s.day = r.u8(1, 7);
  s.sH = r.u8(0, 23);
  s.sM = r.u8(0, 59);
  s.eH = r.u8(0, 23);
  s.eM = r.u8(0, 59);
  s.type = r.u8(1, 6);
  r.str(s.subj, LP_SUBJ_MAX);
  r.str(s.prof, LP_PROF_MAX);
  return r.done();
}
size_t encResvBody(const ResvRec& x, uint8_t* out, size_t cap) {
  W w(out, cap);
  w.u16(x.resvId);
  w.u8(x.y);
  w.u8(x.m, 1, 12);
  w.u8(x.d, 1, 31);
  hm(w, x.sH, x.sM);
  hm(w, x.eH, x.eM);
  w.u8(x.type, 1, 6);
  w.str(x.subj, LP_SUBJ_MAX);
  w.str(x.prof, LP_PROF_MAX);
  return w.done();
}
bool decResvBody(const uint8_t* p, uint8_t n, ResvRec& x) {
  R r(p, n);
  x.resvId = r.u16();
  x.y = r.u8();
  x.m = r.u8(1, 12);
  x.d = r.u8(1, 31);
  x.sH = r.u8(0, 23);
  x.sM = r.u8(0, 59);
  x.eH = r.u8(0, 23);
  x.eM = r.u8(0, 59);
  x.type = r.u8(1, 6);
  r.str(x.subj, LP_SUBJ_MAX);
  r.str(x.prof, LP_PROF_MAX);
  return r.done();
}
size_t encExamBody(const ExamRec& e, uint8_t* out, size_t cap) {
  W w(out, cap);
  w.u16(e.examId);
  w.u8(e.y1);
  w.u8(e.m1, 1, 12);
  w.u8(e.d1, 1, 31);
  w.u8(e.y2);
  w.u8(e.m2, 1, 12);
  w.u8(e.d2, 1, 31);
  return w.done();
}
bool decExamBody(const uint8_t* p, uint8_t n, ExamRec& e) {
  R r(p, n);
  e.examId = r.u16();
  e.y1 = r.u8();
  e.m1 = r.u8(1, 12);
  e.d1 = r.u8(1, 31);
  e.y2 = r.u8();
  e.m2 = r.u8(1, 12);
  e.d2 = r.u8(1, 31);
  return r.done();
}

// NEW_VER + 본문 조합 헬퍼
#define LC_ENC_VER(NAME, T, BODY)                                          \
  size_t enc##NAME(uint8_t newVer, const T& x, uint8_t* out, size_t cap) { \
    if (cap < 1) return 0;                                                 \
    out[0] = newVer;                                                       \
    size_t n = BODY(x, out + 1, cap - 1);                                  \
    return n ? n + 1 : 0;                                                  \
  }
#define LC_DEC_VER(NAME, T, BODY)                                      \
  bool dec##NAME(const uint8_t* p, uint8_t n, uint8_t& newVer, T& x) { \
    if (n < 1) return false;                                           \
    newVer = p[0];                                                     \
    return BODY(p + 1, (uint8_t)(n - 1), x);                           \
  }
LC_ENC_VER(SlotSet, SlotRec, encSlotBody)
LC_DEC_VER(SlotSet, SlotRec, decSlotBody)
LC_ENC_VER(ResvSet, ResvRec, encResvBody)
LC_DEC_VER(ResvSet, ResvRec, decResvBody)
LC_ENC_VER(ExamSet, ExamRec, encExamBody)
LC_DEC_VER(ExamSet, ExamRec, decExamBody)

// ---------- 단순 타입 ----------
size_t encTime(const Time& t, uint8_t* out, size_t cap) {
  W w(out, cap);
  w.u32(t.epoch);
  w.u8(t.flags);
  return w.done();
}
bool decTime(const uint8_t* p, uint8_t n, Time& t) {
  R r(p, n);
  t.epoch = r.u32();
  t.flags = r.u8();
  return r.done();
}

size_t encSlotDel(uint8_t nv, const SlotDel& s, uint8_t* out, size_t cap) {
  W w(out, cap);
  w.u8(nv);
  w.u8(s.day, 1, 7);
  hm(w, s.sH, s.sM);
  return w.done();
}
bool decSlotDel(const uint8_t* p, uint8_t n, uint8_t& nv, SlotDel& s) {
  R r(p, n);
  nv = r.u8();
  s.day = r.u8(1, 7);
  s.sH = r.u8(0, 23);
  s.sM = r.u8(0, 59);
  return r.done();
}

size_t encDayClear(uint8_t nv, const DayClear& d, uint8_t* out, size_t cap) {
  W w(out, cap);
  w.u8(nv);
  w.u8(d.day, 1, 7);
  return w.done();
}
bool decDayClear(const uint8_t* p, uint8_t n, uint8_t& nv, DayClear& d) {
  R r(p, n);
  nv = r.u8();
  d.day = r.u8(1, 7);
  return r.done();
}

size_t encResvDel(uint8_t nv, const ResvDel& x, uint8_t* out, size_t cap) {
  W w(out, cap);
  w.u8(nv);
  w.u16(x.resvId);
  return w.done();
}
bool decResvDel(const uint8_t* p, uint8_t n, uint8_t& nv, ResvDel& x) {
  R r(p, n);
  nv = r.u8();
  x.resvId = r.u16();
  return r.done();
}

size_t encExamDel(uint8_t nv, const ExamDel& x, uint8_t* out, size_t cap) {
  W w(out, cap);
  w.u8(nv);
  w.u16(x.examId);
  return w.done();
}
bool decExamDel(const uint8_t* p, uint8_t n, uint8_t& nv, ExamDel& x) {
  R r(p, n);
  nv = r.u8();
  x.examId = r.u16();
  return r.done();
}

size_t encFileBegin(uint8_t nv, const FileBegin& f, uint8_t* out, size_t cap) {
  W w(out, cap);
  w.u8(nv);
  w.u8(f.kind, 1, 3);
  w.u16(f.totalLen);
  w.u8(f.nChunks);
  return w.done();
}
bool decFileBegin(const uint8_t* p, uint8_t n, uint8_t& nv, FileBegin& f) {
  R r(p, n);
  nv = r.u8();
  f.kind = r.u8(1, 3);
  f.totalLen = r.u16();
  f.nChunks = r.u8();
  return r.done();
}

size_t encFileData(const FileData& f, uint8_t* out, size_t cap) {
  if (f.len > LP_FILE_CHUNK_MAX) return 0;
  W w(out, cap);
  w.u8(f.seq);
  w.raw(f.data, f.len);
  return w.done();
}
bool decFileData(const uint8_t* p, uint8_t n, FileData& f) {
  if (n < 1 || n - 1 > LP_FILE_CHUNK_MAX) return false;
  f.seq = p[0];
  f.data = p + 1;
  f.len = (uint8_t)(n - 1);
  return true;
}

size_t encFileEnd(const FileEnd& f, uint8_t* out, size_t cap) {
  W w(out, cap);
  w.u16(f.crc);
  return w.done();
}
bool decFileEnd(const uint8_t* p, uint8_t n, FileEnd& f) {
  R r(p, n);
  f.crc = r.u16();
  return r.done();
}

size_t encCmd(const CmdMsg& c, uint8_t* out, size_t cap) {
  W w(out, cap);
  w.u8(c.cmd, LP_CMD_TEST_RENDER, LP_CMD_FORCE_RENDER);
  w.raw(c.args, c.argsLen);
  return w.done();
}
bool decCmd(const uint8_t* p, uint8_t n, CmdMsg& c) {
  if (n < 1 || p[0] < LP_CMD_TEST_RENDER || p[0] > LP_CMD_FORCE_RENDER) return false;
  c.cmd = p[0];
  c.args = p + 1;
  c.argsLen = (uint8_t)(n - 1);
  return true;
}

size_t encSetRoom(uint8_t nv, const SetRoom& s, uint8_t* out, size_t cap) {
  W w(out, cap);
  w.u8(nv);
  w.raw(s.mac, 6);
  w.u8(s.bld);
  w.u16(s.room);
  w.u8(s.unit, 0, 2);
  return w.done();
}
bool decSetRoom(const uint8_t* p, uint8_t n, uint8_t& nv, SetRoom& s) {
  R r(p, n);
  nv = r.u8();
  const uint8_t* m = r.raw(6);
  if (!r.ok) return false;
  for (int k = 0; k < 6; ++k) s.mac[k] = m[k];
  s.bld = r.u8();
  s.room = r.u16();
  s.unit = r.u8(0, 2);
  return r.done();
}

static void ackW(W& w, const Ack& a) {
  w.u8(a.status, 0, 8);
  w.u8(a.detail);
  w.u16(a.battMv);
  w.u8(a.schedVer);
  w.u8(a.resvVer);
  w.u8(a.examVer);
  w.u8(a.identVer);
  w.u8(a.fw);
  w.u8(a.layout, 0, 8);
}
static void ackR(R& r, Ack& a) {
  a.status = r.u8(0, 8);
  a.detail = r.u8();
  a.battMv = r.u16();
  a.schedVer = r.u8();
  a.resvVer = r.u8();
  a.examVer = r.u8();
  a.identVer = r.u8();
  a.fw = r.u8();
  a.layout = r.u8(0, 8);
}

size_t encAck(const Ack& a, uint8_t* out, size_t cap) {
  W w(out, cap);
  ackW(w, a);
  return w.done();
}
bool decAck(const uint8_t* p, uint8_t n, Ack& a) {
  R r(p, n);
  ackR(r, a);
  return r.done();
}

size_t encStatus(const Status& s, uint8_t* out, size_t cap) {
  W w(out, cap);
  ackW(w, s.ack);
  w.u8((uint8_t)s.rssiLast);
  w.u8((uint8_t)s.snrLastX4);
  w.u8(s.flags);
  w.u16(s.uptimeH);
  return w.done();
}
bool decStatus(const uint8_t* p, uint8_t n, Status& s) {
  R r(p, n);
  ackR(r, s.ack);
  s.rssiLast = (int8_t)r.u8();
  s.snrLastX4 = (int8_t)r.u8();
  s.flags = r.u8();
  s.uptimeH = r.u16();
  return r.done();
}

size_t encHello(const Hello& h, uint8_t* out, size_t cap) {
  W w(out, cap);
  w.raw(h.mac, 6);
  w.u8(h.fw);
  w.u16(h.battMv);
  return w.done();
}
bool decHello(const uint8_t* p, uint8_t n, Hello& h) {
  R r(p, n);
  const uint8_t* m = r.raw(6);
  if (!r.ok) return false;
  for (int k = 0; k < 6; ++k) h.mac[k] = m[k];
  h.fw = r.u8();
  h.battMv = r.u16();
  return r.done();
}

bool nextRecord(const uint8_t* body, uint16_t n, uint16_t& pos, uint8_t& recType, const uint8_t*& rec,
                uint8_t& recLen) {
  if (pos >= n) return false;
  if (pos + 2 > n) {
    pos = n;
    return false;
  }
  recType = body[pos];
  recLen = body[pos + 1];
  if (pos + 2 + recLen > n) {
    pos = n;
    return false;
  }
  rec = body + pos + 2;
  pos = (uint16_t)(pos + 2 + recLen);
  return true;
}

}  // namespace lc

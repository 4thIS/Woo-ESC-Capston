#include "node_core.h"

#include <string.h>

#include "kst_time.h"

namespace nc {

bool isForMe(const Ident& me, const lc::Header& h) {
  if (h.flags & LP_FLAG_BROADCAST) return true;
  if (h.bld == LP_BLD_ALL) return true;
  if (h.bld == LP_BLD_UNPROVISIONED) return false;  // SET_ROOM 은 미설정 노드만(프로비저닝은 S9)
  return h.bld == me.bld && h.room == me.room && (h.unit == LP_UNIT_ALL || h.unit == me.unit);
}

bool gap(uint8_t oldVer, uint8_t newVer) {
  return (((int)newVer - (int)oldVer) % 255 + 255) % 255 != 1;
}

ns::Date todayOf(uint32_t epochUtc) {
  const sch::KstTime k = sch::toKst(epochUtc);
  return ns::Date{(uint8_t)(k.year - 2000), k.month, k.day};
}

namespace {

// 저장 결과 → ACK. Ok 면 버전 연속성으로 OK/GAP(§12, #74 12)
uint8_t ackOf(ns::StoreStatus st, uint8_t oldVer, uint8_t newVer) {
  switch (st) {
    case ns::StoreStatus::Ok:
      return gap(oldVer, newVer) ? LP_ACK_GAP : LP_ACK_OK;
    case ns::StoreStatus::StoreFail:
      return LP_ACK_STORE_FAIL;
    case ns::StoreStatus::BadPayload:
      return LP_ACK_BAD_PAYLOAD;
    default:
      return LP_ACK_UNSUPPORTED;
  }
}

// 프레임 하나 적용. 반환 = ACK status. o.changed·o.timeSet·o.detail 을 채운다.
uint8_t apply(ns::NodeStore& st, FileRx& f, const lc::Header& h, const uint8_t* p, uint32_t now, Outcome& o) {
  const ns::RtcState& r = st.state();
  const bool clockOk = now > kClockValidEpoch;
  const ns::Date today = todayOf(now);
  uint8_t v = 0, rc;
  switch (h.type) {
    case LP_TYPE_TIME: {
      lc::Time t{};
      if (!lc::decTime(p, h.len, t)) return LP_ACK_BAD_PAYLOAD;
      o.timeSet = true;
      o.epoch = t.epoch;
      return LP_ACK_OK;
    }
    case LP_TYPE_SLOT_SET: {
      lc::SlotRec x{};
      if (!lc::decSlotSet(p, h.len, v, x)) return LP_ACK_BAD_PAYLOAD;
      const uint8_t old = r.schedVer;
      rc = ackOf(st.applySlotSet(v, x), old, v);
      break;
    }
    case LP_TYPE_SLOT_DEL: {
      lc::SlotDel x{};
      if (!lc::decSlotDel(p, h.len, v, x)) return LP_ACK_BAD_PAYLOAD;
      const uint8_t old = r.schedVer;
      rc = ackOf(st.applySlotDel(v, x), old, v);
      break;
    }
    case LP_TYPE_DAY_CLEAR: {
      lc::DayClear x{};
      if (!lc::decDayClear(p, h.len, v, x)) return LP_ACK_BAD_PAYLOAD;
      const uint8_t old = r.schedVer;
      rc = ackOf(st.applyDayClear(v, x), old, v);
      break;
    }
    case LP_TYPE_RESV_SET: {
      lc::ResvRec x{};
      if (!lc::decResvSet(p, h.len, v, x)) return LP_ACK_BAD_PAYLOAD;
      const uint8_t old = r.resvVer;
      rc = ackOf(st.applyResvSet(v, x, today, clockOk), old, v);
      break;
    }
    case LP_TYPE_RESV_DEL: {
      lc::ResvDel x{};
      if (!lc::decResvDel(p, h.len, v, x)) return LP_ACK_BAD_PAYLOAD;
      const uint8_t old = r.resvVer;
      rc = ackOf(st.applyResvDel(v, x), old, v);
      break;
    }
    case LP_TYPE_EXAM_SET: {
      lc::ExamRec x{};
      if (!lc::decExamSet(p, h.len, v, x)) return LP_ACK_BAD_PAYLOAD;
      const uint8_t old = r.examVer;
      rc = ackOf(st.applyExamSet(v, x), old, v);
      break;
    }
    case LP_TYPE_EXAM_DEL: {
      lc::ExamDel x{};
      if (!lc::decExamDel(p, h.len, v, x)) return LP_ACK_BAD_PAYLOAD;
      const uint8_t old = r.examVer;
      rc = ackOf(st.applyExamDel(v, x), old, v);
      break;
    }
    case LP_TYPE_FILE_BEGIN: {
      lc::FileBegin b{};
      if (!lc::decFileBegin(p, h.len, f.newVer, b) || b.totalLen > kFileMax || b.nChunks > kFileChunksMax ||
          (uint32_t)b.nChunks * LP_FILE_CHUNK_MAX < b.totalLen)
        return LP_ACK_BAD_PAYLOAD;
      f.active = true;
      f.kind = b.kind;
      f.len = b.totalLen;
      f.nChunks = b.nChunks;
      memset(f.have, 0, sizeof f.have);
      return LP_ACK_OK;
    }
    case LP_TYPE_FILE_DATA: {
      lc::FileData d{};
      if (!f.active || !lc::decFileData(p, h.len, d) || d.seq >= f.nChunks) return LP_ACK_BAD_PAYLOAD;
      const uint32_t off = (uint32_t)d.seq * LP_FILE_CHUNK_MAX;
      if (off + d.len > f.len) return LP_ACK_BAD_PAYLOAD;
      memcpy(f.buf + off, d.data, d.len);
      f.have[d.seq] = true;
      return LP_ACK_OK;
    }
    case LP_TYPE_FILE_END: {
      lc::FileEnd e{};
      if (!f.active || !lc::decFileEnd(p, h.len, e)) return LP_ACK_BAD_PAYLOAD;
      for (uint8_t i = 0; i < f.nChunks; ++i)
        if (!f.have[i]) {
          o.detail = i;
          return LP_ACK_FILE_MISSING;
        }
      if (lc::crc16(f.buf, f.len) != e.crc) return LP_ACK_BAD_CRC;
      const ns::StoreStatus s = st.replaceKind(f.kind, f.newVer, f.buf, f.len, today, clockOk);
      if (s != ns::StoreStatus::Ok) return ackOf(s, 0, 0);
      f.active = false;
      o.changed = true;
      return LP_ACK_OK;  // FILE 은 전체 교체 — GAP 없음(§3.3)
    }
    default:  // CMD·SET_ROOM·SET_PARAM 은 2단계(프로비저닝)
      return LP_ACK_UNSUPPORTED;
  }
  if (rc == LP_ACK_OK || rc == LP_ACK_GAP) o.changed = true;
  return rc;
}

}  // namespace

Outcome handleFrame(ns::NodeStore& st, FileRx& f, const lc::Header& h, const uint8_t* p, uint32_t nowEpoch) {
  Outcome o;
  uint8_t s;
  if (h.type != LP_TYPE_TIME && h.txn != 0 && h.txn == st.state().lastTxn) {
    s = LP_ACK_DUP;  // 재적용 없이 ACK 만(§3.5)
  } else {
    s = apply(st, f, h, p, nowEpoch, o);
    // lastTxn 은 저장 결과가 OK(GAP 포함)일 때만(#74 10). TIME 은 건드리지 않는다(§3.5).
    // setLastTxn 실패는 무시한다 — 데이터는 이미 저장됐고, lastTxn 을 놓치면 같은 프레임이 다시 와도 멱등
    // 적용될 뿐이다.
    if (h.type != LP_TYPE_TIME && h.txn != 0 && (s == LP_ACK_OK || s == LP_ACK_GAP))
      (void)st.setLastTxn(h.txn);
  }
  const bool wantAck = (h.flags & LP_FLAG_ACK_REQ) && !(h.flags & LP_FLAG_BROADCAST) && h.bld != LP_BLD_ALL;
  o.status = wantAck ? s : kNoAck;
  return o;
}

}  // namespace nc

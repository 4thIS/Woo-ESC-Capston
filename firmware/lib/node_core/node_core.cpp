#include "node_core.h"

#include <stdio.h>
#include <string.h>

#include <algorithm>
#include <cstring>

#include "kst_time.h"
#include "schedule.h"

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
      if (t.flags & LP_TIMEFLAG_REQUEST_STATUS) {
        o.statusReq = true;
        o.statusSpreadMs = kReqStatusSpreadMs;
      }
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
    case LP_TYPE_CMD: {
      lc::CmdMsg c{};
      if (!lc::decCmd(p, h.len, c)) return LP_ACK_BAD_PAYLOAD;
      if (c.cmd != LP_CMD_REQUEST_STATUS) return LP_ACK_UNSUPPORTED;  // 나머지 CMD 는 2단계
      o.statusReq = true;
      return LP_ACK_OK;
    }
    default:  // SET_ROOM 은 2단계(프로비저닝)
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
    // setLastTxn 실패는 무시한다 — 데이터는 이미 저장됐다. lastTxn 을 놓치면 같은 프레임이 다시 왔을 때 DUP
    // 이 아니라 재적용되는데, 버전이 이미 v 라 gap(v, v) → GAP ACK → 서버 FILE 재동기가 된다. 해롭진 않지만
    // 재동기 한 번이 든다.
    if (h.type != LP_TYPE_TIME && h.txn != 0 && (s == LP_ACK_OK || s == LP_ACK_GAP))
      (void)st.setLastTxn(h.txn);
  }
  const bool wantAck = (h.flags & LP_FLAG_ACK_REQ) && !(h.flags & LP_FLAG_BROADCAST) && h.bld != LP_BLD_ALL;
  o.status = wantAck ? s : kNoAck;
  return o;
}

namespace {

struct Item {
  uint16_t s, e;  // 자정부터 분
  uint8_t type;
  bool resv;
  uint8_t idx;  // r.slots / r.resv 위치
};

void fillSlot(RenderSlot& r, const char* subj, const char* prof, uint16_t s, uint16_t e, uint8_t type) {
  memset(&r, 0, sizeof r);
  strncpy(r.subj, subj, sizeof r.subj - 1);
  strncpy(r.prof, prof, sizeof r.prof - 1);
  r.sH = (uint8_t)(s / 60), r.sM = (uint8_t)(s % 60), r.eH = (uint8_t)(e / 60), r.eM = (uint8_t)(e % 60);
  r.type = type;
  r.flags = 0x01;
}

}  // namespace

sch::LayoutDecision buildModel(const ns::RtcState& r, uint32_t epochUtc, RenderModel& m) {
  memset(&m, 0, sizeof m);
  m.bld = (char)r.bld;
  m.room = r.room;
  m.unit = r.unit;
  const sch::KstTime k = sch::toKst(epochUtc);
  char ds[12];  // month·day 는 두 자리지만 컴파일러는 u8 전체 범위로 본다
  snprintf(ds, sizeof ds, "%02u.%02u", k.month, k.day);
  memcpy(m.dateStr, ds, sizeof m.dateStr - 1);
  m.weekday = k.weekday;
  const uint16_t nowMin = sch::minuteOfDay(k);

  // RTC 슬롯이 오늘 요일 것일 때만 쓴다 — 자정 직후 어댑터가 refreshDay 하기 전엔 빈 것으로 본다
  const uint8_t nSlots = r.slotsDay == k.weekday ? r.nSlots : 0;
  const sch::ScheduleView v{r.slots, nSlots, r.resv, r.nResv, r.exams, r.nExam};
  const sch::LayoutDecision d = sch::determineLayout(v, epochUtc);
  m.layout = d.layout;

  static Item it[LP_SLOT_DAY_MAX + ns::kResvMax];
  int n = 0;
  for (uint8_t i = 0; i < nSlots; ++i)
    it[n++] = {(uint16_t)(r.slots[i].sH * 60 + r.slots[i].sM), (uint16_t)(r.slots[i].eH * 60 + r.slots[i].eM),
               r.slots[i].type, false, i};
  const ns::Date today = todayOf(epochUtc);
  for (uint8_t i = 0; i < r.nResv; ++i)
    if (r.resv[i].y == today.y && r.resv[i].m == today.m && r.resv[i].d == today.d)
      it[n++] = {(uint16_t)(r.resv[i].sH * 60 + r.resv[i].sM), (uint16_t)(r.resv[i].eH * 60 + r.resv[i].eM),
                 r.resv[i].type, true, i};
  int ord[LP_SLOT_DAY_MAX + ns::kResvMax];
  for (int i = 0; i < n; ++i) ord[i] = i;
  std::stable_sort(ord, ord + n, [&](int a, int b) { return it[a].s < it[b].s; });
  auto subjOf = [&](const Item& x) { return x.resv ? r.resv[x.idx].subj : r.slots[x.idx].subj; };
  auto profOf = [&](const Item& x) { return x.resv ? r.resv[x.idx].prof : r.slots[x.idx].prof; };

  // 오늘 목록 — 연속 교시 한 행(terminal-epaper.md 「오늘 목록」, #143). 판정은 교시 단위 그대로
  for (int j = 0; j < n; ++j) {
    const Item& x = it[ord[j]];
    if (m.nToday > 0) {
      TodaySlot& p = m.today[m.nToday - 1];
      const int pe = p.eH * 60 + p.eM;
      const int g = (int)x.s - pe;
      if (p.type == x.type && g >= 0 && g <= LP_BREAK_GAP_MAX_MIN &&
          strncmp(p.subj, subjOf(x), sizeof p.subj) == 0) {
        if ((int)x.e > pe) p.eH = (uint8_t)(x.e / 60), p.eM = (uint8_t)(x.e % 60);
        continue;
      }
    }
    if (m.nToday >= 24) break;
    TodaySlot& t = m.today[m.nToday++];
    t.sH = (uint8_t)(x.s / 60), t.sM = (uint8_t)(x.s % 60), t.eH = (uint8_t)(x.e / 60),
    t.eM = (uint8_t)(x.e % 60);
    strncpy(t.subj, subjOf(x), sizeof t.subj - 1);
    t.type = x.type;
  }

  // cur: 판정한 항목(쉬는시간이면 곧 시작할 수업 — cur = next, #89). next: 그 뒤 처음 시작하는 항목
  int curIt = -1;
  for (int i = 0; i < n; ++i) {
    const bool isResv = d.by == sch::Decider::Resv;
    const bool isSlot =
        d.by == sch::Decider::Slot || d.by == sch::Decider::ExamSlot || d.by == sch::Decider::Break;
    if ((isResv && it[i].resv && it[i].idx == d.index) || (isSlot && !it[i].resv && it[i].idx == d.index)) {
      curIt = i;
      break;
    }
  }
  if (curIt >= 0)
    fillSlot(m.cur, subjOf(it[curIt]), profOf(it[curIt]), it[curIt].s, it[curIt].e, it[curIt].type);
  if (d.layout == LP_LAYOUT_BREAK) {
    m.next = m.cur;
  } else {
    const uint16_t after = curIt >= 0 ? it[curIt].e : nowMin;
    for (int j = 0; j < n; ++j) {
      const Item& x = it[ord[j]];
      if (ord[j] != curIt && (curIt >= 0 ? x.s >= after : x.s > after)) {
        fillSlot(m.next, subjOf(x), profOf(x), x.s, x.e, x.type);
        break;
      }
    }
  }
  return d;
}

lc::Ack buildAck(const ns::RtcState& r, uint8_t status, uint8_t detail, uint16_t battMv, uint8_t fw,
                 uint8_t layout) {
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

void StatusPlan::sent(uint32_t nowMs, bool ok, bool clockOk, uint8_t flags) {
  if (ok) staleSent_ = (flags & LP_STATUSFLAG_CLOCK_STALE) != 0;
  if (!ok) {
    pending_ = true;
    onlyIfStale_ = false;
    dueMs_ = nowMs + kBusyRetryMs;
    return;
  }
  if (!clockOk) {
    pending_ = true;
    onlyIfStale_ = true;
    const uint32_t wait = staleTries_ >= 5 ? kStaleRetryMs : kStaleRetryFirstMs << staleTries_;
    dueMs_ = nowMs + (wait < kStaleRetryMs ? wait : kStaleRetryMs);
    if (staleTries_ < 5) ++staleTries_;
    return;
  }
  staleTries_ = 0;
  pending_ = false;
  onlyIfStale_ = false;
}

void StatusPlan::onTimeSet(uint32_t nowMs) {
  if (!staleSent_) return;
  staleSent_ = false;
  request(nowMs, kAfterTimeStatusMs);
}

uint32_t StatusPlan::msUntilDue(uint32_t nowMs, bool clockOk) const {
  if (!pending_ || (onlyIfStale_ && clockOk)) return UINT32_MAX;
  const int32_t left = (int32_t)(dueMs_ - nowMs);
  return left <= 0 ? 0 : (uint32_t)left;
}

namespace {
bool sameSlot(const RenderSlot& a, const RenderSlot& b) {
  return std::strcmp(a.subj, b.subj) == 0 && std::strcmp(a.prof, b.prof) == 0 && a.sH == b.sH &&
         a.sM == b.sM && a.eH == b.eH && a.eM == b.eM && a.type == b.type && a.flags == b.flags;
}
}  // namespace

bool sameScreen(const RenderModel& a, const RenderModel& b) {
  if (a.layout != b.layout || a.bld != b.bld || a.room != b.room || a.unit != b.unit ||
      a.weekday != b.weekday || a.nToday != b.nToday)
    return false;
  if (std::strncmp(a.dateStr, b.dateStr, sizeof a.dateStr) != 0) return false;
  if (std::strncmp(a.newTag, b.newTag, sizeof a.newTag) != 0) return false;
  if (!sameSlot(a.cur, b.cur) || !sameSlot(a.next, b.next)) return false;
  for (uint8_t i = 0; i < a.nToday && i < 24; ++i) {
    const TodaySlot &x = a.today[i], &y = b.today[i];
    if (x.sH != y.sH || x.sM != y.sM || x.eH != y.eH || x.eM != y.eM || x.type != y.type ||
        std::strcmp(x.subj, y.subj) != 0)
      return false;
  }
  return true;
}

uint32_t sleepMs(uint32_t nowMs, bool clockOk, uint32_t nowEpoch, uint32_t nextChangeEpoch, bool dayReady,
                 const StatusPlan& p) {
  uint32_t ms = dayReady ? kSleepCapMs : kSleepCapNoDayMs;
  if (clockOk) {
    if (nextChangeEpoch <= nowEpoch) return 0;
    const uint32_t untilChange = nextChangeEpoch - nowEpoch;
    if (untilChange < ms / 1000u) ms = untilChange * 1000u;
  }
  const uint32_t untilStatus = p.msUntilDue(nowMs, clockOk);
  if (untilStatus < ms) ms = untilStatus;
  return ms < kSleepMinMs ? 0 : ms;
}

}  // namespace nc

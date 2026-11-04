#include "node_core.h"

#include <stdio.h>
#include <string.h>

#include <algorithm>

namespace nc {

void clear(State& s) {
  memset(&s, 0, sizeof s);
}

bool isForMe(const Ident& me, const lc::Header& h) {
  if (h.flags & LP_FLAG_BROADCAST) return true;
  if (h.bld == LP_BLD_ALL) return true;
  if (h.bld == LP_BLD_UNPROVISIONED) return false;  // SET_ROOM 은 미설정 노드만(프로비저닝은 S9)
  return h.bld == me.bld && h.room == me.room && (h.unit == LP_UNIT_ALL || h.unit == me.unit);
}

bool gap(uint8_t oldVer, uint8_t newVer) {
  return (((int)newVer - (int)oldVer) % 255 + 255) % 255 != 1;
}

namespace {

uint8_t applyVer(uint8_t& cur, uint8_t newVer) {
  bool g = gap(cur, newVer);
  cur = newVer;
  return g ? LP_ACK_GAP : LP_ACK_OK;
}

template <class T, class Eq>
bool upsert(T* arr, uint8_t& n, uint8_t cap, const T& v, Eq eq) {
  for (uint8_t i = 0; i < n; ++i)
    if (eq(arr[i], v)) {
      arr[i] = v;
      return true;
    }
  if (n >= cap) return false;
  arr[n++] = v;
  return true;
}

template <class T, class Pred>
void eraseIf(T* arr, uint8_t& n, Pred pred) {
  uint8_t k = 0;
  for (uint8_t i = 0; i < n; ++i)
    if (!pred(arr[i])) arr[k++] = arr[i];
  n = k;
}

bool sameSlot(const lc::SlotRec& a, const lc::SlotRec& b) {
  return a.day == b.day && a.sH == b.sH && a.sM == b.sM;
}

// FILE_END: 레코드 스트림을 풀어 그 kind 를 통째로 바꾼다. 실패하면 State 는 그대로.
uint8_t replaceKind(State& s, const FileRx& f) {
  static State tmp;
  tmp = s;
  uint16_t pos = 0;
  uint8_t rt, rl;
  const uint8_t* r;
  static const uint8_t kRecType[] = {0, LP_TYPE_SLOT_SET, LP_TYPE_RESV_SET, LP_TYPE_EXAM_SET};
  if (f.kind < LP_FILEKIND_SCHEDULE || f.kind > LP_FILEKIND_EXAM) return LP_ACK_BAD_PAYLOAD;
  if (f.kind == LP_FILEKIND_SCHEDULE) tmp.nSlots = 0;
  if (f.kind == LP_FILEKIND_RESV) tmp.nResv = 0;
  if (f.kind == LP_FILEKIND_EXAM) tmp.nExam = 0;
  while (pos < f.len) {
    if (!lc::nextRecord(f.buf, f.len, pos, rt, r, rl) || rt != kRecType[f.kind]) return LP_ACK_BAD_PAYLOAD;
    bool ok;
    if (f.kind == LP_FILEKIND_SCHEDULE) {
      if (tmp.nSlots >= LP_SLOT_WEEK_MAX) return LP_ACK_STORE_FAIL;
      ok = lc::decSlotBody(r, rl, tmp.slots[tmp.nSlots]);
      if (ok) ++tmp.nSlots;
    } else if (f.kind == LP_FILEKIND_RESV) {
      if (tmp.nResv >= kResvMax) return LP_ACK_STORE_FAIL;
      ok = lc::decResvBody(r, rl, tmp.resv[tmp.nResv]);
      if (ok) ++tmp.nResv;
    } else {
      if (tmp.nExam >= kExamMax) return LP_ACK_STORE_FAIL;
      ok = lc::decExamBody(r, rl, tmp.exams[tmp.nExam]);
      if (ok) ++tmp.nExam;
    }
    if (!ok) return LP_ACK_BAD_PAYLOAD;  // CRC 는 맞는데 레코드가 안 풀림(#74 11)
  }
  if (f.kind == LP_FILEKIND_SCHEDULE) tmp.schedVer = f.newVer;
  if (f.kind == LP_FILEKIND_RESV) tmp.resvVer = f.newVer;
  if (f.kind == LP_FILEKIND_EXAM) tmp.examVer = f.newVer;
  s = tmp;
  return LP_ACK_OK;  // FILE 은 전체 교체 — GAP 없음(§3.3)
}

// 프레임 하나 적용. 반환 = ACK status. o.changed·o.timeSet 을 채운다.
uint8_t apply(State& s, FileRx& f, const lc::Header& h, const uint8_t* p, Outcome& o) {
  uint8_t v;
  switch (h.type) {
    case LP_TYPE_TIME: {
      lc::Time t{};
      if (!lc::decTime(p, h.len, t)) return LP_ACK_BAD_PAYLOAD;
      o.timeSet = true;
      o.epoch = t.epoch;
      return LP_ACK_OK;
    }
    case LP_TYPE_SLOT_SET: {
      lc::SlotRec r{};
      if (!lc::decSlotSet(p, h.len, v, r)) return LP_ACK_BAD_PAYLOAD;
      if (!upsert(s.slots, s.nSlots, (uint8_t)LP_SLOT_WEEK_MAX, r, sameSlot)) return LP_ACK_STORE_FAIL;
      o.changed = true;
      return applyVer(s.schedVer, v);
    }
    case LP_TYPE_SLOT_DEL: {
      lc::SlotDel d{};
      if (!lc::decSlotDel(p, h.len, v, d)) return LP_ACK_BAD_PAYLOAD;
      eraseIf(s.slots, s.nSlots,
              [&](const lc::SlotRec& a) { return a.day == d.day && a.sH == d.sH && a.sM == d.sM; });
      o.changed = true;
      return applyVer(s.schedVer, v);
    }
    case LP_TYPE_DAY_CLEAR: {
      lc::DayClear d{};
      if (!lc::decDayClear(p, h.len, v, d)) return LP_ACK_BAD_PAYLOAD;
      eraseIf(s.slots, s.nSlots, [&](const lc::SlotRec& a) { return a.day == d.day; });
      o.changed = true;
      return applyVer(s.schedVer, v);
    }
    case LP_TYPE_RESV_SET: {
      lc::ResvRec r{};
      if (!lc::decResvSet(p, h.len, v, r)) return LP_ACK_BAD_PAYLOAD;
      if (!upsert(s.resv, s.nResv, kResvMax, r,
                  [](const lc::ResvRec& a, const lc::ResvRec& b) { return a.resvId == b.resvId; }))
        return LP_ACK_STORE_FAIL;
      o.changed = true;
      return applyVer(s.resvVer, v);
    }
    case LP_TYPE_RESV_DEL: {
      lc::ResvDel d{};
      if (!lc::decResvDel(p, h.len, v, d)) return LP_ACK_BAD_PAYLOAD;
      eraseIf(s.resv, s.nResv, [&](const lc::ResvRec& a) { return a.resvId == d.resvId; });
      o.changed = true;
      return applyVer(s.resvVer, v);
    }
    case LP_TYPE_EXAM_SET: {
      lc::ExamRec r{};
      if (!lc::decExamSet(p, h.len, v, r)) return LP_ACK_BAD_PAYLOAD;
      if (!upsert(s.exams, s.nExam, kExamMax, r,
                  [](const lc::ExamRec& a, const lc::ExamRec& b) { return a.examId == b.examId; }))
        return LP_ACK_STORE_FAIL;
      o.changed = true;
      return applyVer(s.examVer, v);
    }
    case LP_TYPE_EXAM_DEL: {
      lc::ExamDel d{};
      if (!lc::decExamDel(p, h.len, v, d)) return LP_ACK_BAD_PAYLOAD;
      eraseIf(s.exams, s.nExam, [&](const lc::ExamRec& a) { return a.examId == d.examId; });
      o.changed = true;
      return applyVer(s.examVer, v);
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
      uint32_t off = (uint32_t)d.seq * LP_FILE_CHUNK_MAX;
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
      uint8_t st = replaceKind(s, f);
      if (st == LP_ACK_OK) {
        f.active = false;
        o.changed = true;
      }
      return st;
    }
    default:  // CMD·SET_ROOM·SET_PARAM 은 S9(프로비저닝) 에서
      return LP_ACK_UNSUPPORTED;
  }
}

}  // namespace

Outcome handleFrame(State& s, FileRx& f, const lc::Header& h, const uint8_t* p) {
  Outcome o;
  uint8_t st;
  if (h.type != LP_TYPE_TIME && h.txn != 0 && h.txn == s.lastTxn) {
    st = LP_ACK_DUP;  // 재적용 없이 ACK 만(§3.5)
  } else {
    st = apply(s, f, h, p, o);
    // lastTxn 은 저장 결과가 OK(GAP 포함)일 때만(#74 10). TIME 은 건드리지 않는다(§3.5)
    if (h.type != LP_TYPE_TIME && h.txn != 0 && (st == LP_ACK_OK || st == LP_ACK_GAP)) s.lastTxn = h.txn;
  }
  bool wantAck = (h.flags & LP_FLAG_ACK_REQ) && !(h.flags & LP_FLAG_BROADCAST) && h.bld != LP_BLD_ALL;
  o.status = wantAck ? st : kNoAck;
  return o;
}

// ---------------- 상태 판단 ----------------
namespace {

uint8_t typeToLayout(uint8_t t) {
  switch (t) {
    case LP_SLOTTYPE_CLASS:
      return LP_LAYOUT_CLASS;
    case LP_SLOTTYPE_EXAM:
      return LP_LAYOUT_EXAM;
    case LP_SLOTTYPE_CANCELLED:
      return LP_LAYOUT_CANCELLED;
    case LP_SLOTTYPE_SPECIAL:
      return LP_LAYOUT_SPECIAL;
    case LP_SLOTTYPE_RENTAL:
      return LP_LAYOUT_RENTAL;
    default:
      return LP_LAYOUT_EMPTY;
  }
}

// 판정과 '상태를 정한 것'(비교용 키). kind: 0 빈강의실, 1 예약, 2 슬롯, 3 쉬는시간(키 = 틈 시작 분)
struct St {
  uint8_t layout;
  uint8_t kind;
  int key;  // items 안 위치 또는 틈 시작 분
  int8_t src;
};

St stateAt(const Item* it, int n, bool inExam, int t) {
  for (int i = 0; i < n; ++i)  // 1. 예약
    if (it[i].resv && it[i].s <= t && t < it[i].e) return {typeToLayout(it[i].type), 1, i, (int8_t)i};
  for (int i = 0; i < n; ++i)  // 2·3. 슬롯 안(시험기간이면 시험중)
    if (!it[i].resv && it[i].s <= t && t < it[i].e)
      return {inExam ? (uint8_t)LP_LAYOUT_EXAM : typeToLayout(it[i].type), 2, i, (int8_t)i};
  // 3. 같은 날 수업 슬롯 사이 0 < 틈 ≤ 15분 → 쉬는시간. 슬롯을 시작 순으로 본다
  int ord[LP_SLOT_WEEK_MAX + kResvMax];
  int m = 0;
  for (int i = 0; i < n && m < (int)(sizeof ord / sizeof ord[0]); ++i)
    if (!it[i].resv) ord[m++] = i;
  std::stable_sort(ord, ord + m, [&](int a, int b) { return it[a].s < it[b].s; });
  for (int k = 0; k + 1 < m; ++k) {
    const Item& a = it[ord[k]];
    const Item& b = it[ord[k + 1]];
    int g = (int)b.s - (int)a.e;
    if (a.type == LP_SLOTTYPE_CLASS && b.type == LP_SLOTTYPE_CLASS && g > 0 && g <= LP_BREAK_GAP_MAX_MIN &&
        a.e <= t && t < b.s)
      return {LP_LAYOUT_BREAK, 3, (int)a.e, (int8_t)ord[k + 1]};
  }
  return {LP_LAYOUT_EMPTY, 0, -1, -1};
}

bool sameSt(const St& a, const St& b) {
  return a.layout == b.layout && a.kind == b.kind && a.key == b.key;
}

}  // namespace

Decision decide(const Item* it, int n, bool inExam, uint16_t at) {
  St now = stateAt(it, n, inExam, at);
  int until = -1;
  // 상태가 바뀔 수 있는 곳은 항목의 시작·끝뿐 — at 이후 경계를 오름차순으로 보며 첫 변화
  int best = 24 * 60 + 1;
  int prev = at;
  for (;;) {
    best = 24 * 60 + 1;
    for (int i = 0; i < n; ++i) {
      if (it[i].s > prev && it[i].s < best) best = it[i].s;
      if (it[i].e > prev && it[i].e < best) best = it[i].e;
    }
    if (best > 24 * 60) break;
    if (!sameSt(stateAt(it, n, inExam, best), now)) {
      until = best;
      break;
    }
    prev = best;
  }
  return Decision{now.layout, now.src, (int16_t)until};
}

Kst toKst(uint32_t epochUtc) {
  uint32_t t = epochUtc + 9u * 3600u;
  uint32_t days = t / 86400u;
  Kst k{};
  k.min = (uint16_t)((t % 86400u) / 60u);
  k.wday = (uint8_t)((days + 3) % 7 + 1);  // 1970-01-01 = 목(4) → 월=1
  // civil from days (Howard Hinnant)
  int64_t z = (int64_t)days + 719468;
  int64_t era = z / 146097;
  uint32_t doe = (uint32_t)(z - era * 146097);
  uint32_t yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
  int64_t y = (int64_t)yoe + era * 400;
  uint32_t doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
  uint32_t mp = (5 * doy + 2) / 153;
  uint32_t d = doy - (153 * mp + 2) / 5 + 1;
  uint32_t mo = mp < 10 ? mp + 3 : mp - 9;
  if (mo <= 2) ++y;
  k.y2k = (uint8_t)(y - 2000);
  k.mon = (uint8_t)mo;
  k.mday = (uint8_t)d;
  return k;
}

namespace {

void fillSlot(RenderSlot& r, const char* subj, const char* prof, uint16_t s, uint16_t e, uint8_t type) {
  memset(&r, 0, sizeof r);
  strncpy(r.subj, subj, sizeof r.subj - 1);
  strncpy(r.prof, prof, sizeof r.prof - 1);
  r.sH = (uint8_t)(s / 60), r.sM = (uint8_t)(s % 60), r.eH = (uint8_t)(e / 60), r.eM = (uint8_t)(e % 60);
  r.type = type;
  r.flags = 0x01;
}

}  // namespace

Decision buildModel(const Ident& me, const State& s, uint32_t epochUtc, RenderModel& m) {
  memset(&m, 0, sizeof m);
  m.bld = (char)me.bld;
  m.room = me.room;
  m.unit = me.unit;
  m.layout = LP_LAYOUT_EMPTY;
  Kst k = toKst(epochUtc);
  char ds[12];  // mon·mday 는 두 자리지만 컴파일러는 u8 전체 범위로 본다
  snprintf(ds, sizeof ds, "%02u.%02u", k.mon, k.mday);
  memcpy(m.dateStr, ds, sizeof m.dateStr - 1);
  m.weekday = k.wday;

  static Item it[LP_SLOT_WEEK_MAX + kResvMax];
  int n = 0;
  for (uint8_t i = 0; i < s.nSlots; ++i)
    if (s.slots[i].day == k.wday)
      it[n++] = {(uint16_t)(s.slots[i].sH * 60 + s.slots[i].sM),
                 (uint16_t)(s.slots[i].eH * 60 + s.slots[i].eM), s.slots[i].type, false, i};
  for (uint8_t i = 0; i < s.nResv; ++i)
    if (s.resv[i].y == k.y2k && s.resv[i].m == k.mon && s.resv[i].d == k.mday)
      it[n++] = {(uint16_t)(s.resv[i].sH * 60 + s.resv[i].sM), (uint16_t)(s.resv[i].eH * 60 + s.resv[i].eM),
                 s.resv[i].type, true, i};
  int key = k.y2k * 10000 + k.mon * 100 + k.mday;
  bool inExam = false;
  for (uint8_t i = 0; i < s.nExam; ++i) {
    int a = s.exams[i].y1 * 10000 + s.exams[i].m1 * 100 + s.exams[i].d1;
    int b = s.exams[i].y2 * 10000 + s.exams[i].m2 * 100 + s.exams[i].d2;
    inExam = inExam || (a <= key && key <= b);
  }

  Decision d = decide(it, n, inExam, k.min);
  m.layout = d.layout;

  // 오늘 목록 — 시작 순, 앞 24개(RenderModel 동결 #27)
  int ord[LP_SLOT_WEEK_MAX + kResvMax];
  for (int i = 0; i < n; ++i) ord[i] = i;
  std::stable_sort(ord, ord + n, [&](int a, int b) { return it[a].s < it[b].s; });
  auto subjOf = [&](const Item& x) { return x.resv ? s.resv[x.idx].subj : s.slots[x.idx].subj; };
  auto profOf = [&](const Item& x) { return x.resv ? s.resv[x.idx].prof : s.slots[x.idx].prof; };
  for (int j = 0; j < n && m.nToday < 24; ++j) {
    const Item& x = it[ord[j]];
    TodaySlot& t = m.today[m.nToday++];
    t.sH = (uint8_t)(x.s / 60), t.sM = (uint8_t)(x.s % 60), t.eH = (uint8_t)(x.e / 60),
    t.eM = (uint8_t)(x.e % 60);
    strncpy(t.subj, subjOf(x), sizeof t.subj - 1);
    t.type = x.type;
  }

  // cur: 상태를 정한 항목(쉬는시간이면 곧 시작할 수업 — cur = next, #89). next: 그 뒤 처음 시작하는 항목
  if (d.src >= 0) {
    const Item& c = it[d.src];
    fillSlot(m.cur, subjOf(c), profOf(c), c.s, c.e, c.type);
  }
  if (d.layout == LP_LAYOUT_BREAK) {
    m.next = m.cur;
  } else {
    bool hasCur = d.src >= 0;
    uint16_t after = hasCur ? it[d.src].e : k.min;
    for (int j = 0; j < n; ++j) {
      const Item& x = it[ord[j]];
      if (ord[j] != d.src && (hasCur ? x.s >= after : x.s > after)) {
        fillSlot(m.next, subjOf(x), profOf(x), x.s, x.e, x.type);
        break;
      }
    }
  }
  return d;
}

}  // namespace nc

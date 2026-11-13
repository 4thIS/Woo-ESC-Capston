#include "record_file.h"

namespace ns {

namespace {

// 레코드 스트림을 순회하며 kind 의 타입만 받아 디코드한다. accept(rec) 가 false 면 OverCapacity.
// max 는 out 의 용량 — 넘는 레코드는 out 에 쓰지 않는다.
template <typename Rec, typename Dec, typename Accept>
ParseResult parseImpl(const uint8_t* body, uint16_t n, Rec* out, uint8_t& count, uint8_t recType, uint8_t max,
                      Dec dec, Accept accept) {
  count = 0;
  uint16_t pos = 0, before = 0;
  uint8_t t = 0, len = 0;
  const uint8_t* rec = nullptr;
  while (before = pos, lc::nextRecord(body, n, pos, t, rec, len)) {
    if (t != recType) return ParseResult::Corrupt;
    Rec r{};
    if (!dec(rec, len, r)) return ParseResult::Corrupt;
    if (count >= max || !accept(r)) return ParseResult::OverCapacity;
    out[count++] = r;
  }
  // nextRecord: 정상 종료면 pos >= n 에서 false(before == n), 형식 오류면 pos < n 에서 false(before != n)
  if (before != n) return ParseResult::Corrupt;
  return ParseResult::Ok;
}

// 레코드마다 [type][len][본문] 을 쓴다. 실패(cap 부족·인코드 실패)는 0.
template <typename Rec, typename Enc>
size_t writeImpl(const Rec* in, uint8_t count, uint8_t* out, size_t cap, uint8_t recType, Enc enc) {
  size_t pos = 0;
  for (uint8_t i = 0; i < count; ++i) {
    if (cap - pos < 2) return 0;
    const size_t bl = enc(in[i], out + pos + 2, cap - pos - 2);
    if (bl == 0 || bl > 0xFF) return 0;
    out[pos] = recType;
    out[pos + 1] = static_cast<uint8_t>(bl);
    pos += 2 + bl;
  }
  return pos;
}

}  // namespace

ParseResult parseSlots(const uint8_t* body, uint16_t n, lc::SlotRec* out, uint8_t& count) {
  uint8_t perDay[8] = {};  // 인덱스 = 요일 1..7
  return parseImpl(body, n, out, count, LP_TYPE_SLOT_SET, LP_SLOT_WEEK_MAX, lc::decSlotBody,
                   [&perDay](const lc::SlotRec& r) {
                     if (r.day < 1 || r.day > 7) return false;
                     return ++perDay[r.day] <= LP_SLOT_DAY_MAX;
                   });
}

ParseResult parseResv(const uint8_t* body, uint16_t n, lc::ResvRec* out, uint8_t& count) {
  return parseImpl(body, n, out, count, LP_TYPE_RESV_SET, kResvMax, lc::decResvBody,
                   [](const lc::ResvRec&) { return true; });
}

ParseResult parseExams(const uint8_t* body, uint16_t n, lc::ExamRec* out, uint8_t& count) {
  return parseImpl(body, n, out, count, LP_TYPE_EXAM_SET, kExamMax, lc::decExamBody,
                   [](const lc::ExamRec&) { return true; });
}

size_t writeSlots(const lc::SlotRec* in, uint8_t count, uint8_t* out, size_t cap) {
  if (count > LP_SLOT_WEEK_MAX) return 0;
  return writeImpl(in, count, out, cap, LP_TYPE_SLOT_SET, lc::encSlotBody);
}

size_t writeResv(const lc::ResvRec* in, uint8_t count, uint8_t* out, size_t cap) {
  if (count > kResvMax) return 0;
  return writeImpl(in, count, out, cap, LP_TYPE_RESV_SET, lc::encResvBody);
}

size_t writeExams(const lc::ExamRec* in, uint8_t count, uint8_t* out, size_t cap) {
  if (count > kExamMax) return 0;
  return writeImpl(in, count, out, cap, LP_TYPE_EXAM_SET, lc::encExamBody);
}

uint8_t slotsOfDay(const lc::SlotRec* week, uint8_t n, uint8_t weekday, lc::SlotRec* out) {
  uint8_t m = 0;
  for (uint8_t i = 0; i < n && m < LP_SLOT_DAY_MAX; ++i) {
    if (week[i].day != weekday) continue;
    // 시작 시각(시, 분) 오름차순 삽입 — 같은 시각이면 먼저 들어온 쪽이 앞(안정)
    uint8_t j = m++;
    while (j > 0 &&
           (out[j - 1].sH > week[i].sH || (out[j - 1].sH == week[i].sH && out[j - 1].sM > week[i].sM))) {
      out[j] = out[j - 1];
      --j;
    }
    out[j] = week[i];
  }
  return m;
}

}  // namespace ns

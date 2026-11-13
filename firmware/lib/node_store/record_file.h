// 레코드 파일(/schedule.bin 등) <-> 표 변환과 요일 추출. 표준 C++ 만 쓴다 — Arduino/ESP 헤더 금지.
// 파일 형식은 FILE 본문과 같은 레코드 스트림이다: [TYPE:1][LEN:1][본문:LEN] 의 반복 (lora_codec nextRecord).
#pragma once

#include <cstddef>
#include <cstdint>

#include "lora_codec.h"

namespace ns {

constexpr uint8_t kResvMax = 24;  // v2 §5.1
constexpr uint8_t kExamMax = 8;   // v2 §5.1
// 본문 최대 — 코덱 직렬화(문자열은 [길이:1][바이트] 접두) 기준. 과목명·교수 상한이 바뀌면 자동으로 따라간다.
// 슬롯 6(day·시작 HM·끝 HM·type) + 1+LP_SUBJ_MAX + 1+LP_PROF_MAX = 52 B
// 예약 10(resvId 2·y·m·d·시작 HM·끝 HM·type) + 1+LP_SUBJ_MAX + 1+LP_PROF_MAX = 56 B
// 시험 8(examId 2 + 날짜 6) B
constexpr size_t kSlotBodyMax = 6 + 1 + LP_SUBJ_MAX + 1 + LP_PROF_MAX;
constexpr size_t kResvBodyMax = 10 + 1 + LP_SUBJ_MAX + 1 + LP_PROF_MAX;
constexpr size_t kExamBodyMax = 8;
// 레코드 최대 = 2(헤더) + 본문 최대
constexpr size_t kSchedFileMax = LP_SLOT_WEEK_MAX * (2 + kSlotBodyMax);  // 5,184 B
constexpr size_t kResvFileMax = kResvMax * (2 + kResvBodyMax);           // 1,392 B
constexpr size_t kExamFileMax = kExamMax * (2 + kExamBodyMax);           //    80 B

enum class ParseResult : uint8_t { Ok, Corrupt, OverCapacity };

// out 은 상한 개(슬롯 LP_SLOT_WEEK_MAX, 예약 kResvMax, 시험 kExamMax) 이상이면 된다 —
// 상한을 넘는 레코드는 out 에 쓰기 전에 OverCapacity 로 끝낸다.
// 슬롯: 주간 상한 LP_SLOT_WEEK_MAX, 한 요일 상한 LP_SLOT_DAY_MAX — 둘 중 하나라도 넘으면 OverCapacity.
// Corrupt = 레코드 형식 오류·타입 불일치·본문 디코드 실패. n = 0 은 Ok, count 0.
// Ok 가 아니면 out·count 내용은 믿지 말 것.
ParseResult parseSlots(const uint8_t* body, uint16_t n, lc::SlotRec* out, uint8_t& count);
ParseResult parseResv(const uint8_t* body, uint16_t n, lc::ResvRec* out, uint8_t& count);
ParseResult parseExams(const uint8_t* body, uint16_t n, lc::ExamRec* out, uint8_t& count);

// 반환 = 쓴 바이트 수. cap 부족·인코드 실패·상한 초과 count 면 0 (count 0 도 0 B).
size_t writeSlots(const lc::SlotRec* in, uint8_t count, uint8_t* out, size_t cap);
size_t writeResv(const lc::ResvRec* in, uint8_t count, uint8_t* out, size_t cap);
size_t writeExams(const lc::ExamRec* in, uint8_t count, uint8_t* out, size_t cap);

// 주간 표에서 weekday(1=월..7=일) 슬롯만 시작 시각 순으로 out 에. 반환 = 개수(≤ LP_SLOT_DAY_MAX)
uint8_t slotsOfDay(const lc::SlotRec* week, uint8_t n, uint8_t weekday, lc::SlotRec* out);

}  // namespace ns

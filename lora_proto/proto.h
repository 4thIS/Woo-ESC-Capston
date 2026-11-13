#ifndef LORA_PROTO_PROTO_H
#define LORA_PROTO_PROTO_H
// v2 스펙 §3 상수 원본. Python 미러는 lora_proto/proto.py — tools/check_mirror.py 가 일치를 검사한다.
// 이름 규칙: LP_<GROUP>_<NAME>. check_mirror 는 <GROUP> 을 proto.py 의 enum 클래스에 매핑한다.

#define LP_PROTO_VER      2
#define LP_FLAG_ACK_REQ   0x01
#define LP_FLAG_BROADCAST 0x02
#define LP_FLAG_WAKE_SENT 0x04
#define LP_HEADER_LEN     9
#define LP_MAX_FRAME      255
#define LP_MAX_PAYLOAD    245
#define LP_FILE_CHUNK_MAX 200
#define LP_BLD_UNPROVISIONED 0x00
#define LP_BLD_ALL        0xFF
#define LP_ROOM_ALL       0xFFFF
#define LP_UNIT_ALL       0
// 과목명 UTF-8 상한 — 분반을 과목명 뒤에 붙인다(「웹프로그래밍실습 102」, 2026-11-12 팀장 결정). 실제 최장 31 B
#define LP_SUBJ_MAX       32
#define LP_PROF_MAX       12
// v2 §5.3 쉬는시간: 같은 날 수업 슬롯 사이 틈이 0 < 틈 <= 이 값(분)이면 쉬는시간 (#74). 판정 벡터는 room_state_vectors.json
#define LP_BREAK_GAP_MAX_MIN 15
// v2 §5.1 노드 저장 상한 (#74, 2026-10-14): 방당 주간 정규 슬롯(LittleFS)·하루(RTC 캐시 = RenderModel today[24]).
// 넘으면 STORE_FAIL. 서버 CSV 검사도 같은 값으로 막는다
#define LP_SLOT_WEEK_MAX 96
#define LP_SLOT_DAY_MAX  24

enum {
  LP_TYPE_TIME = 0x01, LP_TYPE_SLOT_SET = 0x02, LP_TYPE_SLOT_DEL = 0x03, LP_TYPE_DAY_CLEAR = 0x04,
  LP_TYPE_RESV_SET = 0x05, LP_TYPE_RESV_DEL = 0x06, LP_TYPE_EXAM_SET = 0x07, LP_TYPE_EXAM_DEL = 0x08,
  LP_TYPE_FILE_BEGIN = 0x09, LP_TYPE_FILE_DATA = 0x0A, LP_TYPE_FILE_END = 0x0B, LP_TYPE_CMD = 0x0C,
  LP_TYPE_SET_ROOM = 0x0D, LP_TYPE_ACK = 0x10, LP_TYPE_STATUS = 0x11, LP_TYPE_HELLO = 0x12,
};
enum {
  LP_ACK_OK = 0x00, LP_ACK_BAD_CRC = 0x01, LP_ACK_BAD_PAYLOAD = 0x02, LP_ACK_STORE_FAIL = 0x03,
  LP_ACK_GAP = 0x04, LP_ACK_FILE_MISSING = 0x05, LP_ACK_UNSUPPORTED = 0x06, LP_ACK_BUSY = 0x07, LP_ACK_DUP = 0x08,
};
enum {
  LP_CMD_TEST_RENDER = 0x01, LP_CMD_REBOOT = 0x02, LP_CMD_SET_PARAM = 0x03,
  LP_CMD_REQUEST_STATUS = 0x04, LP_CMD_FACTORY_RESET = 0x05, LP_CMD_FORCE_RENDER = 0x06,
};
enum { LP_SLOTTYPE_CLASS = 1, LP_SLOTTYPE_EXAM = 2, LP_SLOTTYPE_CANCELLED = 3, LP_SLOTTYPE_EMPTY = 4, LP_SLOTTYPE_SPECIAL = 5, LP_SLOTTYPE_RENTAL = 6 };
enum { LP_FILEKIND_SCHEDULE = 1, LP_FILEKIND_RESV = 2, LP_FILEKIND_EXAM = 3 };
enum { LP_LAYOUT_CLASS = 1, LP_LAYOUT_BREAK = 2, LP_LAYOUT_CANCELLED = 3, LP_LAYOUT_EMPTY = 4, LP_LAYOUT_EXAM = 5, LP_LAYOUT_SPECIAL = 6, LP_LAYOUT_RENTAL = 7, LP_LAYOUT_SETUP = 8 };
enum { LP_STATUSFLAG_CLOCK_STALE = 0x01, LP_STATUSFLAG_UNPROVISIONED = 0x02, LP_STATUSFLAG_LOW_BATT = 0x04 };
enum { LP_TIMEFLAG_REQUEST_STATUS = 0x01 };
#endif

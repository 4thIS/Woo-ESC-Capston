"""문장 틀 — intent 마다 학습(train)·검증(val) 틀을 따로 둔다. 검증 틀은 학습에 쓰지 않는다.

자리표시: {s_X} = set 칸, {t_X} = target 칸, {x_X} = 문장에만 넣고 양식에는 넣지 않음.
X: rooms(강의실 1~3개) group(층·범위) when(날짜·목록) range(기간) days(요일) time(시각 구간)
   start(시작만 "16시로") type(유형 낱말) subject professor reason requester
"""

from __future__ import annotations

import re
from dataclasses import dataclass

PLACEHOLDER = re.compile(r"\{([stx])_(\w+)\}")
FIELD_OF = {
    "rooms": "rooms",
    "group": "rooms",
    "when": "when",
    "range": "when",
    "days": "when",
    "time": "time",
    "start": "time",
    "type": "type",
    "subject": "subject",
    "professor": "professor",
    "reason": "reason",
    "requester": "requester",
}


@dataclass(frozen=True)
class Tpl:
    id: str
    split: str  # train | val
    intent: str
    text: str
    type_label: str | None = None  # 문장에 유형 낱말이 고정으로 들어 있을 때(예: "휴강")


T = Tpl
TEMPLATES: tuple[Tpl, ...] = (
    # A. 날짜별 일정
    T("event.add/01", "train", "event.add", "{s_rooms} {s_when} {s_time} {s_type} 예약해줘"),
    T(
        "event.add/02",
        "train",
        "event.add",
        "{s_when} {s_time}에 {s_rooms}에서 {s_subject} {s_type} 잡아줘",
    ),
    T("event.add/03", "train", "event.add", "{s_rooms} {s_when} {s_subject} 휴강 처리해줘", "휴강"),
    T(
        "event.add/04",
        "train",
        "event.add",
        "{s_when} {s_rooms} {s_time} {s_subject} 보강 넣어줘",
        "수업",
    ),
    T(
        "event.add/05",
        "train",
        "event.add",
        "{s_subject} {s_type} {s_when} {s_time} {s_rooms}에 등록해줘",
    ),
    T(
        "event.add/06",
        "train",
        "event.add",
        "{s_rooms}에 {s_when} {s_time} {s_type} 하나 추가. 담당은 {s_professor}",
    ),
    T("event.add/07", "train", "event.add", "{s_group} {s_when} 휴강", "휴강"),
    T(
        "event.add/v1",
        "val",
        "event.add",
        "{s_rooms} {s_when} {s_time}에 {s_type} 일정 넣어 주실래요",
    ),
    T(
        "event.add/v2",
        "val",
        "event.add",
        "{s_when}에 {s_subject} {s_type} 있어서 {s_rooms} {s_time} 잡아 주세요",
    ),
    T(
        "event.change/01",
        "train",
        "event.change",
        "{t_rooms} {t_when} {t_subject} {s_start} 바꿔줘",
    ),
    T(
        "event.change/02",
        "train",
        "event.change",
        "{t_rooms} {t_when} {t_time} 일정 {s_when}로 옮겨줘",
    ),
    T(
        "event.change/03",
        "train",
        "event.change",
        "{t_when} {t_rooms} {t_subject} 이름 {s_subject}로 변경",
    ),
    T(
        "event.change/04",
        "train",
        "event.change",
        "{t_rooms} {t_when} {t_subject} 시간을 {s_time}로 수정",
    ),
    T(
        "event.change/v1",
        "val",
        "event.change",
        "{t_rooms} {t_when} {t_time}에 잡힌 거 {s_start} 해 주세요",
    ),
    T("event.change/v2", "val", "event.change", "{t_when} {t_subject} 장소를 {s_rooms}로 바꿔"),
    T("event.remove/01", "train", "event.remove", "{t_rooms} {t_when} {t_subject} 취소해줘"),
    T("event.remove/02", "train", "event.remove", "{t_when} {t_time} {t_rooms} 일정 삭제"),
    T(
        "event.remove/03",
        "train",
        "event.remove",
        "{t_rooms} {t_when} 잡혀 있는 {t_subject} 없애줘",
    ),
    T(
        "event.remove/v1",
        "val",
        "event.remove",
        "{t_rooms} {t_when}에 있는 {t_subject} 지워 주세요",
    ),
    T("event.remove/v2", "val", "event.remove", "{t_when} {t_time}에 {t_rooms} 예약된 거 빼줘"),
    # B. 시험기간
    T("exam.add/01", "train", "exam.add", "{s_rooms} {s_range} 시험기간으로 설정해줘"),
    T("exam.add/02", "train", "exam.add", "{s_range} {s_rooms} 시험 기간 등록"),
    T("exam.add/03", "train", "exam.add", "{s_group} 시험기간 {s_range}"),
    T("exam.add/v1", "val", "exam.add", "{s_range} 동안 {s_rooms} 시험기간 잡아 주세요"),
    T("exam.change/01", "train", "exam.change", "{t_rooms} 시험기간 {s_range}로 바꿔줘"),
    T("exam.change/02", "train", "exam.change", "{t_rooms} {t_range} 시험기간을 {s_range}로 변경"),
    T("exam.change/v1", "val", "exam.change", "{t_rooms} 시험 기간 {s_range}로 수정 부탁해요"),
    T("exam.remove/01", "train", "exam.remove", "{t_rooms} 시험기간 없애줘"),
    T("exam.remove/02", "train", "exam.remove", "{t_rooms} {t_range} 시험기간 삭제"),
    T("exam.remove/v1", "val", "exam.remove", "{t_rooms}에 걸린 시험 기간 지워줘"),
    # C. 정규 시간표
    T(
        "class.add/01",
        "train",
        "class.add",
        "{s_rooms} {s_days} {s_time} {s_subject} {s_professor} 교수님 수업 추가해줘",
    ),
    T(
        "class.add/02",
        "train",
        "class.add",
        "{s_days} {s_time} {s_rooms}에 {s_subject} 수업 넣어줘",
    ),
    T(
        "class.add/03",
        "train",
        "class.add",
        "정규 시간표에 {s_subject} 추가: {s_rooms} {s_days} {s_time}",
    ),
    T(
        "class.add/v1",
        "val",
        "class.add",
        "{s_rooms}에 {s_subject} 수업 {s_days} {s_time} 새로 등록해 주세요",
    ),
    T(
        "class.change/01",
        "train",
        "class.change",
        "{t_rooms} {t_days} {t_subject} 교수 {s_professor}으로 바꿔줘",
    ),
    T(
        "class.change/02",
        "train",
        "class.change",
        "{t_rooms} {t_days} {t_time} 수업 {s_start} 변경",
    ),
    T(
        "class.change/03",
        "train",
        "class.change",
        "{t_rooms} {t_days} {t_subject} 과목명 {s_subject}로 수정",
    ),
    T(
        "class.change/v1",
        "val",
        "class.change",
        "{t_days} {t_subject} 수업을 {s_rooms}로 옮겨 주세요",
    ),
    T("class.remove/01", "train", "class.remove", "{t_rooms} {t_days} {t_subject} 수업 빼줘"),
    T("class.remove/02", "train", "class.remove", "{t_days} {t_time} {t_rooms} 정규 수업 삭제"),
    T(
        "class.remove/v1",
        "val",
        "class.remove",
        "{t_rooms} 시간표에서 {t_days} {t_subject} 지워 주세요",
    ),
    # D. 학생 신청
    T("request.approve/01", "train", "request.approve", "{t_rooms} {t_when} 신청 승인해줘"),
    T("request.approve/02", "train", "request.approve", "{t_requester} 신청 승인"),
    T(
        "request.approve/03",
        "train",
        "request.approve",
        "{t_when} {t_rooms} {t_requester} 예약 신청 승인해 주세요",
    ),
    T(
        "request.approve/v1",
        "val",
        "request.approve",
        "{t_requester} 님이 낸 {t_rooms} 신청 허락해 줘",
    ),
    T(
        "request.reject/01",
        "train",
        "request.reject",
        "{t_rooms} {t_when} 신청 거절해줘. 사유는 {s_reason}",
    ),
    T("request.reject/02", "train", "request.reject", "{t_requester} 신청 반려, 사유: {s_reason}"),
    T("request.reject/03", "train", "request.reject", "{t_rooms} 신청 거절"),
    T(
        "request.reject/v1",
        "val",
        "request.reject",
        "{t_when} {t_rooms} 신청은 {s_reason} 때문에 안 돼요 거절해 주세요",
    ),
    # E. 조회
    T("ask.free_rooms/01", "train", "ask.free_rooms", "{t_when} {t_time} 빈 강의실 있어?"),
    T("ask.free_rooms/02", "train", "ask.free_rooms", "{t_when} 비어 있는 강의실 알려줘"),
    T(
        "ask.free_rooms/03",
        "train",
        "ask.free_rooms",
        "{t_when} {t_time}에 {t_group} 중 빈 곳 있어?",
    ),
    T(
        "ask.free_rooms/v1",
        "val",
        "ask.free_rooms",
        "{t_when} {t_time} 사용 가능한 강의실 찾아 주세요",
    ),
    T("ask.schedule/01", "train", "ask.schedule", "{t_rooms} {t_when} 일정 보여줘"),
    T("ask.schedule/02", "train", "ask.schedule", "{t_rooms} 시간표 알려줘"),
    T("ask.schedule/v1", "val", "ask.schedule", "{t_rooms} {t_when}에 뭐 있어요?"),
    T("ask.requests/01", "train", "ask.requests", "대기 중인 신청 보여줘"),
    T("ask.requests/02", "train", "ask.requests", "{t_rooms} 승인 대기 목록"),
    T("ask.requests/03", "train", "ask.requests", "{t_when} 들어온 신청 있어?"),
    T("ask.requests/v1", "val", "ask.requests", "아직 처리 안 한 예약 신청 뭐 있지"),
    T("ask.node/01", "train", "ask.node", "{t_rooms} 노드 상태 어때?"),
    T("ask.node/02", "train", "ask.node", "{t_rooms} 배터리 몇 퍼센트야?"),
    T("ask.node/v1", "val", "ask.node", "{t_rooms} 문 앞 화면 잘 돌아가?"),
    # 대화
    T("cancel/01", "train", "cancel", "취소"),
    T("cancel/02", "train", "cancel", "그만할래"),
    T("cancel/03", "train", "cancel", "됐어 안 할래"),
    T("cancel/04", "train", "cancel", "아니 취소해"),
    T("cancel/05", "train", "cancel", "처음부터 다시 할게"),
    T("cancel/v1", "val", "cancel", "이거 안 할게요"),
    T("cancel/v2", "val", "cancel", "그만 둘게"),
    T("unknown/01", "train", "unknown", "점심 뭐 먹지"),
    T("unknown/02", "train", "unknown", "오늘 날씨 어때"),
    T("unknown/03", "train", "unknown", "지난달 가장 많이 빈 강의실 분석해줘"),
    T("unknown/04", "train", "unknown", "{x_rooms} 강의실 새로 만들어줘"),
    T("unknown/05", "train", "unknown", "{x_rooms} 노드 재부팅해줘"),
    T("unknown/06", "train", "unknown", "{x_rooms} 노드 등록해줘"),
    T("unknown/07", "train", "unknown", "고마워"),
    T("unknown/v1", "val", "unknown", "{x_rooms} 강의실 삭제해줘"),
    T("unknown/v2", "val", "unknown", "모든 학생한테 공지 보내줘"),
)

# 되물음에 대한 답 — 빠진 칸 하나를 채운다 (intent fill)
FILL_TEMPLATES: dict[str, tuple[Tpl, ...]] = {
    "subject": (
        T("fill.subject/01", "train", "fill", "{s_subject}"),
        T("fill.subject/02", "train", "fill", "{s_subject}요"),
        T("fill.subject/03", "train", "fill", "이름은 {s_subject}"),
        T("fill.subject/v1", "val", "fill", "{s_subject}로 해 주세요"),
    ),
    "time": (
        T("fill.time/01", "train", "fill", "{s_time}"),
        T("fill.time/02", "train", "fill", "{s_time}요"),
        T("fill.time/v1", "val", "fill", "{s_time}로 할게요"),
    ),
    "when": (
        T("fill.when/01", "train", "fill", "{s_when}"),
        T("fill.when/02", "train", "fill", "{s_when}이요"),
        T("fill.when/v1", "val", "fill", "{s_when}로요"),
    ),
    "rooms": (
        T("fill.rooms/01", "train", "fill", "{s_rooms}"),
        T("fill.rooms/02", "train", "fill", "{s_rooms}에서 할게"),
        T("fill.rooms/v1", "val", "fill", "{s_rooms}로 해 주세요"),
    ),
    "type": (
        T("fill.type/01", "train", "fill", "{s_type}"),
        T("fill.type/v1", "val", "fill", "{s_type} 일정이에요"),
    ),
    "professor": (
        T("fill.professor/01", "train", "fill", "{s_professor} 교수님"),
        T("fill.professor/v1", "val", "fill", "담당은 {s_professor}"),
    ),
    "reason": (
        T("fill.reason/01", "train", "fill", "{s_reason}"),
        T("fill.reason/v1", "val", "fill", "사유는 {s_reason}입니다"),
    ),
}
# 대화 중 강의실을 더하는 답 ("아 801도 같이") — 서버가 rooms 를 더한다
MORE_TEMPLATES: tuple[Tpl, ...] = (
    T("fill.more/01", "train", "fill", "아 {s_rooms}도 같이"),
    T("fill.more/02", "train", "fill", "{s_rooms}도 추가"),
    T("fill.more/v1", "val", "fill", "{s_rooms}도 추가해 주세요"),
)

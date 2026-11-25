import rooms from '@/assets/guide/1-rooms.png'
import room from '@/assets/guide/2-room.png'
import reserve from '@/assets/guide/3-reserve.png'
import me from '@/assets/guide/4-me.png'
import door from '@/assets/guide/5-door.png'

// 이용 안내 다섯 장 (student-room.md 「학생 앱 메뉴 · 이용 안내」). 사진은 실제 학생 화면 캡처와
// 펌웨어 렌더 스냅샷(layout7_student) — 화면이 바뀌면 다시 찍는다. 문장은 사람이 건네는 말투(사용자 문장 가이드)
export interface GuideStep {
  short: string
  chapter: string
  title: string
  desc: string
  tips: [string, string]
  img: string
  alt: string
  /** 사진 틀 — 폰 화면 · 문 앞 e-Paper */
  frame: 'phone' | 'door'
}

export const GUIDE_STEPS: GuideStep[] = [
  {
    short: '강의실 고르기',
    chapter: '강의실 탭',
    title: '지금 비어 있는 곳부터',
    desc: '건물을 고르면 빈 강의실이 맨 위에 모여 있어요. 다 보고 싶을 땐 전체, 늘 가는 곳만 보고 싶을 땐 즐겨찾기로 바꾸면 됩니다.',
    tips: [
      '자주 가는 강의실은 별을 눌러 두세요. 다음부터 바로 위에 떠요.',
      '여기 보이는 상태가 문 앞 화면과 같아요.',
    ],
    img: rooms,
    alt: '강의실 목록 화면 — 지금 빈 강의실 수와 목록',
    frame: 'phone',
  },
  {
    short: '시간표 보기',
    chapter: '강의실 화면',
    title: '들어가 보면, 오늘 하루가 한눈에',
    desc: '강의실을 누르면 오늘 시간표가 나와요. 파란 줄이 지금. 며칠 뒤가 궁금하면 이번 주 전체 보기를 눌러 보세요, 일주일 중 언제 비는지 바로 보입니다.',
    tips: [
      '수업이나 시험, 다른 사람 예약이 잡힌 시간에는 신청할 수 없어요.',
      '화면 아래 갱신 시각을 보면 언제 기준인지 알 수 있어요.',
    ],
    img: room,
    alt: '강의실 화면 — 오늘 시간표와 지금 위치',
    frame: 'phone',
  },
  {
    short: '예약 신청',
    chapter: '예약 화면',
    title: '날짜, 시간, 그리고 어디에 쓸지 한 줄',
    desc: '이 강의실 예약하기를 누르면 오늘부터 7일 안에서 날짜를 고를 수 있어요. 비어 있는 시간을 하나 고르고 쓰임새를 짧게 적으면 끝. 확정은 관리자 승인 뒤에 됩니다.',
    tips: [
      '문 앞 화면에는 이름 대신 "학생 예약"이라고만 나와요.',
      '승인을 기다리는 것까지 합쳐 3건까지 걸어 둘 수 있어요.',
    ],
    img: reserve,
    alt: '예약 신청 화면 — 날짜 칩, 비어 있는 시간, 쓰임새 입력',
    frame: 'phone',
  },
  {
    short: '승인 · 체크인',
    chapter: '내 예약 탭',
    title: '승인됐다면, 시간 맞춰 체크인',
    desc: '승인되면 내 예약에 승인됨이 붙어요. 시작 시각이 되면 체크인 버튼이 켜지고요. 일찍 끝났다면 퇴실까지 눌러 주세요. 그래야 다음 사람이 그 시간을 쓸 수 있으니까요.',
    tips: ['시작 전이라면 취소할 수 있어요.', '승인 전 신청을 거두면 기록도 남지 않아요.'],
    img: me,
    alt: '내 예약 화면 — 승인됨, 체크인과 취소 버튼',
    frame: 'phone',
  },
  {
    short: '문 앞 화면',
    chapter: '강의실 문 앞',
    title: '마지막으로, 문 앞에서 한 번 더',
    desc: '승인된 예약은 강의실 문 앞 화면에 대여중으로 떠요. 오른쪽엔 그날 일정이 같이 있어서, 지나가던 학생도 언제 비는지 알 수 있죠.',
    tips: ['바뀐 내용은 몇 분 안에 화면에 반영돼요.', '이름은 어디에도 나오지 않아요.'],
    img: door,
    alt: '문 앞 e-Paper — 대여중, 학생 예약 17:00–18:30, 오른쪽에 오늘 일정',
    frame: 'door',
  },
]

/** 스와이프 — 옆으로 이만큼 밀어야 넘긴다(세로 스크롤과 헷갈리지 않게 가로가 더 커야 한다) */
export const SWIPE_PX = 50
export function swipeStep(dx: number, dy: number): -1 | 0 | 1 {
  if (Math.abs(dx) < SWIPE_PX || Math.abs(dx) <= Math.abs(dy)) return 0
  return dx < 0 ? 1 : -1
}

import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ConfirmModal from '@/admin/ConfirmModal.vue'
import {
  bldProblem,
  countFor,
  modemChangeText,
  modemOptions,
  normalizeBld,
  rangeProblem,
  rangeRooms,
  roomDeleteLines,
  roomNodeText,
  usedBlds,
} from '@/admin/masterView'
import type { BuildingOut, ModemOut, NodeOut, RoomOut } from '@/api/types'

const B = (id: number, name: string, bld: string, modem_id: string | null = null): BuildingOut => ({
  id,
  school_id: 1,
  name,
  bld,
  modem_id,
})
const R = (id: number, room: number, units = 1): RoomOut => ({
  id,
  building_id: 1,
  room,
  units,
  reservable: false,
})
const M = (modem_id: string): ModemOut => ({
  modem_id,
  agent_ver: null,
  modem_fw: null,
  last_seen_at: null,
  connected: false,
  school_id: 1,
})
const N = (room_id: number, room: number, unit: number, o: Partial<NodeOut> = {}): NodeOut => ({
  room_id,
  building_id: 1,
  building: '공학관',
  bld: 'E',
  room,
  unit,
  modem_id: 'm1',
  mac: null,
  fw: null,
  batt_mv: null,
  rssi: null,
  snr: null,
  sched_ver: null,
  resv_ver: null,
  exam_ver: null,
  ident_ver: null,
  layout: null,
  clock_stale: false,
  low_batt: false,
  uptime_h: null,
  last_seen_at: null,
  last_ack_at: null,
  last_status_at: null,
  sync_state: 'unknown',
  warnings: [],
  ...o,
})
const buildings = [B(1, '공학관', 'E', 'm1'), B(2, '사회관', 'S')]

describe('건물 글자', () => {
  it('친 글자는 대문자 한 글자로 — 영문이 아니면 비운다', () => {
    expect(normalizeBld('e')).toBe('E')
    expect(normalizeBld('ez')).toBe('E')
    expect(normalizeBld('1')).toBe('')
  })
  it('내 학교가 쓰는 글자는 저장 전에 막는다 (자기 자신은 제외)', () => {
    expect(bldProblem('', buildings, null)).toBe('영문 대문자 한 글자를 넣으세요.')
    expect(bldProblem('E', buildings, null)).toBe('이 학교가 이미 쓰는 글자입니다.')
    expect(bldProblem('E', buildings, 1)).toBeNull()
    expect(bldProblem('L', buildings, null)).toBeNull()
    expect(usedBlds(buildings)).toBe('E S')
  })
})

describe('모뎀', () => {
  it('미배정 + 학교 모뎀, 다른 건물이 쓰는 모뎀은 라벨로 알린다', () => {
    expect(modemOptions([M('m1'), M('m2')], buildings, 2)).toEqual([
      { value: '', label: '미배정' },
      { value: 'm1', label: 'm1 · 공학관 사용 중' },
      { value: 'm2', label: 'm2' },
    ])
    expect(modemOptions([M('m1')], buildings, 1)[1].label).toBe('m1')
  })
  it('바꿀 때 문장 — 대기 건수를 숫자로, 옛·새 모뎀 둘 다', () => {
    expect(modemChangeText(7, 'm1', 'm2')).toBe(
      '대기 중 7건이 m2 로 옮겨집니다. 옛 모뎀(m1)과 새 모뎀 양쪽이 설정을 다시 받습니다.',
    )
    expect(modemChangeText(null, null, 'm2')).toBe(
      '대기 중 전송이 m2 로 옮겨집니다. 새 모뎀(m2)이 설정을 받습니다.',
    )
    expect(modemChangeText(500, 'm1', null)).toBe(
      '대기 중 500건 이상이 보낼 모뎀 없이 남습니다. 옛 모뎀(m1)이 설정을 다시 받고, 이 건물 강의실은 갱신을 받지 못합니다.',
    )
  })
})

describe('강의실', () => {
  it('노드 칸 — 단말 없음 / 응답 없음(서버 unseen) / 연결됨 · 가장 낮은 배터리', () => {
    expect(roomNodeText(R(11, 401), [])).toBe('단말 없음')
    expect(roomNodeText(R(11, 401), [N(11, 401, 1, { warnings: ['unseen'] })])).toBe('단말 없음')
    const seen = new Date()
    expect(
      roomNodeText(R(12, 402, 2), [
        N(12, 402, 1, { last_seen_at: seen, batt_mv: 3980 }),
        N(12, 402, 2, { warnings: ['unseen'] }),
      ]),
    ).toBe('응답 없음')
    expect(
      roomNodeText(R(12, 402, 2), [
        N(12, 402, 1, { last_seen_at: seen, batt_mv: 3980 }),
        N(12, 402, 2, { last_seen_at: seen, batt_mv: 3620 }),
      ]),
    ).toBe('연결됨 · 3.62 V')
  })

  it('범위 — 이미 있는 호수는 표시만, 100곳 상한, 거꾸로·빈 값은 문장', () => {
    expect(rangeRooms(501, 505, [503])).toEqual([
      { room: 501, exists: false },
      { room: 502, exists: false },
      { room: 503, exists: true },
      { room: 504, exists: false },
      { room: 505, exists: false },
    ])
    expect(rangeProblem('501', '515')).toBeNull()
    expect(rangeProblem('515', '501')).toBe('끝 호수가 시작 호수보다 작습니다')
    expect(rangeProblem('1', '101')).toBe('한 번에 100곳까지 만들 수 있습니다')
    expect(rangeProblem('0', '5')).toBe('시작·끝 호수를 1~9999 로 넣으세요')
    expect(rangeProblem('5a', '9')).toBe('시작·끝 호수를 1~9999 로 넣으세요')
  })

  it('삭제 문장 — 딸린 개수(살아 있는 예약만), 단말이 붙은 유닛', () => {
    const counts = countFor(
      11,
      [{ room_id: 11 }, { room_id: 11 }, { room_id: 12 }] as never,
      [
        { room_id: 11, status: 'approved' },
        { room_id: 11, status: 'rejected' },
      ] as never,
      [],
    )
    expect(counts).toEqual({ slots: 2, resv: 1, exams: 0 })
    expect(roomDeleteLines('공학관', R(11, 401), counts, [N(11, 401, 1, { mac: 'AA' })])).toEqual([
      '공학관 401호를 지웁니다.',
      '시간표 2건 · 예약 1건이 함께 지워집니다.',
      '문 앞 단말(unit 1)은 갱신을 받지 못하게 됩니다.',
    ])
    expect(roomDeleteLines('공학관', R(11, 401), { slots: 0, resv: 0, exams: 0 }, [])).toEqual([
      '공학관 401호를 지웁니다.',
      '딸린 시간표·예약·시험기간이 없습니다.',
    ])
    expect(roomDeleteLines('공학관', R(11, 401), null, [])[1]).toBe(
      '딸린 시간표·예약 수를 불러오지 못했습니다. 있으면 함께 지워집니다.',
    )
  })
})

describe('ConfirmModal', () => {
  it('지울 대상을 그대로 적고, 확인 버튼은 danger (danger=false 면 primary)', async () => {
    const w = mount(ConfirmModal, {
      props: { open: true, title: '건물 삭제', lines: ['공학관(E) 건물을 지웁니다.'] },
      global: { stubs: { teleport: true } },
    })
    expect(w.text()).toContain('공학관(E) 건물을 지웁니다.')
    const ok = w.findAll('button').find((b) => b.text() === '삭제')!
    expect(ok.classes()).toContain('btn--danger')
    await ok.trigger('click')
    expect(w.emitted('confirm')).toHaveLength(1)
    await w.setProps({ danger: false, confirmLabel: '바꾸기' })
    expect(
      w
        .findAll('button')
        .find((b) => b.text() === '바꾸기')!
        .classes(),
    ).toContain('btn--primary')
    await w
      .findAll('button')
      .find((b) => b.text() === '취소')!
      .trigger('click')
    expect(w.emitted('close')).toHaveLength(1)
  })
})

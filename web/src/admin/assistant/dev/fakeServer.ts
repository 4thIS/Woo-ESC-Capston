// 개발 서버 전용 — 서버 API(01 계획 PR B, `/api/assistant/*`)가 나오기 전 화면을 돌리는 가짜.
// 실제 DB 의 강의실·시간표를 읽어 미리보기를 만들고, 적용은 기존 관리자 API 로 예약을 저장한다.
// 다루는 것은 날짜별 일정 추가(event.add) 하나 — 나머지 intent 는 '아직 못 함' 으로 답한다.
import { ApiError } from '@/api/client'
import { roomsApi } from '@/api/rooms'
import type {
  ApplyOut,
  BuildingOut,
  ChangeOut,
  Enqueued,
  ExamOut,
  ModelManifest,
  PreviewOut,
  ResvIn,
  ResvWithRoom,
  RoomOut,
  SlotOut,
  SlotType,
  TurnIn,
  TurnOut,
} from '@/api/types'
import { BUSY_TYPES, toMin } from '@/components/domain/rules'
import { groupSlots } from '@/components/domain/slotGroups'
import { addDays, hm, kstDateStr, md, mondayOf } from '@/lib/time'
import { STUB_MANIFEST } from '../adapters/stub'

export interface FakeDeps {
  today: string
  rooms(): Promise<RoomOut[]>
  buildings(): Promise<BuildingOut[]>
  slots(roomId: number): Promise<SlotOut[]>
  reservations(roomId: number): Promise<ResvWithRoom[]>
  exams(roomId: number): Promise<ExamOut[]>
  saveResv(roomId: number, r: ResvIn): Promise<Enqueued>
}
export const realDeps = (): FakeDeps => ({
  today: kstDateStr(new Date()),
  rooms: roomsApi.rooms,
  buildings: roomsApi.buildings,
  slots: roomsApi.slots,
  reservations: roomsApi.reservations,
  exams: roomsApi.exams,
  saveResv: roomsApi.saveResv,
})

/** '15시부터 18시까지' → 분. 1~8시는 오후로 본다(강의실 시간표의 관례) */
export function resolveTime(raw: string): { s: number; e: number } | null {
  const m =
    /(\d{1,2})\s*시(?:\s*(반|(\d{1,2})\s*분))?\s*(?:부터|~|-)\s*(\d{1,2})\s*시(?:\s*(반|(\d{1,2})\s*분))?/.exec(
      raw,
    )
  if (!m) return null
  const hour = (h: string) => (Number(h) >= 1 && Number(h) <= 8 ? Number(h) + 12 : Number(h))
  const min = (half?: string, n?: string) => (half === '반' ? 30 : n ? Number(n) : 0)
  return { s: hour(m[1]) * 60 + min(m[2], m[3]), e: hour(m[4]) * 60 + min(m[5], m[6]) }
}

const TYPE_CODE: Record<string, SlotType> = { 수업: 1, 시험: 2, 휴강: 3, 특강: 5, 대여: 6 }
const TYPE_WORD: Record<number, string> = { 1: '수업', 2: '시험', 3: '휴강', 5: '특강', 6: '대여' }
const DAYS = ['월', '화', '수', '목', '금', '토', '일']
const clock = (t: number) => hm(Math.floor(t / 60), t % 60)

interface Draft {
  rooms?: string[]
  when?: string
  time?: string
  type?: string
  subject?: string
}
interface Pending {
  roomId: number
  resv: ResvIn
}

export function createFakeAssistantApi(deps: FakeDeps = realDeps()) {
  let seq = 0
  const drafts = new Map<string, Draft>()
  const previews = new Map<string, Pending>()

  const out = (id: string, o: Partial<TurnOut>): TurnOut => ({
    conversation_id: id,
    kind: 'answer',
    message: '',
    choices: [],
    next_prefix: null,
    closed: false,
    preview: null,
    answer: null,
    ...o,
  })
  const ask = (id: string, d: Draft, question: string) =>
    out(id, {
      kind: 'ask',
      message: question,
      next_prefix: `상태: event.add | 강의실 ${d.rooms?.[0] ?? '?'} | 날짜 ${d.when ?? '?'} | 시각 ${d.time ?? '?'} | 유형 ${d.type ?? '?'} | 이름 ${d.subject ?? '?'}\n질문: ${question}\n관리자: `,
    })
  const fail = (id: string, message: string) => {
    drafts.delete(id)
    return out(id, { kind: 'error', message, closed: true })
  }

  async function evaluate(id: string, d: Draft): Promise<TurnOut> {
    const number = Number(d.rooms?.[0])
    if (!number) return ask(id, d, '어느 강의실인가요?')
    const room = (await deps.rooms()).find((r) => r.room === number)
    if (!room) return fail(id, `${number}호를 찾지 못했습니다.`)
    const dayIdx = DAYS.findIndex((c) => d.when?.includes(c))
    if (dayIdx < 0) return ask(id, d, '어느 요일인가요?')
    const time = d.time ? resolveTime(d.time) : null
    if (!time || time.e <= time.s) return ask(id, d, '몇 시부터 몇 시까지인가요?')
    const type = TYPE_CODE[d.type ?? '특강'] ?? 5
    if (!d.subject) return ask(id, d, `${TYPE_WORD[type]} 이름은 무엇인가요?`)

    const monday = addDays(mondayOf(deps.today), d.when?.includes('다음') ? 7 : 0)
    const date = addDays(monday, dayIdx)
    const [buildings, slots, resv, exams] = await Promise.all([
      deps.buildings(),
      deps.slots(room.id),
      deps.reservations(room.id),
      deps.exams(room.id),
    ])
    const label =
      `${buildings.find((b) => b.id === room.building_id)?.name ?? ''} ${room.room}`.trim()
    const input: ResvIn = {
      date,
      s_h: Math.floor(time.s / 60),
      s_m: time.s % 60,
      e_h: Math.floor(time.e / 60),
      e_m: time.e % 60,
      type,
      subject: d.subject,
      professor: '',
    }
    const added: ResvWithRoom = {
      ...input,
      id: -++seq,
      room_id: room.id,
      status: 'approved',
      requester: null,
      pushed_at: null,
      checked_in_at: null,
      checked_out_at: null,
      reject_reason: null,
    }
    const hit = (s: number, e: number) => s < time.e && time.s < e
    const warnings = [
      // 연속 교시는 묶음 하나로 — 격자와 같은 묶음(groupSlots)
      ...groupSlots(slots.map((s) => ({ ...s, room_id: room.id })))
        .filter((g) => g.day === dayIdx + 1 && BUSY_TYPES.includes(g.slots[0].type))
        .filter((g) => hit(g.start, g.end))
        .map(
          (g) =>
            `기존 ${TYPE_WORD[g.slots[0].type]} "${g.slots[0].subject}"(${clock(g.start)}–${clock(g.end)})와 겹칩니다`,
        ),
      ...resv
        .filter((r) => r.date === date && r.status === 'approved')
        .filter((r) => hit(toMin(r.s_h, r.s_m), toMin(r.e_h, r.e_m)))
        .map((r) => `기존 예약 "${r.subject}"(${hm(r.s_h, r.s_m)}–${hm(r.e_h, r.e_m)})와 겹칩니다`),
    ]
    const previewId = `p_${++seq}`
    previews.set(previewId, { roomId: room.id, resv: input })
    drafts.delete(id)
    const withRoom = {
      slots: slots.map((s) => ({ ...s, room_id: room.id })),
      exams: exams.map((e) => ({ ...e, room_id: room.id })),
    }
    const preview: PreviewOut = {
      preview_id: previewId,
      expires_at: new Date(Date.now() + 10 * 60_000),
      summary: [
        `+ ${md(date)}(${DAYS[dayIdx]}) ${clock(time.s)}–${clock(time.e)} ${TYPE_WORD[type]} "${d.subject}" (${label})`,
      ],
      blockers: date < deps.today ? ['지난 날짜에는 추가할 수 없습니다'] : [],
      warnings,
      notices: [],
      rooms: [
        {
          room_id: room.id,
          building_id: room.building_id,
          label,
          added: 1,
          removed: 0,
          changed: 0,
          weeks: [
            {
              week_start: monday,
              before: { ...withRoom, reservations: resv },
              after: { ...withRoom, reservations: [...resv, added] },
              changes: [{ entity: 'resv', key: `r${added.id}`, op: 'add', fields: [] }],
            },
          ],
        },
      ],
    }
    return out(id, { kind: 'preview', message: '바뀔 모습을 확인해 주세요.', preview })
  }

  return {
    model: async (): Promise<ModelManifest> => STUB_MANIFEST,
    async turn(t: TurnIn): Promise<TurnOut> {
      const id = t.conversation_id ?? `c_${++seq}`
      const form = (t.form ?? {}) as { intent?: string; set?: Draft }
      if (form.intent === 'cancel') {
        drafts.delete(id)
        return out(id, { kind: 'answer', message: '요청을 취소했습니다.', closed: true })
      }
      if (form.intent === 'event.add') {
        drafts.set(id, { ...form.set })
        return evaluate(id, drafts.get(id)!)
      }
      if (form.intent === 'fill' && drafts.has(id)) {
        const d = { ...drafts.get(id), ...form.set }
        drafts.set(id, d)
        return evaluate(id, d)
      }
      return fail(id, '이해하지 못했습니다. 강의실 · 요일 · 시각을 넣어 다시 말씀해 주세요.')
    },
    async apply(previewId: string): Promise<ApplyOut> {
      const p = previews.get(previewId)
      if (!p) throw new ApiError(410, '확인 화면이 만료되었습니다.', [], { detail: 'expired' })
      previews.delete(previewId)
      const enq = await deps.saveResv(p.roomId, p.resv)
      return { change_id: enq.id ?? 0, outbox_ids: enq.outbox_ids }
    },
    changes: async (): Promise<ChangeOut[]> => [],
  }
}
export type AssistantApiLike = ReturnType<typeof createFakeAssistantApi>

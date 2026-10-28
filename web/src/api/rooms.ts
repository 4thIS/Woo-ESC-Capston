import { request } from './client'
import {
  OUTBOX_DATES,
  RESV_DATES,
  type BuildingIn,
  type BuildingOut,
  type BuildingPatch,
  type Enqueued,
  type ExamIn,
  type ExamOut,
  type ExamWithRoom,
  type FailedOut,
  type ImportSummary,
  type OutboxState,
  type ResvIn,
  type ResvWithRoom,
  type RoomIn,
  type RoomOut,
  type RoomPatch,
  type SchoolOut,
  type SlotIn,
  type SlotOut,
  type SlotWithRoom,
} from './types'

/** 서버 IMPORT_MAX_BYTES — 넘으면 413. 화면이 먼저 막는다 */
export const IMPORT_MAX_BYTES = 1024 * 1024

type SlotKeyParts = { day: number; s_h: number; s_m: number }
const resv = { dates: RESV_DATES }

// 전부 관리자 + 학교 스코프 (S4a §3.2) — 다른 학교 자원은 403 이 아니라 404
export const roomsApi = {
  /** 내 학교 하나 — 생성·삭제는 CLI 전용 */
  schools: () => request<SchoolOut[]>('GET', '/api/schools'),

  buildings: () => request<BuildingOut[]>('GET', '/api/buildings'),
  createBuilding: (b: BuildingIn) => request<BuildingOut>('POST', '/api/buildings', b),
  patchBuilding: (id: number, p: BuildingPatch) =>
    request<BuildingOut>('PATCH', `/api/buildings/${id}`, p),
  /** 강의실이 남아 있으면 409 (CASCADE 없음) */
  deleteBuilding: (id: number) => request<{ ok: boolean }>('DELETE', `/api/buildings/${id}`),

  /** 필터 파라미터가 없다 — 전체를 받아 building_id 로 거른다 */
  rooms: () => request<RoomOut[]>('GET', '/api/rooms'),
  createRoom: (r: RoomIn) => request<RoomOut>('POST', '/api/rooms', r),
  patchRoom: (id: number, p: RoomPatch) => request<RoomOut>('PATCH', `/api/rooms/${id}`, p),
  /** 시간표·예약·시험기간이 CASCADE 로 함께 지워진다 */
  deleteRoom: (id: number) => request<{ ok: boolean }>('DELETE', `/api/rooms/${id}`),

  // 건물 단위 조회 (S4b §2.6) — 쓰기는 /rooms/{id}/… 그대로
  buildingSlots: (id: number) => request<SlotWithRoom[]>('GET', `/api/buildings/${id}/slots`),
  buildingResv: (id: number) =>
    request<ResvWithRoom[]>('GET', `/api/buildings/${id}/reservations`, undefined, resv),
  buildingExams: (id: number) => request<ExamWithRoom[]>('GET', `/api/buildings/${id}/exams`),
  /** 최신 순 500건 — 저장 뒤 OutboxDot 추적과 모뎀 변경 확인(대기 건수)이 쓴다 */
  buildingOutbox: (id: number, state?: OutboxState) =>
    request<FailedOut[]>(
      'GET',
      `/api/buildings/${id}/outbox?${state ? `state=${state}&` : ''}limit=500`,
      undefined,
      { dates: OUTBOX_DATES },
    ),

  slots: (roomId: number) => request<SlotOut[]>('GET', `/api/rooms/${roomId}/slots`),
  /** 키 = day+s_h+s_m. 같은 키면 수정, 아니면 추가 — 벌크가 아니다 */
  putSlot: (roomId: number, s: SlotIn) => request<Enqueued>('PUT', `/api/rooms/${roomId}/slots`, s),
  deleteSlot: (roomId: number, k: SlotKeyParts) =>
    request<Enqueued>('DELETE', `/api/rooms/${roomId}/slots/${k.day}/${k.s_h}/${k.s_m}`),

  reservations: (roomId: number) =>
    request<ResvWithRoom[]>('GET', `/api/rooms/${roomId}/reservations`, undefined, resv),
  /** id 없음 = 추가(서버 채번, 응답 id), id 있음 = 같은 방이면 수정 · 다른 방이면 409 */
  saveResv: (roomId: number, r: ResvIn) =>
    request<Enqueued>('POST', `/api/rooms/${roomId}/reservations`, r),
  deleteResv: (roomId: number, id: number) =>
    request<Enqueued>('DELETE', `/api/rooms/${roomId}/reservations/${id}`),

  exams: (roomId: number) => request<ExamOut[]>('GET', `/api/rooms/${roomId}/exams`),
  saveExam: (roomId: number, e: ExamIn) =>
    request<Enqueued>('POST', `/api/rooms/${roomId}/exams`, e),
  deleteExam: (roomId: number, id: number) =>
    request<Enqueued>('DELETE', `/api/rooms/${roomId}/exams/${id}`),

  /** 본문 = CSV 파일 바이트 그대로 (UTF-8 이 아니면 서버가 400 — 화면에서 디코딩하지 않는다) */
  importSlots: (csv: ArrayBuffer, dryRun: boolean) =>
    request<ImportSummary>('POST', `/api/import/slots?dry_run=${dryRun}`, csv, {
      contentType: 'text/csv',
    }),
}

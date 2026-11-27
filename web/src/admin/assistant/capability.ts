// 이 PC 에서 모델을 돌릴 수 있는가 (admin-assistant.md 「모델 상태」). navigator 를 받아 테스트한다
export type DeviceReason = 'no-webgpu' | 'no-adapter' | 'low-memory' | 'no-cache'
/** navigator.deviceMemory(GB, Chrome 만, 최대 8 로 뭉뚱그림) 하한 — E2B int4 약 1.5 GB + 브라우저 */
export const MIN_DEVICE_MEMORY_GB = 4
export const DEVICE_REASON: Record<DeviceReason, string> = {
  'no-webgpu':
    '이 브라우저는 WebGPU 를 지원하지 않아 AI 비서를 쓸 수 없습니다. 최신 Chrome·Edge 를 쓰세요.',
  'no-adapter': '이 PC 의 그래픽 장치로는 AI 모델을 돌릴 수 없습니다.',
  'low-memory': '이 PC 의 메모리가 부족해 AI 모델을 돌릴 수 없습니다.',
  'no-cache': '이 브라우저는 모델을 저장할 수 없습니다(사생활 보호 모드 등).',
}

export interface NavLike {
  gpu?: { requestAdapter(): Promise<unknown | null> }
  deviceMemory?: number
  storage?: {
    estimate?(): Promise<{ quota?: number; usage?: number }>
    persist?(): Promise<boolean>
  }
}
const realNav = () => navigator as unknown as NavLike

export async function checkDevice(
  nav: NavLike = realNav(),
  hasCaches: boolean = typeof caches !== 'undefined',
): Promise<{ ok: true } | { ok: false; reason: DeviceReason }> {
  if (!hasCaches) return { ok: false, reason: 'no-cache' }
  if (!nav.gpu) return { ok: false, reason: 'no-webgpu' }
  const adapter = await nav.gpu.requestAdapter().catch(() => null)
  if (!adapter) return { ok: false, reason: 'no-adapter' }
  if (typeof nav.deviceMemory === 'number' && nav.deviceMemory < MIN_DEVICE_MEMORY_GB)
    return { ok: false, reason: 'low-memory' }
  return { ok: true }
}

/** 남은 저장 공간 — 필요량의 1.1배. 브라우저가 알려 주지 않으면 막지 않는다(받다가 실패하면 그때 안내) */
export async function checkStorage(
  need: number,
  nav: NavLike = realNav(),
): Promise<{ ok: boolean; free: number | null }> {
  const est = await nav.storage?.estimate?.().catch(() => null)
  if (!est || typeof est.quota !== 'number') return { ok: true, free: null }
  const free = est.quota - (est.usage ?? 0)
  return { ok: free >= need * 1.1, free }
}

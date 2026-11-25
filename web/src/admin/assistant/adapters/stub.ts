import { ref } from 'vue'
import type { ModelManifestOn } from '@/api/types'
import type { GenerateReq, LoadProgress, ModelRunner } from '../runner'

/** localStorage 키 — 개발 서버(import.meta.env.DEV)에서만 읽는다. 운영 빌드에는 영향 없음 */
export const STUB_KEY = 'esc-assistant-stub'
/** 관리자 문장(앞뒤 공백 정리) → 모델 출력(양식 객체 또는 원문). 'manual' 이면 개발 입력칸을 그대로 낸다 */
export type StubScript = Record<string, unknown> | 'manual'
/** manual 모드의 "모델 출력" 입력칸 (AI 비서 명령창이 개발 서버에서만 그린다) */
export const manualOutput = ref('')

function safeLocal(): Pick<Storage, 'getItem'> | null {
  try {
    return localStorage
  } catch {
    return null
  }
}

export function readStubScript(
  storage: Pick<Storage, 'getItem'> | null = safeLocal(),
  dev: boolean = import.meta.env.DEV,
): StubScript | null {
  if (!dev || !storage) return null
  const raw = storage.getItem(STUB_KEY)
  if (!raw) return null
  if (raw === 'manual') return 'manual'
  try {
    const v: unknown = JSON.parse(raw)
    return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null
  } catch {
    return null
  }
}

/** 개발용 안내 — 서버 안내가 enabled:false 여도 대화 흐름을 만들 수 있게 */
export const STUB_MANIFEST: ModelManifestOn = {
  enabled: true,
  schema_v: 1,
  runtime: 'webllm',
  repo: 'dev/stub',
  revision: 'stub',
  files: [],
  system_prompt: '',
  first_prefix: '관리자: ',
  json_schema: {},
  generation: { temperature: 0, max_tokens: 256 },
}

const PREFIX = '관리자: '
const lastUtterance = (user: string) => {
  const i = user.lastIndexOf(PREFIX)
  return (i < 0 ? user : user.slice(i + PREFIX.length)).trim()
}
const UNKNOWN = JSON.stringify({ v: 1, intent: 'unknown', target: {}, set: {} })

/** 02 계획 0단계 결과 전에 화면·서버 흐름을 만드는 대역. 화면 쪽에서 돈다(Worker 없음) */
export class StubRunner implements ModelRunner {
  constructor(private script: StubScript) {}

  async load(_m: ModelManifestOn, onProgress: (p: LoadProgress) => void): Promise<void> {
    onProgress({ loaded: 1, total: 1, text: '개발용 대역' })
  }

  async generate(req: GenerateReq): Promise<string> {
    if (this.script === 'manual') return manualOutput.value
    const out = this.script[lastUtterance(req.user)]
    if (out === undefined) return UNKNOWN
    return typeof out === 'string' ? out : JSON.stringify(out)
  }

  async dispose(): Promise<void> {}
}

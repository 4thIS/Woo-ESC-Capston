// 하네스 공통 — 불러오기 시간, 문장별 응답 시간, 토큰, 규격 통과, 정답 일치를 재고 Prediction JSONL 로 내보낸다.
import Ajv from 'https://esm.sh/ajv@8'

const $ = (id) => document.getElementById(id)
const TOP = ['v', 'intent', 'target', 'set']
const FIELDS = ['rooms', 'when', 'time', 'type', 'subject', 'professor', 'reason', 'requester']
let adapter = null
let suite = null
let results = []
let loadInfo = null

// 부록 §1.3 정규 직렬화(키 순서 고정) — 정답 비교용
function canonical(f) {
  const fx = (o) => Object.fromEntries(FIELDS.filter((k) => o && o[k] !== undefined).map((k) => [k, o[k]]))
  return JSON.stringify(Object.fromEntries(TOP.map((k) => [k, k === 'target' || k === 'set' ? fx(f[k]) : f[k]])))
}

async function envInfo() {
  const gpu = navigator.gpu ? await navigator.gpu.requestAdapter() : null
  const info = gpu?.info ?? {}
  return {
    ua: navigator.userAgent,
    cores: navigator.hardwareConcurrency,
    device_memory_gb: navigator.deviceMemory ?? null,
    webgpu: !!gpu,
    gpu: [info.vendor, info.architecture, info.description].filter(Boolean).join(' / '),
    cross_origin_isolated: self.crossOriginIsolated,
  }
}

async function pickRuntime() {
  adapter = await import(`./adapters/${$('runtime').value}.js`)
  $('model').value = adapter.defaultModel ? await adapter.defaultModel() : ''
}

function download(name, text) {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([text], { type: 'application/json' }))
  a.download = name
  a.click()
}

function percentile(xs, p) {
  const s = [...xs].sort((a, b) => a - b)
  return s[Math.max(0, Math.ceil(p * s.length) - 1)]
}

function summarize() {
  const ms = results.map((r) => r.latency_ms)
  const withTok = results.filter((r) => r.tokens)
  const tps = withTok.length
    ? withTok.reduce((a, r) => a + r.tokens / (r.latency_ms / 1000), 0) / withTok.length
    : null
  return {
    ...loadInfo,
    grammar: $('grammar').checked && adapter.supportsGrammar,
    n: results.length,
    mean_ms: Math.round(ms.reduce((a, b) => a + b, 0) / ms.length),
    p90_ms: percentile(ms, 0.9),
    tokens_per_s: tps === null ? '토큰 수를 못 셈' : Number(tps.toFixed(1)),
    schema_valid: results.filter((r) => r.valid).length,
    exact: results.filter((r) => r.correct).length,
  }
}

$('env').textContent = JSON.stringify(await envInfo(), null, 1)
$('runtime').onchange = pickRuntime
await pickRuntime()

$('load').onclick = async () => {
  suite = await (await fetch($('suite').value)).json()
  const t0 = performance.now()
  try {
    await adapter.load($('model').value, (p, text) => {
      $('status').textContent = `불러오는 중 ${Math.round((p || 0) * 100)}% ${text ?? ''}`
    })
  } catch (e) {
    $('status').textContent = `불러오기 실패: ${e}`
    console.error(e)
    return
  }
  loadInfo = { runtime: $('runtime').value, model: $('model').value, load_ms: Math.round(performance.now() - t0), env: await envInfo() }
  $('status').textContent = `불러오기 ${loadInfo.load_ms} ms (같은 모델을 새로고침 뒤 다시 불러오면 = 캐시 시간)`
  $('run').disabled = false
}

$('run').onclick = async () => {
  const constraint = $('grammar').checked && adapter.supportsGrammar ? suite : null
  const validate = new Ajv({ strict: false }).compile(suite.json_schema)
  results = []
  $('rows').innerHTML = ''
  await adapter.generate(suite.system_prompt, suite.examples[0].user, constraint) // 예열 — 기록하지 않는다
  for (const ex of suite.examples) {
    const t0 = performance.now()
    const out = await adapter.generate(suite.system_prompt, ex.user, constraint)
    const latency = Math.round(performance.now() - t0)
    const text = out.text.trim()
    let parsed = null
    try { parsed = JSON.parse(text) } catch { parsed = null }
    const valid = parsed !== null && validate(parsed)
    const correct = valid && ex.gold !== undefined && canonical(parsed) === canonical(ex.gold)
    results.push({ id: ex.id, text, latency_ms: latency, tokens: out.tokens, valid, correct })
    const tr = document.createElement('tr')
    tr.className = valid ? 'ok' : 'bad'
    for (const v of [ex.id, latency, out.tokens ?? '-', valid ? '통과' : '위반', correct ? '일치' : '-']) {
      const td = document.createElement('td')
      td.textContent = String(v)
      tr.append(td)
    }
    const td = document.createElement('td')
    const pre = document.createElement('pre')
    pre.textContent = text
    td.append(pre)
    tr.append(td)
    $('rows').append(tr)
    $('status').textContent = `${results.length}/${suite.examples.length}`
  }
  $('summary').textContent = JSON.stringify(summarize(), null, 1)
  $('export').disabled = false
}

$('export').onclick = () => {
  const rt = loadInfo.runtime
  download(`preds-${rt}.jsonl`, results.map((r) => JSON.stringify({ id: r.id, text: r.text, latency_ms: r.latency_ms })).join('\n') + '\n')
  download(`run-${rt}.json`, JSON.stringify(summarize(), null, 1))
}

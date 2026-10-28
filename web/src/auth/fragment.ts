/**
 * 메일 링크의 #token= 을 읽고 즉시 주소에서 지운다 — 서버 로그·Referer·방문 기록에 남지 않게 (auth.md).
 * 지운 뒤 새로고침하면 토큰이 없으므로 화면은 "링크가 만료되었거나 잘못되었습니다" 로 간다.
 */
export function readFragmentToken(): string | null {
  const m = /^#token=([A-Za-z0-9_-]{1,128})$/.exec(location.hash) // 서버 TokenIn 상한 128
  if (location.hash) {
    // vue-router 는 다음 push 때 state.current 로 지금 항목을 다시 쓴다 — 거기서도 토큰을 지운다
    const url = location.pathname + location.search
    history.replaceState({ ...history.state, current: url }, '', url)
  }
  return m ? m[1] : null
}

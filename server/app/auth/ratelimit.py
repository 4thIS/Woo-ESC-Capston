"""email 당 분당 N 회 (S4a §3.4). 프로세스 메모리 — 단일 워커 전제(README). 재시작 시 초기화."""

from __future__ import annotations

import threading
import time

_hits: dict[str, list[float]] = {}
_now = time.monotonic
_lock = threading.Lock()  # 동기 핸들러·BackgroundTasks 가 스레드풀에서 동시에 부른다 — dict 순회 중 변경·한도 초과 통과 방지


_windows: dict[str, float] = {}  # 키마다 자기 창 — 정리가 하루 창 키를 1분 뒤 지우지 않게
_last_sweep = 0.0


def _sweep(now: float) -> None:
    """마지막 기록이 그 키의 창보다 오래된 키를 지운다 — email 별 키가 무한히 쌓이지 않게. 최대 분당 1회."""
    global _last_sweep
    if now - _last_sweep < 60.0:
        return
    _last_sweep = now
    for k in [k for k, v in _hits.items() if not v or now - v[-1] >= _windows.get(k, 60.0)]:
        del _hits[k]
        _windows.pop(k, None)


def check(key: str, limit: int = 5, window_s: float = 60.0) -> bool:
    with _lock:
        now = _now()
        _sweep(now)
        _windows[key] = window_s
        hits = [t for t in _hits.get(key, []) if now - t < window_s]
        if len(hits) >= limit:
            _hits[key] = hits
            return False
        hits.append(now)
        _hits[key] = hits
        return True


def saturated(key: str, limit: int, window_s: float) -> bool:
    """check 와 같은 판정이지만 기록하지 않는다 — 존재 여부와 무관하게 먼저 거절할 때 (PR #42 🟡)."""
    with _lock:
        now = _now()
        return sum(1 for t in _hits.get(key, ()) if now - t < window_s) >= limit


def reset() -> None:
    global _last_sweep
    with _lock:
        _hits.clear()
        _windows.clear()
        _last_sweep = 0.0

"""표현 → 값 (공통 부록 §3). 순수 함수 — DB·네트워크 없음. 못 풀면 None (추측하지 않는다).

규칙의 원본은 README 표와 vectors/resolve.v1.jsonl — 바꾸면 셋을 함께 고친다."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Literal

WEEKDAYS = "월화수목금토일"
_WEEK_WORDS = {
    "이번주": 0,
    "금주": 0,
    "다음주": 1,
    "담주": 1,
    "다다음주": 2,
    "지난주": -1,
    "저번주": -1,
}
_DAY_WORDS = {"오늘": 0, "내일": 1, "낼": 1, "모레": 2, "내일모레": 2, "낼모레": 2, "글피": 3}
_PREFIX = re.compile(r"^(다다음주|이번주|금주|다음주|담주|지난주|저번주)")
_MD = re.compile(r"^(?:(\d{4})[-./년])?(\d{1,2})(?:[-/.]|월)(\d{1,2})일?$")
_DAY = re.compile(r"^(\d{1,2})일$")
_ISO = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$")
_LIST_SEP = re.compile(r",|、|와|과|랑|하고|및")
_CLOCK = re.compile(r"^(오전|오후|아침|낮|저녁|밤)?(\d{1,2})(?::(\d{2})|시(?:(\d{1,2})분|반)?)?$")
_DUR = re.compile(r"^(?:(\d{1,2})시간(반)?|(\d{1,3})분)$")
_TIME_SEPS = ("부터", "에서", "~", "-")


@dataclass(frozen=True)
class When:
    kind: Literal["dates", "range", "weekdays"]
    dates: tuple[date, ...] = ()
    start: date | None = None
    end: date | None = None
    weekdays: tuple[int, ...] = ()


@dataclass(frozen=True)
class TimeSpan:
    start: time
    end: time | None


def _compact(expr: str) -> str:
    return re.sub(r"\s+", "", expr)


def _mk(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _next_month(d: date) -> tuple[int, int]:
    return (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)


def _monday(today: date, offset: int) -> date:
    return today - timedelta(days=today.weekday()) + timedelta(weeks=offset)


def _weekday_dates(tok: str, today: date, offset: int | None) -> list[date] | None:
    """'금' '금요일' '화목' → 날짜들. offset 이 있으면 그 주, 없으면 오늘 포함 가장 가까운 그 요일."""
    chars = tok.replace("요일", "").replace("욜", "")  # 구어 "금욜"
    if not chars or any(c not in WEEKDAYS for c in chars):
        return None
    out = []
    for c in chars:
        wd = WEEKDAYS.index(c)  # 0 = 월
        if offset is None:
            out.append(today + timedelta(days=(wd - today.weekday()) % 7))
        else:
            out.append(_monday(today, offset) + timedelta(days=wd))
    return out


def _one_date(tok: str, today: date) -> date | None:
    if tok in _DAY_WORDS:
        return today + timedelta(days=_DAY_WORDS[tok])
    if m := _MD.match(tok):
        y, mo, d = m.groups()
        if y:
            return _mk(int(y), int(mo), int(d))
        got = _mk(today.year, int(mo), int(d))
        if got is None:
            return None
        return got if got >= today else _mk(today.year + 1, int(mo), int(d))
    if m := _DAY.match(tok):
        d = int(m.group(1))
        got = _mk(today.year, today.month, d)
        if got is not None and got >= today:
            return got
        return _mk(*_next_month(today), d)
    return None


def _range_end(tok: str, start: date) -> date | None:
    """기간의 끝 — '19' '19일' 은 시작과 같은 달(앞이면 다음 달), '1/3' 은 시작 뒤 가장 가까운 그 날."""
    if m := re.fullmatch(r"(\d{1,2})일?", tok):
        d = int(m.group(1))
        got = _mk(start.year, start.month, d)
        if got is not None and got >= start:
            return got
        # 달을 넘기는 건 월말→월초("28일부터 3일까지")만 — 그 밖에 거꾸로면 잘못 쓴 것
        if start.day < 20 or d > 10:
            return None
        return _mk(*_next_month(start), d)
    if m := _MD.match(tok):
        y, mo, d = m.groups()
        if y:
            return _mk(int(y), int(mo), int(d))
        got = _mk(start.year, int(mo), int(d))
        if got is None:
            return None
        if got >= start:
            return got
        # 같은 달 안에서 거꾸로 가면("12/19~12/15") 내년이 아니라 잘못 쓴 것 — 해를 넘기는 건 달이 바뀔 때만
        return None if int(mo) == start.month else _mk(start.year + 1, int(mo), int(d))
    return None


def _range_start_this_year(tok: str, today: date) -> date | None:
    """기간의 시작 후보 — 연도 없는 날짜는 지났어도 올해(이번 달) 그대로. 진행 중 기간 판정용."""
    if m := _MD.match(tok):
        y, mo, d = m.groups()
        return _mk(int(y or today.year), int(mo), int(d))
    if m := _DAY.match(tok):
        return _mk(today.year, today.month, int(m.group(1)))
    return _one_date(tok, today)


_MAX_RANGE_DAYS = 92


def _split_range(t: str) -> tuple[str, str] | None:
    if "부터" in t:
        a, b = t.split("부터", 1)
    elif "~" in t:
        a, b = t.split("~", 1)
    elif "-" in t and not _ISO.match(t):
        a, b = t.split("-", 1)
    else:
        return None
    b = b.removesuffix("까지")
    return (a, b) if a and b else None


def resolve_when(expr: str, now: datetime) -> When | None:
    today = now.date()
    t = _compact(expr)
    if not t:
        return None
    if t.startswith("매주") or t.endswith("마다"):
        wds = resolve_weekdays(expr)
        return When("weekdays", weekdays=wds) if wds else None
    offset = None
    if m := _PREFIX.match(t):
        offset, t = _WEEK_WORDS[m.group(1)], t[m.end() :]
        if not t:  # "이번 주" 만 — 그 주 월~일
            mon = _monday(today, offset)
            return When("range", start=mon, end=mon + timedelta(days=6))
    if rng := _split_range(t):
        a, b = rng
        if offset is not None:  # "이번 주 월~금"
            da, db = _weekday_dates(a, today, offset), _weekday_dates(b, today, offset)
            if not da or not db or len(da) != 1 or len(db) != 1 or db[0] < da[0]:
                return None
            return When("range", start=da[0], end=db[0])
        start = _range_start_this_year(a, today)
        end = _range_end(b, start) if start else None
        if start is not None and start < today and (end is None or end < today):
            # 시작도 끝도 지났다 — 다음 해(달)로 민다. 시작만 지났고 끝이 오늘 이후면 진행 중 기간이라 그대로.
            start = _one_date(a, today)
            end = _range_end(b, start) if start else None
        if start is None or end is None or not 0 <= (end - start).days <= _MAX_RANGE_DAYS:
            return None
        return When("range", start=start, end=end)
    dates: list[date] = []
    for tok in (x for x in _LIST_SEP.split(t) if x):
        if (ws := _weekday_dates(tok, today, offset)) is not None:
            dates += ws
            continue
        if offset is not None:
            return None
        if (d := _one_date(tok, today)) is None:
            return None
        dates.append(d)
    return When("dates", dates=tuple(sorted(set(dates)))) if dates else None


def resolve_weekdays(expr: str) -> tuple[int, ...] | None:
    t = _compact(expr).removeprefix("매주").removesuffix("마다")
    if m := re.fullmatch(r"([월화수목금토일])(?:요일)?~([월화수목금토일])(?:요일)?", t):
        a, b = WEEKDAYS.index(m.group(1)) + 1, WEEKDAYS.index(m.group(2)) + 1
        return tuple(range(a, b + 1)) if a <= b else None
    t = _LIST_SEP.sub("", t).replace("요일", "")
    if not t or any(c not in WEEKDAYS for c in t):
        return None
    return tuple(sorted({WEEKDAYS.index(c) + 1 for c in t}))


def _clock(tok: str, *, bare_ok: bool) -> time | None:
    """'15시' '3시 반' '오후 2시 30분' '15:30' '정오'. 오전·오후 없는 1~8시는 오후(수업 시간대)."""
    if tok in ("정오", "낮12시"):
        return time(12, 0)
    m = _CLOCK.match(tok)
    if not m:
        return None
    ap, hh, mm1, mm2 = m.groups()
    if not bare_ok and ":" not in tok and "시" not in tok:
        return None
    h, mi = int(hh), int(mm1 or mm2 or 0)
    if ap and (h > 12 or h == 0 or (ap == "밤" and h == 12)):  # 24시간제와 모순·모호
        return None
    if tok.endswith("반"):
        mi = 30
    if h > 23 or mi > 59:
        return None
    if ap in ("오후", "저녁", "밤") and h < 12:
        h += 12
    elif ap in ("오전", "아침") and h == 12:
        h = 0
    elif ap in (None, "낮") and 1 <= h <= 8:
        h += 12
    return time(h, mi)


def resolve_time(expr: str) -> TimeSpan | None:
    t = re.sub(r"(으로|로)$", "", _compact(expr))
    if not t:
        return None
    seps = [x for x in _TIME_SEPS if x in t]
    if not seps:
        if t.endswith("까지"):  # 끝만 말함 — 못 푼다
            return None
        start = _clock(t, bare_ok=False)
        return TimeSpan(start, None) if start else None
    a, b = t.split(seps[0], 1)
    b = b.removesuffix("까지")
    start = _clock(a, bare_ok=True)
    if start is None or not b:
        return None
    if d := _DUR.match(b):
        h, half, mins = d.groups()
        dur = int(h) * 60 + (30 if half else 0) if h else int(mins)
        total = start.hour * 60 + start.minute + dur
        if dur <= 0 or total >= 24 * 60:
            return None
        return TimeSpan(start, time(total // 60, total % 60))
    end = _clock(b, bare_ok=True)
    if end is None or end <= start:
        return None
    return TimeSpan(start, end)


def normalize_room(expr: str) -> str:
    """공백·'호' 정리. 범위·층·건물 표현은 그대로 둔다 — 방으로 푸는 일은 서버(DB)가 한다."""
    t = re.sub(r"\s+", " ", expr.strip())
    t = re.sub(r"(\d)\s*호(?:실)?(?!관)", r"\1", t)
    t = re.sub(r"\s*([~\-])\s*", r"\1", t)
    t = re.sub(r"(\d)\s+층", r"\1층", t)
    return t.strip()

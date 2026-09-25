"""학교 시간대 (S10 §2.2). DB 는 naive UTC, 판정은 KST. now_utc 만 테스트가 monkeypatch 한다."""

from __future__ import annotations

import datetime as dt
from typing import Annotated
from zoneinfo import ZoneInfo

from pydantic import AfterValidator

from app.db import utcnow

SCHOOL_TZ = ZoneInfo("Asia/Seoul")
DAILY_HOUR_LOCAL = 4


def now_utc() -> dt.datetime:
    return utcnow()


def to_local(u: dt.datetime) -> dt.datetime:
    return u.replace(tzinfo=dt.UTC).astimezone(SCHOOL_TZ).replace(tzinfo=None)


def to_utc(local: dt.datetime) -> dt.datetime:
    return local.replace(tzinfo=SCHOOL_TZ).astimezone(dt.UTC).replace(tzinfo=None)


def local_now() -> dt.datetime:
    return to_local(now_utc())


def local_today() -> dt.date:
    return local_now().date()


def week_start(d: dt.date) -> dt.date:
    return d - dt.timedelta(days=d.weekday())


def local_dt(d: dt.date, h: int, m: int) -> dt.datetime:
    return dt.datetime(d.year, d.month, d.day, h, m)  # noqa: DTZ001 — naive 지역 시각이 설계 의도


# 쿼리의 날짜·시각 범위 (#49) — 0001·9999 년 근처는 ±일·시간대 변환이 OverflowError(500) 가 된다.
# ponytail: 정적 범위 — 운영 데이터가 이 밖으로 나갈 일 없음. 넓혀도 양 끝에 몇 주 여유만 두면 된다.
DATE_MIN, DATE_MAX = dt.date(2000, 1, 1), dt.date(2099, 12, 31)


def _in_range[T: dt.date](v: T) -> T:
    d = v.date() if isinstance(v, dt.datetime) else v
    if not DATE_MIN <= d <= DATE_MAX:
        raise ValueError(f"날짜는 {DATE_MIN} ~ {DATE_MAX}")
    return v


QDate = Annotated[dt.date, AfterValidator(_in_range)]
QDateTime = Annotated[dt.datetime, AfterValidator(_in_range)]

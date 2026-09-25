"""학교 시간대 (S10 §2.2). DB 는 naive UTC, 판정은 KST. now_utc 만 테스트가 monkeypatch 한다."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

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

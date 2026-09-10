"""Deterministic date parsing. No AI decides deadlines."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from dateutil import parser as duparser

LOCAL_TZ = ZoneInfo("America/New_York")

_MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec"
# e.g. "Tu September 29, 2026, 9:00AM EDT" / "Sep 20" / "Thursday, Sep 12 at 11:59 PM"
_DATE_RE = re.compile(
    rf"(?:(?:mon|tue?s?|wed|thu?r?s?|fri|sat|sun)[a-z]*\.?,?\s+)?"
    rf"((?:{_MONTHS})[a-z]*\.?)\s+(\d{{1,2}})(?:st|nd|rd|th)?"
    rf"(?:,?\s+(\d{{4}}))?"
    rf"(?:[,\s]+(?:at\s+)?(\d{{1,2}})(?::(\d{{2}}))?\s*([ap]\.?m\.?)?)?"
    rf"(?:\s*(EDT|EST|ET|PDT|PST|PT|UTC))?",
    re.IGNORECASE,
)


def now_local() -> datetime:
    return datetime.now(LOCAL_TZ)


def today_local() -> str:
    return now_local().date().isoformat()


def to_utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def from_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = duparser.isoparse(s)
    except (ValueError, TypeError):
        try:
            dt = duparser.parse(s)
        except (ValueError, TypeError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def to_local(s: str | None) -> datetime | None:
    dt = from_iso(s)
    return dt.astimezone(LOCAL_TZ) if dt else None


def parse_due_text(text: str, default_year: int | None = None, default_time: tuple[int, int] = (23, 59)) -> str | None:
    """Parse a human-written deadline like 'Due: Tu September 29, 2026, 9:00AM EDT'.

    Returns ISO UTC string or None. Year defaults to the current academic year
    (if the date would fall >6 months in the past, next year is used).
    """
    if not text:
        return None
    m = _DATE_RE.search(text)
    if not m:
        return None
    month_s, day_s, year_s, hh, mm, ampm, _tz = m.groups()
    try:
        month = duparser.parse(month_s[:3] + " 1 2000").month
    except (ValueError, TypeError):
        return None
    day = int(day_s)
    now = now_local()
    year = int(year_s) if year_s else (default_year or now.year)
    if hh:
        hour = int(hh)
        minute = int(mm) if mm else 0
        if ampm:
            ap = ampm.lower().replace(".", "")
            if ap == "pm" and hour < 12:
                hour += 12
            if ap == "am" and hour == 12:
                hour = 0
    else:
        hour, minute = default_time
    try:
        dt = datetime(year, month, day, hour, minute, tzinfo=LOCAL_TZ)
    except ValueError:
        return None
    if not year_s and (now - dt) > timedelta(days=180):
        dt = dt.replace(year=year + 1)
    return to_utc_iso(dt)


def humanize_due(iso: str | None, now: datetime | None = None) -> str:
    """'TODAY 11:59 PM', 'TOMORROW 9:00 AM', 'Fri Sep 12', 'OVERDUE 2d'."""
    dt = to_local(iso)
    if not dt:
        return ""
    now = now or now_local()
    delta = dt - now
    time_s = dt.strftime("%-I:%M %p")
    if delta.total_seconds() < 0:
        days = int(-delta.total_seconds() // 86400)
        return f"OVERDUE {days}d" if days else "OVERDUE"
    if dt.date() == now.date():
        return f"TODAY {time_s}"
    if dt.date() == (now + timedelta(days=1)).date():
        return f"TOMORROW {time_s}"
    if delta < timedelta(days=7):
        return dt.strftime("%a %b %-d") + f" {time_s}"
    return dt.strftime("%b %-d")


def bucket_due(iso: str | None, now: datetime | None = None) -> str:
    """OVERDUE | TODAY | TOMORROW | NEXT_3_DAYS | NEXT_7_DAYS | LATER | NONE"""
    dt = to_local(iso)
    if not dt:
        return "NONE"
    now = now or now_local()
    if dt < now:
        return "OVERDUE"
    d = (dt.date() - now.date()).days
    if d == 0:
        return "TODAY"
    if d == 1:
        return "TOMORROW"
    if d <= 3:
        return "NEXT_3_DAYS"
    if d <= 7:
        return "NEXT_7_DAYS"
    return "LATER"


def hours_remaining(iso: str | None, now: datetime | None = None) -> float | None:
    dt = to_local(iso)
    if not dt:
        return None
    now = now or now_local()
    return (dt - now).total_seconds() / 3600.0

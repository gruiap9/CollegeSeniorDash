from datetime import datetime
from zoneinfo import ZoneInfo

from morningbrief.utils.dates import bucket_due, humanize_due, parse_due_text

NY = ZoneInfo("America/New_York")


def test_parse_cs520_style():
    iso = parse_due_text("Homework 1 Due: Tu September 29, 2026, 9:00AM EDT")
    assert iso == "2026-09-29T13:00:00+00:00"


def test_parse_pm():
    iso = parse_due_text("Due: Tu Dec 15, 2026, 11:55PM EST")
    assert iso == "2026-12-16T04:55:00+00:00"


def test_parse_no_time_defaults_2359():
    iso = parse_due_text("Due Sep 20", default_year=2026)
    assert iso == "2026-09-21T03:59:00+00:00"


def test_no_date():
    assert parse_due_text("nothing here") is None


def test_buckets():
    now = datetime(2026, 9, 9, 8, 0, tzinfo=NY)
    assert bucket_due("2026-09-09T23:59:00-04:00", now) == "TODAY"
    assert bucket_due("2026-09-10T09:00:00-04:00", now) == "TOMORROW"
    assert bucket_due("2026-09-12T09:00:00-04:00", now) == "NEXT_3_DAYS"
    assert bucket_due("2026-09-15T09:00:00-04:00", now) == "NEXT_7_DAYS"
    assert bucket_due("2026-09-01T09:00:00-04:00", now) == "OVERDUE"
    assert humanize_due("2026-09-09T23:59:00-04:00", now) == "TODAY 11:59 PM"

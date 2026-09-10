from pathlib import Path

from morningbrief.collectors.course_sites import ingest, parse_cs461, parse_cs520
from morningbrief.collectors.base import CollectResult
from morningbrief.config import CourseSite

FX = Path(__file__).parent / "fixtures"


def test_cs520_deadlines():
    d = parse_cs520("CS520", "https://people.cs.umass.edu/~brun/class/2026Fall/CS520/", (FX / "cs520.html").read_text())
    titles = {a.title: a.due_date for a in d.assignments}
    assert titles["Homework 1"] == "2026-09-29T13:00:00+00:00"
    assert titles["Final project completion"] == "2026-12-16T04:55:00+00:00"
    assert "news" in d.sections and "schedule" in d.sections
    assert d.news[0]["text"].startswith("The first class")


def test_cs461_sections():
    d = parse_cs461("CS461", "https://compscix61.org/", (FX / "cs461.html").read_text())
    assert "general" in d.sections and "week-1-introduction" in d.sections
    assert any("Midterm" in n["text"] for n in d.news)


def test_change_detection_flow(db):
    site = CourseSite(course="CS520", url="u", parser="cs520")
    html = (FX / "cs520.html").read_text()
    d = parse_cs520("CS520", "u", html)
    ingest(db, site, d, CollectResult("x"))
    assert db.events_since("2000-01-01") == []
    moved = html.replace("Due: Tu September 29, 2026, 9:00AM EDT", "Due: Tu September 27, 2026, 9:00AM EDT")
    d2 = parse_cs520("CS520", "u", moved)
    res = CollectResult("x")
    ingest(db, site, d2, res)
    kinds = {e["kind"] for e in db.events_since("2000-01-01")}
    assert "assignment.due_changed" in kinds and "site.changed" in kinds

from morningbrief.db.models import Assignment
from morningbrief.db.repo import snapshot_section, upsert_assignment


def test_assignment_change_detection(db):
    a = Assignment(source="cs520", course="CS520", assignment_id="hw1", title="Homework 1", due_date="2026-09-29T13:00:00+00:00")
    r = upsert_assignment(db, a)
    assert r["new"] and not r["changes"]
    a.due_date = "2026-09-27T13:00:00+00:00"
    r = upsert_assignment(db, a)
    assert not r["new"]
    assert r["changes"]["due_date"] == ("2026-09-29T13:00:00+00:00", "2026-09-27T13:00:00+00:00")


def test_events_dedupe(db):
    assert db.add_event("job.oa", "Amazon OA", dedupe_key="x")
    assert not db.add_event("job.oa", "Amazon OA", dedupe_key="x")
    assert len(db.events_since("2000-01-01")) == 1


def test_section_snapshot(db):
    r = snapshot_section(db, "CS520", "news", "a", "h1")
    assert r["new"]
    r = snapshot_section(db, "CS520", "news", "a", "h1")
    assert not r["changed"]
    r = snapshot_section(db, "CS520", "news", "b", "h2")
    assert r["changed"] and r["old"] == "a"

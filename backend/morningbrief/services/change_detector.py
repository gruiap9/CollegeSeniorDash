"""Derive events from state that collectors alone cannot see.

- new grades (assignment became graded)              -> grade.new
- new assignments discovered in the last 24h         -> assignment.new
- unsubmitted work due within 6 hours                -> assignment.due_soon (notification-worthy)
- overdue & unsubmitted                              -> assignment.overdue
"""

from __future__ import annotations

from datetime import timedelta

from ..config import Config
from ..db.database import Database
from ..utils.dates import from_iso, hours_remaining, now_local, today_local


def emit_assignment_change_events(db: Database, a, changes: dict) -> int:
    """Shared by collectors after upsert_assignment: due-date and grade changes."""
    n = 0
    if "due_date" in changes:
        old, new = changes["due_date"]
        if db.add_event("assignment.due_changed", f"{a.course} — {a.title} deadline changed", detail=f"{old} → {new}",
                        url=a.url, source=a.source, course=a.course, importance=3,
                        dedupe_key=f"due:{a.source}:{a.course}:{a.assignment_id}:{new}"):
            n += 1
    if "grade" in changes and changes["grade"][1]:
        if db.add_event("grade.new", f"{a.course} — {a.title}", detail=str(changes["grade"][1]), url=a.url, source=a.source,
                        course=a.course, importance=2, dedupe_key=f"grade:{a.course}:{a.assignment_id}"):
            n += 1
    elif "status" in changes and changes["status"][1] == "graded":
        if db.add_event("grade.new", f"{a.course} — {a.title}", detail=a.grade or "Grade available", url=a.url,
                        source=a.source, course=a.course, importance=2, dedupe_key=f"grade:{a.course}:{a.assignment_id}"):
            n += 1
    return n


def detect_changes(cfg: Config, db: Database) -> int:
    n = 0
    now = now_local()
    day_ago = (now - timedelta(hours=24)).astimezone().isoformat()
    today = today_local()

    bootstrapped = db.get_meta("bootstrapped_at")
    if not bootstrapped:
        # First ever sync: everything is "new"; don't flood the timeline.
        db.set_meta("bootstrapped_at", now.isoformat())
    new_rows = db.rows("SELECT * FROM assignments WHERE first_seen >= ? AND source != 'gradescope'", (day_ago,)) if bootstrapped else []
    for a in new_rows:
        # Skip assignments already long past when first discovered (backfill noise).
        due = from_iso(a["due_date"])
        if due and (now - due.astimezone(now.tzinfo)) > timedelta(days=2):
            continue
        if db.add_event("assignment.new", f"{a['course']} — {a['title']}", detail=a["due_date"] or "no due date", url=a["url"],
                        source=a["source"], course=a["course"], importance=1,
                        dedupe_key=f"new:{a['source']}:{a['course']}:{a['assignment_id']}"):
            n += 1

    for a in db.rows("SELECT * FROM assignments WHERE status='graded' AND grade IS NOT NULL"):
        if db.add_event("grade.new", f"{a['course']} — {a['title']}", detail=a["grade"], url=a["url"], source=a["source"],
                        course=a["course"], importance=2, dedupe_key=f"grade:{a['course']}:{a['assignment_id']}"):
            n += 1

    for a in db.rows("SELECT * FROM assignments WHERE due_date IS NOT NULL AND (status='unsubmitted' OR status='unknown') AND source='canvas'"):
        h = hours_remaining(a["due_date"], now)
        if h is None:
            continue
        if 0 < h <= 6:
            if db.add_event("assignment.due_soon", f"{a['course']} — {a['title']} due in {int(h)}h", detail="Not submitted",
                            url=a["url"], source=a["source"], course=a["course"], importance=3,
                            dedupe_key=f"duesoon:{a['course']}:{a['assignment_id']}:{today}"):
                n += 1
        elif -72 < h <= 0:
            if db.add_event("assignment.overdue", f"{a['course']} — {a['title']} overdue", detail="Not submitted", url=a["url"],
                            source=a["source"], course=a["course"], importance=2,
                            dedupe_key=f"overdue:{a['course']}:{a['assignment_id']}"):
                n += 1
    return n

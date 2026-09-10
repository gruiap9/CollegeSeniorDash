"""Classify unclassified emails and emit events."""

from __future__ import annotations

import logging

from ..classifiers import importance, job_email, school_email
from ..classifiers.gradescope_email import parse_gradescope_email
from ..classifiers.piazza_email import parse_piazza_email
from ..config import Config
from ..db.database import Database
from ..db.models import Assignment, PiazzaPost
from ..db.repo import set_email_classification, upsert_assignment, upsert_piazza_post

log = logging.getLogger(__name__)


def known_people(db: Database) -> dict[str, str]:
    """Senders we have previously labelled professor/ta/advisor; helps rules on later mail."""
    out: dict[str, str] = {}
    for r in db.rows("SELECT sender_email, school_role FROM emails WHERE category='school' AND school_role IN ('professor','ta','advisor') AND sender_email != ''"):
        out[r["sender_email"]] = r["school_role"]
    return out


def process_unclassified(cfg: Config, db: Database, limit: int = 300) -> int:
    rows = db.rows("SELECT * FROM emails WHERE classified_at IS NULL ORDER BY received_at DESC LIMIT ?", (limit,))
    people = known_people(db)
    n = 0
    for r in rows:
        try:
            _classify_one(cfg, db, r, people)
            n += 1
        except Exception as e:  # never let one email break the sync
            log.exception("classification failed for %s: %s", r["id"], e)
            set_email_classification(db, r["id"], category="other", importance=0)
    return n


def _classify_one(cfg: Config, db: Database, r: dict, people: dict[str, str]) -> None:
    kind = importance.route(r["sender_email"], r["subject"])
    sender, email, subject, body = r["sender"] or "", r["sender_email"] or "", r["subject"] or "", r["body"] or ""

    if kind == "gradescope":
        g = parse_gradescope_email(subject, body)
        set_email_classification(db, r["id"], category="gradescope", importance=2 if g.kind == "grade_published" else 1,
                                 summary=g.summary, company=None)
        if g.course and g.assignment:
            a = Assignment(source="gradescope", course=g.course, assignment_id=g.slug(), title=g.assignment,
                           status="graded" if g.kind == "grade_published" else ("submitted" if g.kind == "submitted" else None),
                           grade=g.grade, url=g.url or r["url"], updated_at=r["received_at"])
            res = upsert_assignment(db, a)
            if g.kind == "grade_published":
                db.add_event("grade.new", f"{g.course} — {g.assignment}", detail=g.grade or "Grade available",
                             url=g.url or r["url"], source="gradescope", course=g.course, importance=2,
                             dedupe_key=f"grade:{g.course}:{g.slug()}")
            elif g.kind == "submitted" and res["new"]:
                db.add_event("assignment.submitted", f"{g.course} — {g.assignment} submitted", url=g.url or r["url"],
                             source="gradescope", course=g.course, importance=0,
                             dedupe_key=f"submitted:{g.course}:{g.slug()}:{r['message_id']}")
            elif g.kind == "regrade":
                db.add_event("grade.regrade", f"{g.course} — {g.assignment} regrade response", url=g.url or r["url"],
                             source="gradescope", course=g.course, importance=2,
                             dedupe_key=f"regrade:{r['message_id']}")
        return

    if kind == "piazza":
        p = parse_piazza_email(subject, body, received_at=r["received_at"])
        set_email_classification(db, r["id"], category="piazza", importance=1 if p.author_role in ("instructor", "ta") else 0,
                                 summary=p.title)
        if p.course:
            post = PiazzaPost(course=p.course, post_id=p.post_id or r["message_id"], title=p.title, author_role=p.author_role,
                              kind=p.kind, created_at=r["received_at"], updated_at=r["received_at"], body=p.body, url=p.url or r["url"])
            upsert_piazza_post(db, post, weight=p.weight)
            if p.author_role == "instructor" and p.kind in ("note", "answer"):
                db.add_event("piazza.instructor", f"{p.course} • {p.title}", detail=p.body[:200], url=p.url or r["url"],
                             source="piazza", course=p.course, importance=2, dedupe_key=f"piazza:{p.course}:{p.post_id or r['message_id']}")
        return

    if kind == "canvas":
        set_email_classification(db, r["id"], category="canvas", importance=0, summary="Canvas notification")
        return

    if kind == "school":
        s = school_email.classify(cfg, sender, email, subject, body, people)
        set_email_classification(db, r["id"], category="school", school_role=s.role, importance=s.importance, summary=s.summary)
        if s.importance >= 2 and s.role in ("professor", "ta", "advisor", "registrar", "financial", "admin"):
            db.add_event("email.important", f"{sender or email} — {subject}", detail=s.summary or r["snippet"], url=r["url"],
                         source=r["account"], course=s.course, importance=s.importance,
                         dedupe_key=f"email:{r['account']}:{r['message_id']}")
        return

    j = job_email.classify(cfg, sender, email, subject, body)
    if not j.job_related:
        set_email_classification(db, r["id"], category="other", importance=0)
        return
    imp = importance.JOB_EVENT_IMPORTANCE.get(j.event, 0)
    set_email_classification(db, r["id"], category="job", company=j.company, job_status=j.event, importance=imp, summary=j.summary)
    if j.event != "JOB_OTHER":
        db.add_event(f"job.{j.event.lower()}", f"{j.company or sender} — {j.event.replace('_', ' ').title()}",
                     detail=j.summary or subject, url=r["url"], source=r["account"], importance=imp,
                     dedupe_key=f"job:{r['account']}:{r['message_id']}")

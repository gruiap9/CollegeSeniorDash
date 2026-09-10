"""Upsert helpers that also emit change events (new / changed)."""

from __future__ import annotations

import json

from .database import Database, utcnow
from .models import Article, Assignment, Email, PiazzaPost


def upsert_assignment(db: Database, a: Assignment) -> dict:
    """Insert or update an assignment; returns {"new": bool, "changes": {field: (old, new)}}."""
    now = utcnow()
    existing = db.row(
        "SELECT * FROM assignments WHERE source=? AND course=? AND assignment_id=?",
        (a.source, a.course, a.assignment_id),
    )
    if existing is None:
        db.conn.execute(
            "INSERT INTO assignments(source,course,assignment_id,title,due_date,status,grade,points_possible,url,raw,first_seen,last_seen,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (a.source, a.course, a.assignment_id, a.title, a.due_date, a.status, a.grade,
             a.points_possible, a.url, a.raw_json(), now, now, a.updated_at),
        )
        db.conn.commit()
        return {"new": True, "changes": {}}

    changes: dict[str, tuple] = {}
    for f in ("title", "due_date", "status", "grade", "points_possible", "url"):
        old, new = existing.get(f), getattr(a, f)
        if new is not None and old != new:
            changes[f] = (old, new)
    db.conn.execute(
        "UPDATE assignments SET title=?, due_date=COALESCE(?,due_date), status=COALESCE(?,status), "
        "grade=COALESCE(?,grade), points_possible=COALESCE(?,points_possible), url=COALESCE(?,url), "
        "raw=?, last_seen=?, updated_at=COALESCE(?,updated_at) WHERE id=?",
        (a.title, a.due_date, a.status, a.grade, a.points_possible, a.url, a.raw_json(), now,
         a.updated_at, existing["id"]),
    )
    db.conn.commit()
    return {"new": False, "changes": changes}


def upsert_email(db: Database, e: Email) -> bool:
    """Insert email if unseen. Returns True when newly inserted."""
    exists = db.row("SELECT id FROM emails WHERE account=? AND message_id=?", (e.account, e.message_id))
    if exists:
        return False
    db.conn.execute(
        "INSERT INTO emails(message_id,account,thread_id,sender,sender_email,subject,snippet,body,received_at,url,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (e.message_id, e.account, e.thread_id, e.sender, e.sender_email, e.subject, e.snippet,
         e.body, e.received_at, e.url, utcnow()),
    )
    db.conn.commit()
    return True


def upsert_piazza_post(db: Database, p: PiazzaPost, weight: float = 0.0) -> dict:
    existing = db.row("SELECT * FROM piazza_posts WHERE course=? AND post_id=?", (p.course, p.post_id))
    if existing is None:
        db.conn.execute(
            "INSERT INTO piazza_posts(course,post_id,title,author_role,kind,created_at,updated_at,body,url,weight,first_seen) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (p.course, p.post_id, p.title, p.author_role, p.kind, p.created_at, p.updated_at, p.body, p.url, weight, utcnow()),
        )
        db.conn.commit()
        return {"new": True, "updated": False}
    updated = bool(p.updated_at and p.updated_at != existing.get("updated_at"))
    db.conn.execute(
        "UPDATE piazza_posts SET title=?, author_role=?, kind=?, updated_at=COALESCE(?,updated_at), body=?, url=COALESCE(?,url), weight=MAX(weight,?) WHERE id=?",
        (p.title, p.author_role, p.kind, p.updated_at, p.body, p.url, weight, existing["id"]),
    )
    db.conn.commit()
    return {"new": False, "updated": updated}


def upsert_article(db: Database, art: Article) -> bool:
    exists = db.row("SELECT id FROM news WHERE article_id=?", (art.article_id,))
    if exists:
        return False
    db.conn.execute(
        "INSERT INTO news(article_id,source,title,published_at,url,summary,first_seen) VALUES(?,?,?,?,?,?,?)",
        (art.article_id, art.source, art.title, art.published_at, art.url, art.summary, utcnow()),
    )
    db.conn.commit()
    return True


def snapshot_section(db: Database, course: str, section: str, content: str, content_hash: str) -> dict:
    """Store a page section; returns {"new": bool, "changed": bool, "old": str|None}."""
    now = utcnow()
    existing = db.row("SELECT * FROM page_sections WHERE course=? AND section=?", (course, section))
    if existing is None:
        db.conn.execute(
            "INSERT INTO page_sections(course,section,content,hash,first_seen,last_seen) VALUES(?,?,?,?,?,?)",
            (course, section, content, content_hash, now, now),
        )
        db.conn.commit()
        return {"new": True, "changed": False, "old": None}
    changed = existing["hash"] != content_hash
    db.conn.execute(
        "UPDATE page_sections SET content=?, hash=?, last_seen=? WHERE id=?",
        (content, content_hash, now, existing["id"]),
    )
    db.conn.commit()
    return {"new": False, "changed": changed, "old": existing["content"] if changed else None}


def set_email_classification(db: Database, email_row_id: int, **fields) -> None:
    allowed = {"category", "company", "job_status", "school_role", "importance", "summary"}
    cols = {k: v for k, v in fields.items() if k in allowed}
    if not cols:
        return
    sets = ", ".join(f"{k}=?" for k in cols)
    db.conn.execute(
        f"UPDATE emails SET {sets}, classified_at=? WHERE id=?",
        (*cols.values(), utcnow(), email_row_id),
    )
    db.conn.commit()


def json_dumps(obj) -> str:
    return json.dumps(obj, default=str)

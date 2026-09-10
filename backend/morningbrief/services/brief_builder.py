"""Assemble morning_brief.json from the database. Pure read + shape; no network."""

from __future__ import annotations

import json
import os
from datetime import timedelta
from pathlib import Path

from ..config import Config, brief_path
from ..db.database import Database
from ..utils.dates import bucket_due, humanize_due, hours_remaining, now_local, to_local

JOB_ORDER = ["OFFER", "INTERVIEW", "OA", "NEXT_ROUND", "RECRUITER", "APPLICATION_RECEIVED", "REJECTION"]


def _local(iso: str | None) -> str | None:
    dt = to_local(iso)
    return dt.isoformat() if dt else None


def build_brief(cfg: Config, db: Database) -> dict:
    now = now_local()
    since_24h = (now - timedelta(hours=24)).isoformat()
    since_7d = (now - timedelta(days=7)).isoformat()

    # ---- since yesterday (event timeline)
    events = [
        {
            "kind": e["kind"], "title": e["title"], "detail": e["detail"], "url": e["url"], "course": e["course"],
            "importance": e["importance"], "at": _local(e["created_at"]),
        }
        for e in db.events_since(since_24h)
        if e["importance"] >= 1
    ][:25]

    # ---- job search
    jobs_7d = db.rows("SELECT * FROM emails WHERE category='job' AND job_status IS NOT NULL AND received_at >= ? ORDER BY received_at DESC", (since_7d,))
    counts = {k: 0 for k in JOB_ORDER}
    for j in jobs_7d:
        if j["job_status"] in counts:
            counts[j["job_status"]] += 1
    recent_jobs = [j for j in jobs_7d if j["received_at"] and j["received_at"] >= since_24h and j["job_status"] != "JOB_OTHER"]
    recent_jobs.sort(key=lambda j: (JOB_ORDER.index(j["job_status"]) if j["job_status"] in JOB_ORDER else 99, j["received_at"]), reverse=False)
    job_items = [
        {"company": j["company"] or j["sender"], "event": j["job_status"], "summary": j["summary"] or j["subject"],
         "subject": j["subject"], "url": j["url"], "received_at": _local(j["received_at"]), "importance": j["importance"]}
        for j in recent_jobs[:12]
    ]

    # ---- important email
    imp = db.rows("SELECT * FROM emails WHERE category='school' AND importance >= 2 AND received_at >= ? ORDER BY importance DESC, received_at DESC LIMIT 10", (since_24h,))
    ignored = db.row("SELECT COUNT(*) AS n FROM emails WHERE received_at >= ? AND importance = 0", (since_24h,))
    important_email = [
        {"sender": e["sender"], "sender_email": e["sender_email"], "role": e["school_role"], "subject": e["subject"],
         "summary": e["summary"] or e["snippet"], "url": e["url"], "received_at": _local(e["received_at"]), "course": None}
        for e in imp
    ]

    # ---- school / assignments
    assignments = db.rows("SELECT * FROM assignments WHERE due_date IS NOT NULL AND due_date >= ? ORDER BY due_date", ((now - timedelta(days=3)).isoformat(),))
    buckets: dict[str, list] = {"OVERDUE": [], "TODAY": [], "TOMORROW": [], "NEXT_3_DAYS": [], "NEXT_7_DAYS": [], "LATER": []}
    seen_keys: set[tuple] = set()
    for a in assignments:
        key = (a["course"], a["title"].lower())
        if key in seen_keys:
            continue
        seen_keys.add(key)
        b = bucket_due(a["due_date"], now)
        if b == "OVERDUE" and a["status"] in ("submitted", "graded"):
            continue
        h = hours_remaining(a["due_date"], now)
        buckets[b].append({
            "course": a["course"], "title": a["title"], "due": _local(a["due_date"]), "due_label": humanize_due(a["due_date"], now),
            "status": a["status"], "grade": a["grade"], "url": a["url"], "source": a["source"],
            "hours_remaining": round(h, 1) if h is not None else None,
        })
    new_grades = [
        {"course": e["course"], "title": e["title"].split(" — ", 1)[-1], "grade": e["detail"], "url": e["url"], "at": _local(e["created_at"])}
        for e in db.events_since(since_24h) if e["kind"] == "grade.new"
    ]
    changes = [
        {"course": e["course"], "title": e["title"], "detail": e["detail"], "url": e["url"]}
        for e in db.events_since(since_24h) if e["kind"] in ("assignment.due_changed", "site.changed")
    ]

    # ---- piazza
    from ..summarizers.piazza import summarize_courses

    piazza = summarize_courses(cfg, db, since_24h)

    # ---- news
    from ..summarizers.news import top_stories

    news = top_stories(cfg, db, since_24h) if cfg.news_enabled else []

    # ---- sync status
    sync = {r["source"]: {"last_success": _local(r["last_success"]), "last_error": r["last_error"]} for r in db.rows("SELECT * FROM sync_state")}

    return {
        "version": 1,
        "generated_at": now.isoformat(),
        "date": now.date().isoformat(),
        "greeting": _greeting(now, cfg.user_name),
        "since_yesterday": events,
        "job_search": {"counts_7d": counts, "items": job_items},
        "important_email": important_email,
        "ignored_email_count": ignored["n"] if ignored else 0,
        "school": {k.lower(): v for k, v in buckets.items()} | {"new_grades": new_grades, "changes": changes},
        "piazza": piazza,
        "news": news,
        "sync_status": sync,
    }


def _greeting(now, name: str) -> str:
    h = now.hour
    word = "Good morning" if h < 12 else ("Good afternoon" if h < 18 else "Good evening")
    return f"{word}{', ' + name if name else ''}"


def write_brief(brief: dict, path: Path | None = None) -> Path:
    path = path or brief_path()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(brief, indent=2, ensure_ascii=False))
    os.replace(tmp, path)  # atomic so the Swift app never reads a half-written file
    return path

"""Group Piazza posts per course and summarize what matters.

Deterministic weighting picks candidates; the LLM (if available) writes the
2-3 bullet "important" summary. Without an LLM we show the top-weighted titles.
"""

from __future__ import annotations

from ..config import Config
from ..db.database import Database
from ..services import llm

_SCHEMA = {
    "type": "object",
    "properties": {
        "important": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"label": {"type": "string"}, "summary": {"type": "string"}, "post_id": {"type": ["string", "null"]}},
                "required": ["label", "summary", "post_id"],
                "additionalProperties": False,
            },
        },
        "other_summary": {"type": "string"},
    },
    "required": ["important", "other_summary"],
    "additionalProperties": False,
}

_SYSTEM = (
    "You summarize a day of Piazza activity for one course for a busy student. Return only JSON. "
    "`important`: at most 4 items that change what the student should do or know: instructor/TA clarifications, "
    "deadline/exam info, widespread bugs in starter code, logistics. Each has a short label (e.g. 'Instructor clarification', "
    "'Homework issue', 'Exam'), a one-sentence summary, and the post_id it came from if known. "
    "`other_summary`: one line like '8 debugging discussions • 4 study-group posts'. Do not invent facts."
)


def summarize_courses(cfg: Config, db: Database, since_iso: str) -> list[dict]:
    courses = [r["course"] for r in db.rows("SELECT DISTINCT course FROM piazza_posts ORDER BY course")]
    out = []
    for course in courses:
        posts = db.rows(
            "SELECT * FROM piazza_posts WHERE course=? AND (first_seen >= ? OR updated_at >= ?) ORDER BY weight DESC, created_at DESC",
            (course, since_iso, since_iso),
        )
        if not posts:
            out.append({"course": course, "new_count": 0, "important": [], "other_summary": "No new activity.", "url": _course_url(db, course)})
            continue
        top = [p for p in posts if p["weight"] >= 0.6][:12]
        result = None
        if llm.available(cfg) and posts:
            corpus = "\n\n".join(
                f"[post {p['post_id']}] role={p['author_role']} kind={p['kind']} weight={p['weight']}\nTitle: {p['title']}\n{(p['body'] or '')[:800]}"
                for p in posts[:40]
            )
            result = llm.structured(cfg, system=_SYSTEM, user=f"Course: {course}\n{len(posts)} new messages.\n\n{corpus}", schema=_SCHEMA, max_tokens=800)
        url_by_id = {p["post_id"]: p["url"] for p in posts}
        if result:
            important = [
                {"label": i["label"], "summary": i["summary"], "url": url_by_id.get(i.get("post_id") or "", _course_url(db, course))}
                for i in result.get("important", [])
            ]
            other = result.get("other_summary", "")
        else:
            important = [{"label": p["author_role"].title(), "summary": p["title"], "url": p["url"]} for p in top[:4]]
            rest = len(posts) - len(important)
            other = f"{rest} other posts" if rest > 0 else ""
        out.append({"course": course, "new_count": len(posts), "important": important, "other_summary": other, "url": _course_url(db, course)})
    return out


def _course_url(db: Database, course: str) -> str | None:
    r = db.row("SELECT url FROM piazza_posts WHERE course=? AND url IS NOT NULL ORDER BY created_at DESC LIMIT 1", (course,))
    if r and r["url"]:
        return r["url"].split("/post/")[0]
    return None

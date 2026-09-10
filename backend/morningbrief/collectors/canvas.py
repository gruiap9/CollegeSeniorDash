"""Canvas LMS collector (official REST API, personal access token).

Setup: Canvas → Account → Settings → "New Access Token", then
`morningbrief setup-canvas`. The token is stored in the Keychain.
Read-only usage: courses, assignments (with submission), upcoming events.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import httpx

from .. import secrets
from ..config import Config
from ..db.database import Database
from ..db.models import Assignment
from ..db.repo import upsert_assignment
from .base import CollectResult, Collector

log = logging.getLogger(__name__)
SOURCE = "canvas"


def interactive_setup(cfg: Config) -> int:
    import getpass

    base = input(f"Canvas base URL [{cfg.canvas_base_url}]: ").strip() or cfg.canvas_base_url
    token = getpass.getpass("Canvas access token (hidden): ").strip()
    if not token:
        print("no token given")
        return 1
    cfg.canvas_base_url = base.rstrip("/")
    with httpx.Client(timeout=20) as c:
        r = c.get(f"{cfg.canvas_base_url}/api/v1/users/self", headers={"Authorization": f"Bearer {token}"})
    if r.status_code != 200:
        print(f"token check failed: HTTP {r.status_code}")
        return 1
    secrets.set_secret(secrets.CANVAS_TOKEN, token)
    cfg.canvas_enabled = True
    cfg.save()
    print(f"Canvas authorized as {r.json().get('name')}; canvas_enabled=true")
    return 0


class CanvasClient:
    def __init__(self, base_url: str, token: str):
        self.base = base_url.rstrip("/")
        self.http = httpx.Client(timeout=30, headers={"Authorization": f"Bearer {token}"})

    def close(self):
        self.http.close()

    def paged(self, path: str, **params) -> list[dict]:
        params.setdefault("per_page", 100)
        url = f"{self.base}/api/v1{path}"
        out: list[dict] = []
        while url:
            r = self.http.get(url, params=params)
            r.raise_for_status()
            out.extend(r.json())
            params = {}
            url = None
            for part in r.headers.get("link", "").split(","):
                if 'rel="next"' in part:
                    url = part.split(";")[0].strip(" <>")
        return out

    def active_courses(self) -> list[dict]:
        courses = self.paged("/courses", enrollment_state="active", include=["term"])
        return [c for c in courses if c.get("name") and not c.get("access_restricted_by_date")]

    def assignments(self, course_id: int) -> list[dict]:
        return self.paged(
            f"/courses/{course_id}/assignments",
            include=["submission"],
            order_by="due_at",
            bucket="unsubmitted",
        ) + self.paged(f"/courses/{course_id}/assignments", include=["submission"], order_by="due_at", bucket="past")


def course_code(course: dict) -> str:
    code = course.get("course_code") or course.get("name") or f"course{course.get('id')}"
    m = re.search(r"\b(?:COMPSCI|CS|CICS|INFO|MATH|STAT)\s?-?(\d{3}[A-Z]?)\b", code, re.I)
    if m:
        prefix = re.sub(r"[\s\-]", "", m.group(0)[: -len(m.group(1))]).upper().replace("COMPSCI", "CS")
        return f"{prefix}{m.group(1).upper()}"
    return re.sub(r"\s+", "", code)[:16].upper()


def normalize_assignment(course: str, a: dict) -> Assignment:
    sub = a.get("submission") or {}
    status = "unknown"
    grade = None
    if sub.get("workflow_state") == "graded" or sub.get("score") is not None:
        status = "graded"
        pts = a.get("points_possible")
        grade = f"{sub.get('score')}/{pts}" if pts is not None else str(sub.get("score"))
    elif sub.get("submitted_at") or sub.get("workflow_state") in ("submitted", "pending_review"):
        status = "submitted"
    elif a.get("submission_types") and "none" not in a["submission_types"]:
        status = "unsubmitted"
    due = a.get("due_at")
    if due:
        due = datetime.fromisoformat(due.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    return Assignment(
        source=SOURCE,
        course=course,
        assignment_id=str(a["id"]),
        title=a.get("name") or "(untitled)",
        due_date=due,
        status=status,
        grade=grade,
        points_possible=a.get("points_possible"),
        url=a.get("html_url"),
        updated_at=a.get("updated_at"),
        raw={"id": a.get("id"), "due_at": a.get("due_at"), "submission_types": a.get("submission_types"),
             "workflow_state": sub.get("workflow_state"), "score": sub.get("score"), "late": sub.get("late")},
    )


class CanvasCollector(Collector):
    name = SOURCE

    def enabled(self, cfg: Config) -> bool:
        return cfg.canvas_enabled

    def collect(self, cfg: Config, db: Database) -> CollectResult:
        res = CollectResult(SOURCE)
        token = secrets.get_secret(secrets.CANVAS_TOKEN)
        if not token:
            raise RuntimeError("Canvas token missing; run `morningbrief setup-canvas`")
        client = CanvasClient(cfg.canvas_base_url, token)
        try:
            for course in client.active_courses():
                code = course_code(course)
                seen: set[str] = set()
                for a in client.assignments(course["id"]):
                    if str(a["id"]) in seen:
                        continue
                    seen.add(str(a["id"]))
                    r = upsert_assignment(db, normalize_assignment(code, a))
                    if r["new"]:
                        res.new += 1
                    elif r["changes"]:
                        res.updated += 1
                res.notes.append(f"{code}:{len(seen)}")
        finally:
            client.close()
        return res

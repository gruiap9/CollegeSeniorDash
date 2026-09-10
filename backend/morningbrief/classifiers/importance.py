"""Routing: decide which classifier handles an email, and produce events."""

from __future__ import annotations

import re

GRADESCOPE_DOMAINS = ("gradescope.com",)
PIAZZA_DOMAINS = ("piazza.com",)
CANVAS_DOMAINS = ("instructure.com",)


def route(sender_email: str, subject: str) -> str:
    e = (sender_email or "").lower()
    if any(d in e for d in GRADESCOPE_DOMAINS):
        return "gradescope"
    if any(d in e for d in PIAZZA_DOMAINS):
        return "piazza"
    if any(d in e for d in CANVAS_DOMAINS):
        return "canvas"
    if e.endswith("umass.edu") or re.search(r"\bumass\b", subject or "", re.I):
        return "school"
    return "job_or_other"


JOB_EVENT_IMPORTANCE = {
    "OFFER": 3,
    "INTERVIEW": 3,
    "OA": 3,
    "NEXT_ROUND": 2,
    "REJECTION": 1,
    "RECRUITER": 1,
    "APPLICATION_RECEIVED": 1,
    "JOB_OTHER": 0,
}

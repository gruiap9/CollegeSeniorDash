"""Parse Piazza notification/digest emails into posts with weights.

Weights: instructor post/response 1.0, TA response 0.8, announcement 0.8,
followups 0.4, student question 0.3, social 0.1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_COURSE_SUBJ = re.compile(r"^\[?\s*((?:CS|COMPSCI|CICS)\s?-?\d{3}[A-Z]?(?:/\d{3})?)[^\]]*\]?", re.I)
_URL = re.compile(r"https://piazza\.com/class/([a-z0-9]+)(?:/post/(\d+))?", re.I)
_INSTRUCTOR = re.compile(r"\b(instructor|professor|prof\.)\b", re.I)
_TA = re.compile(r"\b(TA|teaching assistant|course staff)\b")
_ANNOUNCE = re.compile(r"\b(announcement|note|pinned)\b", re.I)
_SOCIAL = re.compile(r"\b(study group|study partner|anyone want|looking for (a )?(group|partner|teammate)|lost and found)\b", re.I)


@dataclass
class PiazzaInfo:
    course: str | None
    post_id: str | None
    title: str
    author_role: str
    kind: str
    body: str
    url: str | None
    weight: float


def _course_norm(s: str) -> str:
    return s.upper().replace("COMPSCI", "CS").replace(" ", "").replace("-", "").split("/")[0]


def parse_piazza_email(subject: str, body: str, received_at: str | None = None) -> PiazzaInfo:
    subject = (subject or "").strip()
    body = body or ""
    course = None
    m = _COURSE_SUBJ.search(subject)
    if m:
        course = _course_norm(m.group(1))
    else:
        m = re.search(r"\b((?:CS|COMPSCI)\s?-?\d{3}[A-Z]?)\b", body, re.I)
        course = _course_norm(m.group(1)) if m else None
    m = _URL.search(body)
    url = m.group(0) if m else None
    post_id = m.group(2) if m and m.group(2) else None

    title = re.sub(r"^\[[^\]]*\]\s*", "", subject)
    title = re.sub(r"^(new (note|post|question|followup|answer)|instructor (note|answer)|update)[:\-\s]*", "", title, flags=re.I).strip() or subject

    head = f"{subject}\n{body[:600]}"
    if _INSTRUCTOR.search(head):
        role, weight = "instructor", 1.0
    elif _TA.search(head):
        role, weight = "ta", 0.8
    else:
        role, weight = "student", 0.3
    if re.search(r"\b(answer|answered|responded|response)\b", head, re.I):
        kind = "answer"
    elif re.search(r"\bfollow-?up\b", head, re.I):
        kind, weight = "followup", max(weight, 0.4)
    elif _ANNOUNCE.search(head):
        kind, weight = "note", max(weight, 0.8)
    elif re.search(r"\bquestion\b", head, re.I):
        kind = "question"
    else:
        kind = "note"
    if _SOCIAL.search(head):
        weight = 0.1
    return PiazzaInfo(course, post_id, title[:200], role, kind, body[:4000], url, weight)

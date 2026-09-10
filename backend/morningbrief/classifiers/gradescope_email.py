"""Parse Gradescope notification emails deterministically.

Kinds: submitted | grade_published | regrade | announcement | other
Grades are only recorded when they literally appear in the email.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..utils.html import slugify

_COURSE = re.compile(r"\b((?:CS|COMPSCI|CICS)\s?-?\d{3}[A-Z]?(?:/\d{3})?)\b", re.I)
_ASSIGN_SUBJ = [
    re.compile(r"(?:grade|grades) (?:for|on) (?:your submission to )?[\"“']?(.+?)[\"”']? (?:in|for|-) (.+?) (?:has|have|are|is) (?:been )?(?:released|published|posted)", re.I),
    re.compile(r"(?:your submission to|submission for|submitted to) [\"“']?(.+?)[\"”']? (?:in|for|-) (.+?)$", re.I),
    re.compile(r"\[(.+?)\]\s*(.+)", re.I),
]
_SCORE = re.compile(r"(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*(?:points|pts)?", re.I)
_URL = re.compile(r"https://www\.gradescope\.com/courses/\d+(?:/assignments/\d+(?:/submissions/\d+)?)?")


@dataclass
class GradescopeInfo:
    kind: str
    course: str | None
    assignment: str | None
    grade: str | None = None
    url: str | None = None
    summary: str = ""

    def slug(self) -> str:
        return slugify(self.assignment or "")


def _course_norm(s: str | None) -> str | None:
    if not s:
        return None
    m = _COURSE.search(s)
    if not m:
        return s.strip()[:40]
    c = m.group(1).upper().replace("COMPSCI", "CS").replace(" ", "").replace("-", "")
    return c.split("/")[0]


def parse_gradescope_email(subject: str, body: str) -> GradescopeInfo:
    subject = subject or ""
    text = f"{subject}\n{body or ''}"
    lower = text.lower()
    if re.search(r"regrade", lower):
        kind = "regrade"
    elif re.search(r"(grade|grades|score).{0,40}(released|published|posted|available)|graded submission|your grade", lower):
        kind = "grade_published"
    elif re.search(r"(submission (was )?received|successfully submitted|submitted to|thank you for (your )?submi)", lower):
        kind = "submitted"
    elif re.search(r"(announcement|posted a new|new assignment|has been (posted|released)|is now available)", lower):
        kind = "announcement"
    else:
        kind = "other"

    assignment = course = None
    for rx in _ASSIGN_SUBJ:
        m = rx.search(subject)
        if m:
            assignment, course = m.group(1).strip(), m.group(2).strip()
            break
    if not course:
        m = _COURSE.search(text)
        course = m.group(1) if m else None
    if not assignment:
        m = re.search(r"(?:assignment|submission)[:\s]+[\"“']?([A-Z][^\n\"”']{2,60})", body or "", re.I)
        assignment = m.group(1).strip() if m else None
        if not assignment:
            m = re.search(r"((?:Homework|HW|Problem Set|PSet|Project|Lab|Quiz|Exam|Midterm)\s?\d+[A-Za-z]?)", text, re.I)
            assignment = m.group(1) if m else None

    grade = None
    if kind == "grade_published":
        m = _SCORE.search(body or "")
        if m:
            grade = f"{m.group(1)}/{m.group(2)}"
    m = _URL.search(body or "")
    url = m.group(0) if m else None

    course_n = _course_norm(course)
    summary = {
        "grade_published": f"Grade released for {assignment or 'an assignment'}" + (f": {grade}" if grade else ""),
        "submitted": f"Submission received for {assignment or 'an assignment'}",
        "regrade": f"Regrade response for {assignment or 'an assignment'}",
        "announcement": f"Gradescope: {subject}",
        "other": f"Gradescope: {subject}",
    }[kind]
    return GradescopeInfo(kind, course_n, assignment, grade, url, summary)

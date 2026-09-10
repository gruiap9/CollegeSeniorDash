"""School email classification (UMass / course mail).

Roles: professor ta advisor registrar career_center financial admin automated announcement other
Importance: 0 ignore, 1 low, 2 notable, 3 important (shown in brief / notified).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..config import Config
from ..services import llm

ROLES = ["professor", "ta", "advisor", "registrar", "career_center", "financial", "admin", "automated", "announcement", "other"]

_UMASS = re.compile(r"@(?:[\w.-]+\.)?umass\.edu$", re.I)
_AUTOMATED_SENDER = re.compile(r"(no-?reply|do-?not-?reply|notification|mailer|bounce|newsletter|digest|listserv|announce)", re.I)
_ANNOUNCE = re.compile(r"\b(newsletter|weekly update|this week at|events? this week|reminder: campus|unsubscribe|"
                       r"opt out|view (this email )?in (your )?browser|calendar of events)\b", re.I)
_REGISTRAR = re.compile(r"\b(registrar|spire|enroll(ment)?|registration|add/drop|withdraw|transcript|degree audit|graduation)\b", re.I)
_ADVISOR = re.compile(r"\b(advis(or|ing)|appointment|degree progress|academic plan|major requirement)\b", re.I)
_CAREER = re.compile(r"\b(career (center|services|fair)|handshake|resume review|employer|info session)\b", re.I)
_FINANCIAL = re.compile(r"\b(bursar|tuition|bill(ing)?|financial aid|payment due|scholarship|fafsa|refund)\b", re.I)
_PROF_SIGNAL = re.compile(r"\b(professor|prof\.|instructor|lecture|office hours|class (today|tomorrow|is cancel)|"
                          r"exam|midterm|quiz|homework|problem set|pset|assignment|due date|deadline|extension|grade)\b", re.I)
_TA_SIGNAL = re.compile(r"\b(TA|teaching assistant|grader|discussion section|lab section)\b")
_URGENT = re.compile(r"\b(cancel+ed|moved|rescheduled|changed|extended|urgent|important|action required|"
                     r"deadline|due (today|tomorrow)|tonight|asap|immediately|last chance|final reminder)\b", re.I)

IGNORE_SENDERS = ("piazza.com", "gradescope.com", "instructure.com", "canvas")


@dataclass
class SchoolClassification:
    school_related: bool
    role: str = "other"
    importance: int = 1
    summary: str = ""
    course: str | None = None
    method: str = "rules"


def detect_course(text: str) -> str | None:
    m = re.search(r"\b(?:CS|COMPSCI|CICS|INFO|MATH|STAT)\s?-?(\d{3}[A-Z]?)\b", text, re.I)
    if m:
        prefix = m.group(0).split(m.group(1))[0].strip().upper().replace("COMPSCI", "CS").replace("-", "").replace(" ", "")
        return f"{prefix}{m.group(1).upper()}"
    return None


def rules(sender: str, sender_email: str, subject: str, body: str, known_people: dict[str, str] | None = None) -> SchoolClassification:
    known_people = known_people or {}
    email_l = (sender_email or "").lower()
    text = f"{subject}\n{body[:4000]}"
    course = detect_course(text)
    umass = bool(_UMASS.search(email_l))

    if any(s in email_l for s in IGNORE_SENDERS):
        return SchoolClassification(False, "automated", 0)
    if not umass and not course:
        return SchoolClassification(False, "other", 0)

    if email_l in known_people:
        role = known_people[email_l]
        imp = 3 if role in ("professor", "advisor") else 2
        if _URGENT.search(text):
            imp = 3
        return SchoolClassification(True, role, imp, course=course)

    if _AUTOMATED_SENDER.search(email_l) or _AUTOMATED_SENDER.search(sender or ""):
        return SchoolClassification(True, "automated", 0, course=course)
    if _ANNOUNCE.search(text):
        return SchoolClassification(True, "announcement", 0, course=course)
    if _FINANCIAL.search(text):
        return SchoolClassification(True, "financial", 2 if _URGENT.search(text) else 1, course=course)
    if _REGISTRAR.search(text):
        return SchoolClassification(True, "registrar", 2, course=course)
    if _ADVISOR.search(text):
        return SchoolClassification(True, "advisor", 3 if _URGENT.search(text) else 2, course=course)
    if _CAREER.search(text):
        return SchoolClassification(True, "career_center", 1, course=course)
    if _TA_SIGNAL.search(text) and course:
        return SchoolClassification(True, "ta", 2, course=course)
    if _PROF_SIGNAL.search(text) and (course or umass):
        return SchoolClassification(True, "professor", 3 if _URGENT.search(text) else 2, course=course)
    # Personal mail from a umass.edu address with no strong signal.
    return SchoolClassification(True, "other", 1, course=course, method="rules-weak")


_SCHEMA = {
    "type": "object",
    "properties": {
        "role": {"type": "string", "enum": ROLES},
        "importance": {"type": "integer", "minimum": 0, "maximum": 3},
        "summary": {"type": "string"},
        "course": {"type": ["string", "null"]},
    },
    "required": ["role", "importance", "summary", "course"],
    "additionalProperties": False,
}

_SYSTEM = (
    "You classify a university student's school email. Return only JSON. "
    "role: who the sender is acting as (professor, ta, advisor, registrar, career_center, financial, admin, "
    "automated, announcement, other). importance: 0 = ignore (newsletter/automated/marketing), 1 = low, "
    "2 = notable, 3 = important (a person addressing the student about something actionable or time-sensitive: "
    "changed office hours, deadlines, registration appointments, grades, meeting requests). "
    "summary: one short sentence stating the concrete point, e.g. 'Office hours moved to Thursday 2-4 PM.' "
    "course: course code like CS461 if identifiable, else null."
)


def classify(cfg: Config, sender: str, sender_email: str, subject: str, body: str, known_people: dict[str, str] | None = None) -> SchoolClassification:
    r = rules(sender, sender_email, subject, body, known_people)
    if not r.school_related or r.importance == 0:
        return r
    if not llm.available(cfg):
        return r
    out = llm.structured(
        cfg,
        system=_SYSTEM,
        user=f"From: {sender} <{sender_email}>\nSubject: {subject}\n\n{body[: cfg.llm_max_email_chars]}",
        schema=_SCHEMA,
        max_tokens=300,
    )
    if not out:
        return r
    return SchoolClassification(
        True,
        role=out.get("role") or r.role,
        importance=int(out.get("importance", r.importance)),
        summary=out.get("summary") or "",
        course=out.get("course") or r.course,
        method="llm",
    )

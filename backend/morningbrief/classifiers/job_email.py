"""Job-search email classification: deterministic rules first, LLM for ambiguous.

Output event vocabulary:
  APPLICATION_RECEIVED OA INTERVIEW RECRUITER NEXT_ROUND OFFER REJECTION JOB_OTHER
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..config import Config
from ..services import llm

JOB_EVENTS = ["APPLICATION_RECEIVED", "OA", "INTERVIEW", "RECRUITER", "NEXT_ROUND", "OFFER", "REJECTION", "JOB_OTHER"]

ATS_DOMAINS = (
    "greenhouse.io", "greenhouse-mail.io", "lever.co", "myworkday.com", "myworkdayjobs.com", "workday.com",
    "icims.com", "smartrecruiters.com", "ashbyhq.com", "jobvite.com", "taleo.net", "successfactors.com",
    "hackerrank.com", "codesignal.com", "hirevue.com", "karat.com", "wellfound.com", "handshake.com",
    "joinhandshake.com", "linkedin.com", "indeed.com", "brassring.com", "bamboohr.com", "rippling.com",
    "amazon.jobs", "recruiting.", "careers.", "talent.", "jobs.",
)

_JOB_HINTS = re.compile(
    r"\b(application|applied|candidate|recruit|interview|assessment|hiring|position|role|internship|"
    r"new grad|offer|opportunit|job|career|talent|resume|résumé)\b",
    re.I,
)
_OA = re.compile(r"\b(online assessment|coding assessment|technical assessment|hackerrank|codesignal|"
                 r"coding challenge|take-home|take home|assessment invitation|complete (your|the) assessment)\b", re.I)
_REJECT = re.compile(r"\b(unfortunately|not (be )?moving forward|other candidates|will not be (proceeding|moving)|"
                     r"decided to (pursue|move forward with) other|not selected|no longer (under )?consider|"
                     r"position has been filled|regret to inform|we have decided not to)\b", re.I)
_INTERVIEW = re.compile(r"\b(interview|phone screen|schedule (a|your) (call|conversation|chat)|availability for a call|"
                        r"onsite|on-site|virtual onsite|final round|hiring manager (call|conversation))\b", re.I)
_NEXT = re.compile(r"\b(next (step|round|stage)|moving forward (with|to)|advance(d)? to|congratulations.*(round|stage))\b", re.I)
_OFFER = re.compile(r"\b(offer letter|pleased to offer|extend (an|the) offer|job offer|offer of employment)\b", re.I)
_RECEIVED = re.compile(r"\b(thank you for (applying|your application|your interest)|application (has been )?(received|submitted)|"
                       r"we('ve| have) received your application|application confirmation|successfully (applied|submitted))\b", re.I)
_RECRUITER = re.compile(r"\b(reaching out|came across your (profile|resume)|would love to (chat|connect)|"
                        r"opportunity (at|with)|i'?m a (technical )?recruiter)\b", re.I)
_NEWSLETTER = re.compile(r"\b(unsubscribe|job alert|jobs? for you|recommended jobs|new jobs|daily digest|weekly digest|"
                         r"jobs matching|top job picks)\b", re.I)


@dataclass
class JobClassification:
    job_related: bool
    event: str = "JOB_OTHER"
    company: str | None = None
    confidence: float = 0.0
    summary: str = ""
    method: str = "rules"


def guess_company(sender: str, sender_email: str, subject: str) -> str | None:
    subj = subject or ""
    m = re.search(r"(?:at|from|with|@)\s+([A-Z][A-Za-z0-9&.\- ]{1,40}?)(?:[\s,.!:\-–]|$)", subj)
    if m:
        return m.group(1).strip()
    name = (sender or "").strip()
    for bad in ("recruiting", "talent", "careers", "team", "hiring", "no-reply", "noreply", "notifications", "do not reply"):
        name = re.sub(bad, "", name, flags=re.I)
    name = name.strip(" -|,@").strip()
    if name and not re.search(r"@|\d", name) and len(name) <= 40:
        return name
    dom = (sender_email or "").split("@")[-1]
    if dom and not any(a in dom for a in ATS_DOMAINS) and dom.count(".") >= 1:
        base = dom.split(".")[-2]
        return base.capitalize() if len(base) > 2 else None
    return None


def rules(sender: str, sender_email: str, subject: str, body: str) -> JobClassification:
    text = f"{subject}\n{body[:4000]}"
    dom = (sender_email or "").lower()
    ats = any(a in dom for a in ATS_DOMAINS)
    hints = len(_JOB_HINTS.findall(text))
    company = guess_company(sender, sender_email, subject)

    if not ats and hints == 0:
        return JobClassification(False, confidence=0.8)

    checks = [
        ("OFFER", _OFFER, 0.9),
        ("REJECTION", _REJECT, 0.85),
        ("OA", _OA, 0.85),
        ("NEXT_ROUND", _NEXT, 0.6),
        ("INTERVIEW", _INTERVIEW, 0.7),
        ("APPLICATION_RECEIVED", _RECEIVED, 0.85),
        ("RECRUITER", _RECRUITER, 0.55),
    ]
    hits = [(ev, conf) for ev, rx, conf in checks if rx.search(text)]
    newsletter = bool(_NEWSLETTER.search(text))
    if not hits:
        if newsletter:
            return JobClassification(False, confidence=0.7, summary="job newsletter / alert")
        return JobClassification(bool(ats or hints >= 2), "JOB_OTHER", company, 0.4 if ats else 0.3)
    # Rejection wording beats everything except a real offer.
    ev, conf = hits[0]
    if ev == "INTERVIEW" and any(h[0] == "REJECTION" for h in hits):
        ev, conf = "REJECTION", 0.8
    if len(hits) > 1 and ev not in ("OFFER", "REJECTION", "OA"):
        conf = min(conf, 0.55)
    return JobClassification(True, ev, company, conf, method="rules")


_SCHEMA = {
    "type": "object",
    "properties": {
        "job_related": {"type": "boolean"},
        "company": {"type": ["string", "null"]},
        "event": {"type": "string", "enum": JOB_EVENTS},
        "confidence": {"type": "number"},
        "summary": {"type": "string"},
    },
    "required": ["job_related", "company", "event", "confidence", "summary"],
    "additionalProperties": False,
}

_SYSTEM = (
    "You classify a student's job-search emails. Return only JSON. "
    "Event meanings: APPLICATION_RECEIVED (confirmation an application was submitted/received), "
    "OA (invitation to an online/coding assessment), INTERVIEW (scheduling or confirming an interview), "
    "RECRUITER (outreach from a recruiter about a role), NEXT_ROUND (advanced to a further stage), "
    "OFFER (a job offer), REJECTION (not moving forward), JOB_OTHER (job-related but none of these). "
    "Newsletters, job alerts and marketing are NOT job_related. Summary: one short sentence, second person."
)


def classify(cfg: Config, sender: str, sender_email: str, subject: str, body: str) -> JobClassification:
    r = rules(sender, sender_email, subject, body)
    if r.confidence >= 0.8 or not llm.available(cfg):
        return r
    if not r.job_related and r.confidence >= 0.6:
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
    return JobClassification(
        job_related=bool(out.get("job_related")),
        event=out.get("event") or "JOB_OTHER",
        company=out.get("company") or r.company,
        confidence=float(out.get("confidence") or 0.5),
        summary=out.get("summary") or "",
        method="llm",
    )

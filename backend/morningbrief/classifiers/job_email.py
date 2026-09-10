"""Job-search email classification: deterministic rules first, LLM for ambiguous.

Output event vocabulary:
  APPLICATION_RECEIVED OA INTERVIEW RECRUITER NEXT_ROUND OFFER REJECTION JOB_OTHER

Real ATS confirmation emails are messier than a first pass assumes:

- They routinely mention "interview"/"assessment" in HEDGED, forward-looking
  boilerplate ("you MAY be invited to an assessment", "IF you are not
  selected...", "selected candidates will move forward to the interview
  stage") describing a *possible future step*, not something that already
  happened. A bare keyword match can't tell "we scheduled your interview"
  from "if selected, you may be interviewed" or from a rejection's own
  "if you are not selected" boilerplate matching REJECTION's "not selected"
  phrase. `_HEDGE` + `_unhedged_hits()` filters these out.
- The actionable, factual statement ("thanks for applying", "we regret to
  inform you") is reliably near the very top of the email; the hedged
  "what happens next" language comes later. Matching is done in two passes —
  subject + a short lead-in first, the full body only if that finds nothing
  — so a late, hedged mention can't outrank an early, factual one.
- Real emails use typographic punctuation (curly quotes, em dashes) that a
  plain ASCII regex silently fails to match (e.g. "We've" with a curly
  apostrophe never matches a pattern written with a straight one). Text is
  normalized before any matching.
- The bare word "interview" appears constantly in non-job content (a music
  newsletter's "exclusive interview with the DJ", "tips on acing your
  interview" advice copy) — `_INTERVIEW` requires a possessive/scheduling
  phrase, not the bare word.
- LinkedIn's social digest emails ("X recently posted", "X shared a post:")
  quote OTHER PEOPLE's job news ("I accepted an offer at...") under the
  user's own inbox, from the same domain as LinkedIn's real job emails. These
  are excluded before any keyword matching runs.
"""

from __future__ import annotations

import re
import unicodedata
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

# Head-window size for pass 1 (chars of body, after the always-included
# subject). Tuned against real ATS templates: the factual "thanks for
# applying" / "we regret to inform you" statement is always well within this;
# the hedged "what happens next" section (where OA/INTERVIEW false-positives
# live) is reliably past it.
_HEAD_CHARS = 400


def _normalize(text: str) -> str:
    """Straight-quote typographic punctuation so ASCII regexes actually match
    real HTML-sourced email text (curly apostrophes/quotes, em/en dashes)."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    return (
        text.replace("‘", "'").replace("’", "'")
        .replace("“", '"').replace("”", '"')
        .replace("–", "-").replace("—", "-")
        .replace(" ", " ")
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
# Requires a possessive/scheduling phrase, not the bare word "interview" —
# that alone matches constantly in unrelated content (a music newsletter's
# "exclusive interview with the DJ", generic "tips on acing your interview"
# advice copy) and in hedged ATS boilerplate ("selected candidates will move
# forward to the interview stage").
_INTERVIEW = re.compile(
    r"\b(schedule (?:a|your) (?:interview|call|conversation|chat)|availability for a call|"
    r"interview invitation|interview request|invite you (?:to|for) (?:an? )?interview|"
    r"your interview (?:is |has been )?(?:scheduled|confirmed|set|booked)|"
    r"(?:phone|video|onsite|on-site|virtual) interview|"
    r"final round|hiring manager (?:call|conversation))\b",
    re.I,
)
_NEXT = re.compile(r"\b(next (step|round|stage)|moving forward (with|to)|advance(d)? to|congratulations.*(round|stage))\b", re.I)
_OFFER = re.compile(r"\b(offer letter|pleased to offer|extend (an|the) offer|job offer|offer of employment)\b", re.I)
_RECEIVED = re.compile(r"\b(thank(s| you) for (applying|your application|your interest)|"
                       r"application (has been )?(received|submitted)|"
                       r"we('ve| have) received your application|application confirmation|"
                       r"successfully (applied|submitted))\b", re.I)
_RECRUITER = re.compile(r"\b(reaching out|came across your (profile|resume)|would love to (chat|connect)|"
                        r"opportunity (at|with)|i'?m a (technical )?recruiter)\b", re.I)
_NEWSLETTER = re.compile(r"\b(unsubscribe|job alert|jobs? for you|recommended jobs|new jobs|daily digest|weekly digest|"
                         r"jobs matching|top job picks)\b", re.I)
# Account-verification / "here's the link to start an application" emails —
# these precede an actual application, they are not a received/submitted
# confirmation. Recognized deterministically (rather than left to the LLM
# fallback) because it's a common, well-defined ATS template, and an LLM
# asked to classify it was observed getting this wrong (calling it
# APPLICATION_RECEIVED even though nothing has been submitted yet).
_PRE_APPLICATION = re.compile(
    r"\b(verify(?:ing)? your (?:email|account)|confirm your email address|"
    r"complete (?:setup for )?your candidate account|start your (?:job )?application|"
    r"invited? to (?:start|begin) (?:your |an? )?application|"
    r"create(?:d)? your (?:career|candidate) account)\b",
    re.I,
)

# Forward-looking / conditional / advice language. A category match preceded
# closely by one of these describes a *possible* future step or general
# process, not something that has actually happened to this recipient.
# Note: `\bif\b` alone (not "if ... selected") — a preceding hedge phrase
# like REJECTION's own "not selected" match sits AFTER "if" in the source
# text, so the word that would follow "if" is already consumed by the
# category's own match and never appears in the context window we check.
_HEDGE = re.compile(
    r"\b(if|may|might|could|possibly|potentially|depending on|planned to|are planned|"
    r"selected candidates|some (?:roles|candidates|positions)|tips (?:on|for)|advice)\b",
    re.I,
)
# Generous enough for "If <clause>, <consequence>" sentences, where the
# conditional word can sit well before the actual verb phrase it hedges.
_HEDGE_WINDOW = 150
_HEDGED_CATEGORIES = {"OA", "INTERVIEW", "REJECTION", "NEXT_ROUND", "OFFER"}

# LinkedIn's social/network-digest template quotes OTHER PEOPLE's posts
# ("Sean Durkin shared a post: I accepted a job offer...") under the user's
# own address — that's someone else's news, not the recipient's.
_LINKEDIN_SOCIAL_NOISE = re.compile(r"\b(shared a post|recently posted|commented on|liked your)\b", re.I)


@dataclass
class JobClassification:
    job_related: bool
    event: str = "JOB_OTHER"
    company: str | None = None
    confidence: float = 0.0
    summary: str = ""
    method: str = "rules"


def _unhedged_match(category: str, rx: re.Pattern, text: str):
    """Return the first match of `rx` in `text` that isn't immediately
    preceded by hedging/conditional language, or None. Categories not in
    `_HEDGED_CATEGORIES` (RECEIVED, RECRUITER) are returned unhedged."""
    if category not in _HEDGED_CATEGORIES:
        return rx.search(text)
    for m in rx.finditer(text):
        context = text[max(0, m.start() - _HEDGE_WINDOW):m.start()]
        if not _HEDGE.search(context):
            return m
    return None


_CHECKS = [
    ("OFFER", _OFFER, 0.9),
    ("REJECTION", _REJECT, 0.85),
    ("OA", _OA, 0.85),
    ("NEXT_ROUND", _NEXT, 0.6),
    ("INTERVIEW", _INTERVIEW, 0.7),
    ("APPLICATION_RECEIVED", _RECEIVED, 0.85),
    ("RECRUITER", _RECRUITER, 0.55),
]


def _hits_in(text: str) -> list[tuple[str, float]]:
    return [(ev, conf) for ev, rx, conf in _CHECKS if _unhedged_match(ev, rx, text)]


# ------------------------------------------------------------- company name
_COMPANY_AT_FROM_WITH = re.compile(r"\b(?:at|from|with)\b\s+([A-Z][A-Za-z0-9&.\- ]{1,40}?)(?:[\s,.!:\-]|$)")
_COMPANY_SUBJECT_PATTERNS = [
    # Anchored to stop at the first sentence break (comma, period, "!", or
    # end of string) — NOT just end-of-string, since these phrases often sit
    # mid-sentence in a body ("Thanks for applying to GM, where we..."). A
    # broader "application to <X>" pattern was tried and dropped: it can't
    # distinguish a company ("...to Oscar!") from a role title ("...to Entry
    # Level Software Engineer is in!") using capitalization alone.
    re.compile(r"thank(?:s| you) for applying to ([A-Z][\w&.,'\- ]{1,50}?)(?:[!.,]|\s*$)", re.I),
    re.compile(r"thank(?:s| you) for (?:your application|applying) to ([A-Z][\w&.,'\- ]{1,50}?)(?:[!.,]|\s*$)", re.I),
    re.compile(r"successfully submitted your ([A-Z][\w&.,'\- ]{1,50}?) job application", re.I),
]
# Sender display names like "IBM Talent Acquisition" / "Amazon Recruiting Team"
# should strip the whole role phrase, not one word (leaving "IBM  Acquisition").
_BAD_NAME_PHRASES = (
    "talent acquisition", "early career talent", "recruiting team", "talent team",
    "hiring team", "careers team", "people team",
)
_BAD_NAME_WORDS = ("recruiting", "talent", "careers", "team", "hiring", "no-reply", "noreply", "notifications", "do not reply")


def _clean_subject(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def guess_company(sender: str, sender_email: str, subject: str, body: str = "") -> str | None:
    subject = _normalize(subject)
    body_head = _normalize(body)[:400]
    dom = (sender_email or "").lower().split("@")[-1]

    # 1. Reliable, specific ATS confirmation-template phrasings — tried
    #    against the subject and then the body's lead-in, since the company
    #    name is often stated in the body even when the subject omits it
    #    (e.g. a Workday subject naming only the role).
    for haystack in (subject, body_head):
        for rx in _COMPANY_SUBJECT_PATTERNS:
            m = rx.search(haystack)
            if m:
                return _clean_subject(m.group(1)).rstrip(" .,")

    # 2. Generic "<role> at <Company>" / "from <Company>" — word-boundaried
    #    so it can't match a substring inside an unrelated word (e.g. the
    #    "at" inside "Great" in "Great News!").
    for haystack in (subject, body_head):
        m = _COMPANY_AT_FROM_WITH.search(haystack)
        if m:
            return m.group(1).strip()

    # 3. Sender display name, with whole bad phrases stripped before
    #    individual bad words (so "IBM Talent Acquisition" -> "IBM", not
    #    "IBM  Acquisition").
    name = (sender or "").strip()
    for phrase in _BAD_NAME_PHRASES:
        name = re.sub(re.escape(phrase), "", name, flags=re.I)
    for bad in _BAD_NAME_WORDS:
        name = re.sub(rf"\b{bad}\b", "", name, flags=re.I)
    name = re.sub(r"\s+", " ", name).strip(" -|,@").strip()
    # A "display name" with no spaces that's actually a bare hostname (e.g. a
    # From: header with no friendly name at all, so this ends up being
    # "mail.amazon.jobs" or "fanduel.com") isn't a company name — fall
    # through to the Workday/domain fallbacks below for cleaner output.
    looks_like_hostname = bool(re.fullmatch(r"[\w-]+(?:\.[\w-]+)+", name or ""))
    if name and not looks_like_hostname and not re.search(r"@|\d", name) and len(name) <= 40:
        return name

    # 4. Workday puts the company as the literal local-part of the sending
    #    address (e.g. salesforce@myworkday.com, generalmotors@myworkday.com)
    #    — best-effort title-casing beats showing the raw address.
    if "myworkday.com" in dom or "myworkdayjobs.com" in dom:
        local = (sender_email or "").split("@")[0]
        if local and local.isalpha():
            return local.capitalize()

    # 5. A non-ATS-platform domain's second-level name (skip when it's a
    #    known shared platform — that names the platform, not the employer).
    if dom and not any(a in dom for a in ATS_DOMAINS) and dom.count(".") >= 1:
        base = dom.split(".")[-2]
        return base.capitalize() if len(base) > 2 else None
    return None


def rules(sender: str, sender_email: str, subject: str, body: str) -> JobClassification:
    subject = _normalize(subject)
    body = _normalize(body)
    dom = (sender_email or "").lower()
    ats = any(a in dom for a in ATS_DOMAINS)
    full_text = f"{subject}\n{body[:4000]}"
    company = guess_company(sender, sender_email, subject, body)

    # LinkedIn's social-network digest quotes other people's posts/news —
    # excluded outright, before any keyword matching, regardless of what
    # those quoted posts happen to say.
    if "linkedin.com" in dom and _LINKEDIN_SOCIAL_NOISE.search(f"{subject}\n{body[:300]}"):
        return JobClassification(False, confidence=0.9, summary="LinkedIn network activity, not your own job search")

    hints = len(_JOB_HINTS.findall(full_text))
    if not ats and hints == 0:
        return JobClassification(False, confidence=0.8)

    # Pass 1: subject + a short lead-in, where the factual "this already
    # happened" statement lives in real ATS templates. Pass 2 (full body)
    # only runs if pass 1 finds nothing, so a late hedged mention can't
    # outrank an early factual one it would otherwise tie with on priority.
    head_text = f"{subject}\n{body[:_HEAD_CHARS]}"
    hits = _hits_in(head_text) or _hits_in(full_text)

    newsletter = bool(_NEWSLETTER.search(full_text))
    if not hits:
        if newsletter:
            return JobClassification(False, confidence=0.7, summary="job newsletter / alert")
        if _PRE_APPLICATION.search(full_text):
            # Confidence >= the LLM-skip threshold in classify(): this template
            # is unambiguous enough that a second opinion isn't needed.
            return JobClassification(True, "JOB_OTHER", company, 0.8, summary="account/email verification — nothing submitted yet")
        return JobClassification(bool(ats or hints >= 2), "JOB_OTHER", company, 0.4 if ats else 0.3)
    ev, conf = hits[0]
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
    "Newsletters, job alerts and marketing are NOT job_related. A confirmation email describing possible "
    "FUTURE steps ('you may be invited to an assessment', 'selected candidates will interview') is "
    "APPLICATION_RECEIVED, not OA/INTERVIEW, unless it states something has actually been scheduled or is "
    "required now. A social-network digest quoting someone else's job news is not job_related. "
    "Summary: one short sentence, second person."
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

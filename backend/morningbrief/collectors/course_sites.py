"""Public course-website scrapers (CS520, CS461) with change detection.

Strategy: HTTP GET → BeautifulSoup → deterministic extraction of
assignments/deadlines/news → snapshot each logical section by hash →
diff against yesterday → events. No AI decides a deadline.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

import httpx

from ..config import Config, CourseSite
from ..db.database import Database
from ..db.models import Assignment
from ..db.repo import snapshot_section, upsert_assignment
from ..utils.dates import parse_due_text
from ..utils.html import normalize_ws, slugify, soup, stable_hash, text_of
from .base import CollectResult, Collector

log = logging.getLogger(__name__)
SOURCE = "course_sites"
UA = "MorningBrief/0.1 (personal course dashboard; contact: student)"

_DUE_RE = re.compile(r"\bdue\b[:\s]*(.+)", re.I)


@dataclass
class SiteData:
    course: str
    url: str
    sections: dict[str, str] = field(default_factory=dict)   # name -> text
    assignments: list[Assignment] = field(default_factory=list)
    news: list[dict] = field(default_factory=list)            # {text, url}


# ------------------------------------------------------------------ CS520
def parse_cs520(course: str, url: str, html: str) -> SiteData:
    s = soup(html)
    data = SiteData(course, url)

    news_h = s.find(id="news")
    if news_h:
        ul = news_h.find_next("ul")
        items = []
        for li in ul.find_all("li", recursive=False) if ul else []:
            t = text_of(li)
            if not t:
                continue
            a = li.find("a", href=True)
            items.append({"text": t, "url": urljoin(url, a["href"]) if a else url + "#news"})
        data.news = items
        data.sections["news"] = "\n".join(i["text"] for i in items)

    sched_h = s.find(id="schedule")
    table = sched_h.find_next("table") if sched_h else None
    if table:
        rows_text = []
        for tr in table.find_all("tr"):
            cells = [text_of(td) for td in tr.find_all(["td", "th"])]
            rows_text.append(" | ".join(c for c in cells if c))
            for td in tr.find_all("td"):
                t = text_of(td)
                m = _DUE_RE.search(t)
                if not m:
                    continue
                title = normalize_ws(t[: m.start()]).strip(" :-")
                due = parse_due_text(m.group(1))
                if not title:
                    continue
                a = td.find("a", href=True)
                kind = "project" if "project" in title.lower() else "homework"
                data.assignments.append(Assignment(
                    source="cs520", course=course, assignment_id=slugify(title), title=title, due_date=due,
                    url=urljoin(url, a["href"]) if a else url + "#schedule",
                    raw={"kind": kind, "due_text": m.group(1)},
                ))
        data.sections["schedule"] = "\n".join(rows_text)

    # Also catch "Homework 1 is posted! Due: ..." in news.
    for item in data.news:
        m = _DUE_RE.search(item["text"])
        mt = re.search(r"((?:Homework|HW|Project|In-class exercise|Extra credit)[^.!,]*?\d*)", item["text"], re.I)
        if m and mt:
            title = normalize_ws(mt.group(1))
            data.assignments.append(Assignment(source="cs520", course=course, assignment_id=slugify(title), title=title,
                                               due_date=parse_due_text(m.group(1)), url=item["url"], raw={"from": "news"}))
    for h in s.find_all("h3"):
        name = slugify(text_of(h))
        if name in ("news", "schedule") or not name:
            continue
        body = []
        for sib in h.find_next_siblings():
            if sib.name in ("h3", "h2", "hr"):
                break
            body.append(text_of(sib))
        data.sections[name] = "\n".join(b for b in body if b)
    return data


# ------------------------------------------------------------------ CS461
def parse_cs461(course: str, url: str, html: str) -> SiteData:
    s = soup(html)
    data = SiteData(course, url)
    content = s.find(class_="wikicontent") or s
    current = "top"
    buf: dict[str, list[str]] = {current: []}
    for el in content.children:
        if getattr(el, "name", None) in ("h1", "h2", "h3", "h4", "h5"):
            current = slugify(text_of(el)) or current
            buf.setdefault(current, [])
            continue
        t = text_of(el) if getattr(el, "name", None) else normalize_ws(str(el))
        if t:
            buf[current].append(t)
    for name, lines in buf.items():
        data.sections[name] = "\n".join(lines)

    # Deadlines: any line with "due" and a parseable date.
    for el in content.find_all(["li", "p", "td", "strong"]):
        t = text_of(el)
        m = _DUE_RE.search(t)
        if not m:
            continue
        due = parse_due_text(m.group(1))
        if not due:
            continue
        title = normalize_ws(t[: m.start()]).strip(" :-–")
        if not title or len(title) > 120:
            mt = re.search(r"((?:Homework|HW|Assignment|Project|Quiz|Lab|Problem Set|PSet)\s?\d+[A-Za-z]?)", t, re.I)
            title = mt.group(1) if mt else title[:80]
        if not title:
            continue
        a = el.find("a", href=True)
        data.assignments.append(Assignment(source="cs461", course=course, assignment_id=slugify(title), title=title,
                                           due_date=due, url=urljoin(url, a["href"]) if a else url,
                                           raw={"due_text": m.group(1)}))
    # Exam lines are worth surfacing as news when they change.
    for el in content.find_all("strong"):
        t = text_of(el)
        if re.match(r"(midterm|final)\b", t, re.I):
            data.news.append({"text": t, "url": url})
    data.sections["exams"] = "\n".join(n["text"] for n in data.news)
    return data


def parse_generic(course: str, url: str, html: str) -> SiteData:
    s = soup(html)
    data = SiteData(course, url)
    data.sections["page"] = text_of(s.body or s)
    return data


PARSERS = {"cs520": parse_cs520, "cs461": parse_cs461, "generic": parse_generic}


def fetch(url: str) -> str:
    with httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": UA}) as c:
        r = c.get(url)
        r.raise_for_status()
        return r.text


def ingest(db: Database, site: CourseSite, data: SiteData, res: CollectResult, page_label: str = "") -> None:
    prefix = f"{page_label}:" if page_label else ""
    for name, content in data.sections.items():
        if not content.strip():
            continue
        r = snapshot_section(db, site.course, prefix + name, content, stable_hash(content))
        if r["changed"]:
            added = _diff_lines(r["old"] or "", content)
            detail = " / ".join(added)[:400] if added else "Section content changed"
            db.add_event("site.changed", f"{site.course} site: {name.replace('-', ' ')} updated", detail=detail,
                         url=data.url, source=site.parser, course=site.course,
                         importance=2 if name in ("news", "schedule", "exams") else 1,
                         dedupe_key=f"site:{site.course}:{prefix}{name}:{stable_hash(content)}")
            res.events += 1
            res.updated += 1
    seen = set()
    for a in data.assignments:
        if a.assignment_id in seen:
            continue
        seen.add(a.assignment_id)
        r = upsert_assignment(db, a)
        if r["new"]:
            res.new += 1
        # due-date changes are handled by change_detector using the returned changes
        if r["changes"].get("due_date"):
            old, new = r["changes"]["due_date"]
            db.add_event("assignment.due_changed", f"{site.course} — {a.title} deadline changed",
                         detail=f"{old} → {new}", url=a.url, source=a.source, course=site.course, importance=3,
                         dedupe_key=f"due:{a.source}:{site.course}:{a.assignment_id}:{new}")
            res.events += 1


def _diff_lines(old: str, new: str) -> list[str]:
    o = set(l.strip() for l in old.splitlines())
    return [l.strip() for l in new.splitlines() if l.strip() and l.strip() not in o][:5]


class CourseSiteCollector(Collector):
    name = SOURCE

    def enabled(self, cfg: Config) -> bool:
        return bool(cfg.course_sites)

    def collect(self, cfg: Config, db: Database) -> CollectResult:
        res = CollectResult(SOURCE)
        for site in cfg.course_sites:
            parser = PARSERS.get(site.parser, parse_generic)
            try:
                data = parser(site.course, site.url, fetch(site.url))
                ingest(db, site, data, res)
                for extra in site.extra_urls:
                    d2 = parser(site.course, extra, fetch(extra))
                    ingest(db, site, d2, res, page_label=slugify(extra.rsplit("/", 1)[-1]))
                res.notes.append(f"{site.course}:{len(data.assignments)} deadlines")
            except Exception as e:
                log.exception("site %s failed", site.course)
                res.notes.append(f"{site.course}: ERROR {e!r}")
        return res

"""Tech-news collector from a fixed RSS/Atom feed set (no open-web browsing)."""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone
from time import mktime
from urllib.parse import urlsplit, urlunsplit

import feedparser
import httpx

from ..config import Config
from ..db.database import Database
from ..db.models import Article
from ..db.repo import upsert_article
from ..utils.html import html_to_text
from .base import CollectResult, Collector

log = logging.getLogger(__name__)
SOURCE = "news"
UA = "MorningBrief/0.1 (+personal RSS reader)"


def canonical_url(url: str) -> str:
    p = urlsplit(url or "")
    q = "&".join(kv for kv in p.query.split("&") if kv and not kv.lower().startswith(("utm_", "ref=", "source=", "fbclid")))
    return urlunsplit((p.scheme, p.netloc.lower(), p.path.rstrip("/"), q, ""))


def article_id(url: str) -> str:
    return hashlib.sha1(canonical_url(url).encode()).hexdigest()[:20]


def parse_feed(name: str, weight: float, content: bytes | str, cutoff: datetime) -> list[Article]:
    fp = feedparser.parse(content)
    out = []
    for e in fp.entries:
        link = e.get("link") or ""
        if not link:
            continue
        ts = e.get("published_parsed") or e.get("updated_parsed")
        published = datetime.fromtimestamp(mktime(ts), tz=timezone.utc) if ts else None
        if published and published < cutoff:
            continue
        summary = e.get("summary") or (e.get("content") or [{}])[0].get("value", "") or ""
        summary = re.sub(r"\s+", " ", html_to_text(summary))[:1000]
        out.append(Article(article_id=article_id(link), source=name, title=re.sub(r"\s+", " ", e.get("title", "")).strip(),
                           url=link, published_at=published.isoformat() if published else None, summary=summary, source_weight=weight))
    return out


class NewsCollector(Collector):
    name = SOURCE

    def enabled(self, cfg: Config) -> bool:
        return cfg.news_enabled and bool(cfg.news_feeds)

    def collect(self, cfg: Config, db: Database) -> CollectResult:
        res = CollectResult(SOURCE)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=36)
        with httpx.Client(timeout=20, follow_redirects=True, headers={"User-Agent": UA}) as c:
            for feed in cfg.news_feeds:
                try:
                    r = c.get(feed["url"])
                    r.raise_for_status()
                    arts = parse_feed(feed["name"], float(feed.get("weight", 0.5)), r.content, cutoff)
                    res.new += sum(1 for a in arts if upsert_article(db, a))
                except Exception as e:
                    log.warning("feed %s failed: %s", feed["name"], e)
                    res.notes.append(f"{feed['name']}: {type(e).__name__}")
        # prune old articles
        db.conn.execute("DELETE FROM news WHERE first_seen < ?", ((datetime.now(timezone.utc) - timedelta(days=14)).isoformat(),))
        db.conn.commit()
        return res

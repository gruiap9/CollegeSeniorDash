"""Piazza collector.

Version 1 is email-based: Piazza notification emails are parsed by the email
pipeline (see classifiers/piazza_email.py). This collector only prunes old
posts. Direct (authenticated) Piazza access is intentionally not implemented:
it would require storing your Piazza password, which this project avoids.
Enable per-post/instant email notifications in Piazza settings for best results.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..config import Config
from ..db.database import Database
from .base import CollectResult, Collector

SOURCE = "piazza"


class PiazzaCollector(Collector):
    name = SOURCE

    def enabled(self, cfg: Config) -> bool:
        return True

    def collect(self, cfg: Config, db: Database) -> CollectResult:
        res = CollectResult(SOURCE)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        cur = db.conn.execute("DELETE FROM piazza_posts WHERE first_seen < ?", (cutoff,))
        db.conn.commit()
        res.notes.append(f"email-based; pruned {cur.rowcount}")
        return res

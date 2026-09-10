"""SQLite access layer.

One connection per process; WAL mode; schema created/migrated on open.
All timestamps are stored as ISO-8601 UTC strings.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from ..config import db_path

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- Per-source sync bookkeeping (cursors, last success).
CREATE TABLE IF NOT EXISTS sync_state (
    source        TEXT PRIMARY KEY,
    cursor        TEXT,
    last_success  TEXT,
    last_error    TEXT,
    last_attempt  TEXT
);

CREATE TABLE IF NOT EXISTS assignments (
    id            INTEGER PRIMARY KEY,
    source        TEXT NOT NULL,          -- canvas | cs520 | cs461 | gradescope
    course        TEXT NOT NULL,
    assignment_id TEXT NOT NULL,          -- source-native id (or stable slug)
    title         TEXT NOT NULL,
    due_date      TEXT,                   -- ISO UTC or NULL
    status        TEXT,                   -- unsubmitted | submitted | graded | unknown
    grade         TEXT,
    points_possible REAL,
    url           TEXT,
    raw           TEXT,                   -- JSON blob of source record
    first_seen    TEXT NOT NULL,
    last_seen     TEXT NOT NULL,
    updated_at    TEXT,
    UNIQUE(source, course, assignment_id)
);

CREATE TABLE IF NOT EXISTS emails (
    id           INTEGER PRIMARY KEY,
    message_id   TEXT NOT NULL,
    account      TEXT NOT NULL,           -- gmail | outlook
    thread_id    TEXT,
    sender       TEXT,
    sender_email TEXT,
    subject      TEXT,
    snippet      TEXT,
    body         TEXT,
    received_at  TEXT,
    url          TEXT,
    category     TEXT,                    -- job | school | gradescope | piazza | other
    company      TEXT,
    job_status   TEXT,                    -- APPLICATION_RECEIVED | OA | INTERVIEW | ...
    school_role  TEXT,                    -- professor | ta | advisor | registrar | ...
    importance   INTEGER DEFAULT 0,       -- 0..3
    summary      TEXT,
    classified_at TEXT,
    created_at   TEXT NOT NULL,
    UNIQUE(account, message_id)
);

CREATE TABLE IF NOT EXISTS piazza_posts (
    id          INTEGER PRIMARY KEY,
    course      TEXT NOT NULL,
    post_id     TEXT NOT NULL,
    title       TEXT,
    author_role TEXT,                     -- instructor | ta | student | unknown
    kind        TEXT,                     -- note | question | followup | answer
    created_at  TEXT,
    updated_at  TEXT,
    body        TEXT,
    summary     TEXT,
    url         TEXT,
    weight      REAL DEFAULT 0,
    first_seen  TEXT NOT NULL,
    UNIQUE(course, post_id)
);

CREATE TABLE IF NOT EXISTS news (
    id           INTEGER PRIMARY KEY,
    article_id   TEXT NOT NULL UNIQUE,    -- hash of canonical url
    source       TEXT,
    title        TEXT,
    published_at TEXT,
    url          TEXT,
    summary      TEXT,
    cluster_id   TEXT,
    importance   REAL DEFAULT 0,
    first_seen   TEXT NOT NULL
);

-- Snapshots of course-site sections for change detection.
CREATE TABLE IF NOT EXISTS page_sections (
    id          INTEGER PRIMARY KEY,
    course      TEXT NOT NULL,
    section     TEXT NOT NULL,            -- e.g. "news", "schedule", "week-3"
    content     TEXT,
    hash        TEXT NOT NULL,
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL,
    UNIQUE(course, section)
);

-- Everything notable that happened, in one timeline. This feeds
-- "SINCE YESTERDAY" and notifications.
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY,
    created_at  TEXT NOT NULL,
    kind        TEXT NOT NULL,            -- job.oa | job.rejection | assignment.new | assignment.due_changed | grade.new | email.important | piazza.instructor | site.changed ...
    source      TEXT,
    course      TEXT,
    title       TEXT NOT NULL,
    detail      TEXT,
    url         TEXT,
    importance  INTEGER DEFAULT 1,        -- 0 low .. 3 critical
    dedupe_key  TEXT UNIQUE,
    notified_at TEXT,
    shown_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at);
CREATE INDEX IF NOT EXISTS idx_emails_received ON emails(received_at);
CREATE INDEX IF NOT EXISTS idx_assignments_due ON assignments(due_date);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Database:
    def __init__(self, path: Path | None = None):
        self.path = path or db_path()
        self.conn = sqlite3.connect(str(self.path), detect_types=0)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    # -- lifecycle -----------------------------------------------------
    def _migrate(self) -> None:
        self.conn.executescript(SCHEMA)
        cur = self.get_meta("schema_version")
        if cur is None:
            self.set_meta("schema_version", str(SCHEMA_VERSION))
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    # -- meta ----------------------------------------------------------
    def get_meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self.conn.commit()

    # -- sync state ----------------------------------------------------
    def get_sync(self, source: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM sync_state WHERE source=?", (source,)).fetchone()

    def mark_sync_attempt(self, source: str) -> None:
        self.conn.execute(
            "INSERT INTO sync_state(source,last_attempt) VALUES(?,?) "
            "ON CONFLICT(source) DO UPDATE SET last_attempt=excluded.last_attempt",
            (source, utcnow()),
        )
        self.conn.commit()

    def mark_sync_success(self, source: str, cursor: str | None = None) -> None:
        self.conn.execute(
            "INSERT INTO sync_state(source,cursor,last_success,last_error) VALUES(?,?,?,NULL) "
            "ON CONFLICT(source) DO UPDATE SET cursor=COALESCE(excluded.cursor, sync_state.cursor), "
            "last_success=excluded.last_success, last_error=NULL",
            (source, cursor, utcnow()),
        )
        self.conn.commit()

    def mark_sync_error(self, source: str, error: str) -> None:
        self.conn.execute(
            "INSERT INTO sync_state(source,last_error) VALUES(?,?) "
            "ON CONFLICT(source) DO UPDATE SET last_error=excluded.last_error",
            (source, error[:2000]),
        )
        self.conn.commit()

    # -- events --------------------------------------------------------
    def add_event(
        self,
        kind: str,
        title: str,
        *,
        detail: str | None = None,
        url: str | None = None,
        source: str | None = None,
        course: str | None = None,
        importance: int = 1,
        dedupe_key: str | None = None,
    ) -> bool:
        """Insert an event; returns False if dedupe_key already exists."""
        try:
            self.conn.execute(
                "INSERT INTO events(created_at,kind,source,course,title,detail,url,importance,dedupe_key) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (utcnow(), kind, source, course, title, detail, url, importance, dedupe_key),
            )
        except sqlite3.IntegrityError:
            return False
        self.conn.commit()
        return True

    def events_since(self, iso: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM events WHERE created_at >= ? ORDER BY importance DESC, created_at DESC",
            (iso,),
        ).fetchall()

    # -- generic helpers -----------------------------------------------
    def rows(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def row(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        r = self.conn.execute(sql, params).fetchone()
        return dict(r) if r else None

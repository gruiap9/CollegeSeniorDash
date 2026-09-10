"""Plain dataclasses used to pass normalized records between collectors and the DB."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Assignment:
    source: str
    course: str
    assignment_id: str
    title: str
    due_date: str | None = None  # ISO UTC
    status: str | None = None
    grade: str | None = None
    points_possible: float | None = None
    url: str | None = None
    updated_at: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def raw_json(self) -> str:
        return json.dumps(self.raw, default=str, sort_keys=True)


@dataclass
class Email:
    message_id: str
    account: str
    sender: str
    sender_email: str
    subject: str
    received_at: str | None
    snippet: str = ""
    body: str = ""
    thread_id: str | None = None
    url: str | None = None


@dataclass
class PiazzaPost:
    course: str
    post_id: str
    title: str
    author_role: str = "unknown"
    kind: str = "note"
    created_at: str | None = None
    updated_at: str | None = None
    body: str = ""
    url: str | None = None


@dataclass
class Article:
    article_id: str
    source: str
    title: str
    url: str
    published_at: str | None
    summary: str = ""
    source_weight: float = 0.5


def to_dict(obj: Any) -> dict[str, Any]:
    return asdict(obj)

"""Configuration and on-disk layout.

Everything lives under ~/Library/Application Support/MorningBrief/ by default.
Secrets are NOT stored here; see `morningbrief.secrets` (macOS Keychain).

Set MORNINGBRIEF_HOME to relocate the data directory (used by tests).
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

APP_NAME = "MorningBrief"


def data_dir() -> Path:
    override = os.environ.get("MORNINGBRIEF_HOME")
    if override:
        p = Path(override).expanduser()
    else:
        p = Path.home() / "Library" / "Application Support" / APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def db_path() -> Path:
    return data_dir() / "morningbrief.db"


def config_path() -> Path:
    return data_dir() / "config.json"


def brief_path() -> Path:
    return data_dir() / "morning_brief.json"


def log_dir() -> Path:
    p = data_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


@dataclass
class CourseSite:
    """A public course website to scrape."""

    course: str
    url: str
    parser: str  # "cs520" | "cs461" | "generic"
    extra_urls: list[str] = field(default_factory=list)
    # Public pages only. If the site's TLS certificate is broken (compscix61.org
    # has served an expired one), retry without verification and log a warning.
    allow_insecure_ssl: bool = False


@dataclass
class Config:
    timezone: str = "America/New_York"
    user_name: str = ""

    # Accounts
    gmail_enabled: bool = False
    gmail_client_secret_file: str = ""  # path to Google OAuth client JSON (kept outside repo)
    outlook_enabled: bool = False
    outlook_client_id: str = ""  # Azure app registration (public client) id
    outlook_tenant: str = "common"

    # Canvas
    canvas_enabled: bool = False
    canvas_base_url: str = "https://umass.instructure.com"

    # Course sites
    course_sites: list[CourseSite] = field(
        default_factory=lambda: [
            CourseSite(
                course="CS520",
                url="https://people.cs.umass.edu/~brun/class/2026Fall/CS520/",
                parser="cs520",
            ),
            CourseSite(
                course="CS461",
                url="https://compscix61.org/",
                parser="cs461",
                extra_urls=["https://compscix61.org/courseCalendar.md"],
                allow_insecure_ssl=True,
            ),
        ]
    )

    # Piazza (email-based by default; network access is opt-in)
    piazza_enabled: bool = False
    piazza_courses: dict[str, str] = field(default_factory=dict)  # course -> network id

    # News
    news_enabled: bool = True
    news_feeds: list[dict[str, Any]] = field(
        default_factory=lambda: [
            {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/technology-lab", "weight": 0.9},
            {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "weight": 0.8},
            {"name": "TechCrunch", "url": "https://techcrunch.com/feed/", "weight": 0.8},
            {"name": "Hacker News", "url": "https://hnrss.org/frontpage?points=150", "weight": 0.9},
            {"name": "OpenAI", "url": "https://openai.com/news/rss.xml", "weight": 1.0},
            {"name": "Google Blog", "url": "https://blog.google/rss/", "weight": 0.7},
            {"name": "Microsoft", "url": "https://blogs.microsoft.com/feed/", "weight": 0.6},
            {"name": "Meta Engineering", "url": "https://engineering.fb.com/feed/", "weight": 0.6},
            {"name": "Apple Newsroom", "url": "https://www.apple.com/newsroom/rss-feed.rss", "weight": 0.7},
            {"name": "NVIDIA", "url": "https://blogs.nvidia.com/feed/", "weight": 0.7},
            {"name": "GitHub Blog", "url": "https://github.blog/feed/", "weight": 0.7},
        ]
    )
    news_max_items: int = 5

    # LLM
    llm_enabled: bool = True
    llm_model: str = "claude-haiku-4-5"  # routine classification/summaries; configurable
    llm_max_email_chars: int = 6000

    # Behaviour
    sync_interval_minutes: int = 30
    notify_enabled: bool = True

    @staticmethod
    def load() -> "Config":
        p = config_path()
        if not p.exists():
            cfg = Config()
            cfg.save()
            return cfg
        raw = json.loads(p.read_text())
        sites = [CourseSite(**s) for s in raw.pop("course_sites", [])]
        cfg = Config(**{k: v for k, v in raw.items() if k in Config.__dataclass_fields__})
        if sites:
            cfg.course_sites = sites
        return cfg

    def save(self) -> None:
        config_path().write_text(json.dumps(asdict(self), indent=2) + "\n")

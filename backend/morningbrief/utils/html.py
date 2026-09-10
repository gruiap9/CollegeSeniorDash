"""HTML helpers: text extraction, hashing, section splitting."""

from __future__ import annotations

import hashlib
import re

from bs4 import BeautifulSoup, Comment


def soup(html: str) -> BeautifulSoup:
    s = BeautifulSoup(html, "lxml")
    for c in s.find_all(string=lambda t: isinstance(t, Comment)):
        c.extract()
    for tag in s(["script", "style", "noscript"]):
        tag.decompose()
    return s


def text_of(node) -> str:
    if node is None:
        return ""
    t = node.get_text(" ", strip=True)
    return normalize_ws(t)


def normalize_ws(t: str) -> str:
    return re.sub(r"\s+", " ", t or "").strip()


def stable_hash(text: str) -> str:
    return hashlib.sha256(normalize_ws(text).encode("utf-8")).hexdigest()[:24]


_BLOCK_END = re.compile(r"</(p|div|li|tr|h[1-6]|blockquote|pre|table)>|<br\s*/?>", re.I)


def html_to_text(html: str) -> str:
    """Block-level tags become newlines; inline tags do not split words."""
    html = _BLOCK_END.sub(lambda m: m.group(0) + "\n", html or "")
    s = BeautifulSoup(html, "lxml")
    for tag in s(["script", "style"]):
        tag.decompose()
    text = s.get_text("")
    text = "\n".join(line.strip() for line in text.splitlines())
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def slugify(t: str) -> str:
    t = re.sub(r"[^a-z0-9]+", "-", (t or "").lower()).strip("-")
    return t[:80] or "item"

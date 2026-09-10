"""Rank and summarize recent tech news. Dedupe near-identical headlines, then
score significance × CS/AI relevance × source quality × freshness. The LLM
(optional) writes one-line summaries and can re-rank the shortlist.
"""

from __future__ import annotations

import re
from datetime import timedelta

from ..config import Config
from ..db.database import Database
from ..services import llm
from ..utils.dates import from_iso, now_local

_RELEVANT = re.compile(
    r"\b(ai|llm|gpt|claude|gemini|openai|anthropic|nvidia|gpu|chip|apple|google|microsoft|meta|amazon|aws|github|"
    r"python|rust|linux|kernel|open[- ]source|security|breach|vulnerab|model|agent|robot|startup|acqui|launch|release|"
    r"compiler|database|cloud|kubernetes|swift|ios|macos|android|quantum|semiconductor|tsmc|intel|amd|arm)\b",
    re.I,
)
_STOP = set("a an the of to in on for and or with by from at is are new says its it as vs into over after amid".split())


def _tokens(title: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", title.lower()) if w not in _STOP and len(w) > 2}


def cluster(articles: list[dict]) -> list[list[dict]]:
    clusters: list[tuple[set[str], list[dict]]] = []
    for a in articles:
        toks = _tokens(a["title"])
        for ctoks, members in clusters:
            inter = len(toks & ctoks)
            if inter >= 3 and inter / max(1, min(len(toks), len(ctoks))) >= 0.5:
                members.append(a)
                ctoks |= toks
                break
        else:
            clusters.append((set(toks), [a]))
    return [m for _, m in clusters]


def score(cluster_members: list[dict], weights: dict[str, float], now) -> float:
    best = max(cluster_members, key=lambda a: weights.get(a["source"], 0.5))
    src_q = weights.get(best["source"], 0.5)
    rel = min(1.0, 0.4 + 0.2 * len(_RELEVANT.findall(best["title"] + " " + (best["summary"] or "")[:300])))
    pub = from_iso(best["published_at"])
    age_h = ((now - pub.astimezone(now.tzinfo)).total_seconds() / 3600) if pub else 24
    fresh = max(0.2, 1.0 - age_h / 48)
    coverage = min(1.0, 0.5 + 0.25 * (len(cluster_members) - 1))
    return src_q * rel * fresh * coverage


_SCHEMA = {
    "type": "object",
    "properties": {
        "stories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"index": {"type": "integer"}, "headline": {"type": "string"}, "summary": {"type": "string"}},
                "required": ["index", "headline", "summary"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["stories"],
    "additionalProperties": False,
}
_SYSTEM = (
    "You pick and summarize the top technology stories for a CS senior interested in AI, software engineering and the "
    "big tech companies. Return only JSON. Choose the N most significant distinct stories from the candidates, ordered by "
    "significance, using the given index numbers. headline: concise; summary: one sentence of concrete facts from the "
    "candidate text only."
)


def top_stories(cfg: Config, db: Database, since_iso: str) -> list[dict]:
    now = now_local()
    rows = db.rows("SELECT * FROM news WHERE COALESCE(published_at, first_seen) >= ? ORDER BY published_at DESC LIMIT 400", (since_iso,))
    if not rows:
        return []
    weights = {f["name"]: float(f.get("weight", 0.5)) for f in cfg.news_feeds}
    clusters = cluster(rows)
    ranked = sorted(clusters, key=lambda c: score(c, weights, now), reverse=True)[: max(cfg.news_max_items * 3, 12)]
    candidates = []
    for members in ranked:
        best = max(members, key=lambda a: weights.get(a["source"], 0.5))
        candidates.append({"title": best["title"], "source": best["source"], "url": best["url"], "summary": (best["summary"] or "")[:400],
                           "published_at": best["published_at"], "sources": sorted({m["source"] for m in members})})
    n = cfg.news_max_items
    if llm.available(cfg):
        corpus = "\n\n".join(f"[{i}] {c['title']} ({', '.join(c['sources'])})\n{c['summary']}" for i, c in enumerate(candidates))
        out = llm.structured(cfg, system=_SYSTEM, user=f"N={n}\n\n{corpus}", schema=_SCHEMA, max_tokens=900)
        if out and out.get("stories"):
            picked = []
            for s in out["stories"][:n]:
                i = s.get("index")
                if isinstance(i, int) and 0 <= i < len(candidates):
                    c = candidates[i]
                    picked.append({"rank": len(picked) + 1, "title": s.get("headline") or c["title"], "summary": s.get("summary") or c["summary"],
                                   "source": c["source"], "sources": c["sources"], "url": c["url"], "published_at": c["published_at"]})
            if picked:
                return picked
    return [{"rank": i + 1, "title": c["title"], "summary": _first_sentence(c["summary"]), "source": c["source"], "sources": c["sources"],
             "url": c["url"], "published_at": c["published_at"]} for i, c in enumerate(candidates[:n])]


def _first_sentence(t: str) -> str:
    t = re.sub(r"\s+", " ", t or "").strip()
    m = re.match(r"(.{20,220}?[.!?])(\s|$)", t)
    return m.group(1) if m else t[:200]

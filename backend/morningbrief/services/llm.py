"""Thin wrapper that returns structured JSON from an LLM.

Two providers are supported, selected by `cfg.llm_provider`: "anthropic"
(default) and "gemini". Both are used only for routine classification and
summarization — never as the source of truth for grades, due dates, senders
or times (see the individual classifiers/summarizers). If no API key is
present for the selected provider, `available()` is False and callers fall
back to deterministic rules.
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
import time
from typing import Any

from .. import secrets
from ..config import Config

log = logging.getLogger(__name__)

_anthropic_client = None
_gemini_client = None

# If the provider rate-limits us mid-sync, stop hammering it for the rest of
# this process instead of retrying per-email (a sync can touch dozens of
# emails; free-tier quotas on newer models can be as low as a few per minute).
_gemini_cooldown_until = 0.0
DEFAULT_COOLDOWN_SECONDS = 60.0


# ---------------------------------------------------------------- Anthropic
def _anthropic_api_key() -> str | None:
    return os.environ.get("ANTHROPIC_API_KEY") or secrets.get_secret(secrets.ANTHROPIC_API_KEY)


def _get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic

        _anthropic_client = anthropic.Anthropic(api_key=_anthropic_api_key(), max_retries=2, timeout=60.0)
    return _anthropic_client


def _structured_anthropic(cfg: Config, system: str, user: str, schema: dict[str, Any], max_tokens: int) -> dict[str, Any] | None:
    client = _get_anthropic_client()
    resp = client.messages.create(
        model=cfg.llm_model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"format": {"type": "json_schema", "schema": schema}},
    )
    if resp.stop_reason == "refusal":
        log.warning("Anthropic LLM refused request")
        return None
    text = next((b.text for b in resp.content if b.type == "text"), None)
    return _parse_json_loose(text, provider="anthropic")


# ------------------------------------------------------------------ Gemini
def _gemini_api_key() -> str | None:
    return (
        os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or secrets.get_secret(secrets.GEMINI_API_KEY)
    )


def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        from google import genai

        _gemini_client = genai.Client(api_key=_gemini_api_key())
    return _gemini_client


def _gemini_on_cooldown() -> bool:
    return time.monotonic() < _gemini_cooldown_until


def _start_gemini_cooldown(seconds: float) -> None:
    global _gemini_cooldown_until
    until = time.monotonic() + seconds
    if until > _gemini_cooldown_until:
        _gemini_cooldown_until = until
        log.warning("Gemini rate-limited; backing off for %.0fs (falling back to rules until then)", seconds)


def _retry_after_seconds(exc: Exception) -> float:
    m = re.search(r"retry in (\d+(?:\.\d+)?)s", str(exc), re.I)
    return float(m.group(1)) + 1.0 if m else DEFAULT_COOLDOWN_SECONDS


def _structured_gemini(cfg: Config, system: str, user: str, schema: dict[str, Any], max_tokens: int) -> dict[str, Any] | None:
    if _gemini_on_cooldown():
        return None
    client = _get_gemini_client()
    try:
        interaction = client.interactions.create(
            model=cfg.llm_model_gemini,
            input=user,
            system_instruction=system,
            response_mime_type="application/json",
            response_format={"type": "text", "mime_type": "application/json", "schema_": schema},
            generation_config={"max_output_tokens": max_tokens},
        )
    except Exception as e:
        if getattr(e, "status_code", None) == 429:
            _start_gemini_cooldown(_retry_after_seconds(e))
            return None
        raise
    text = getattr(interaction, "output_text", None)
    return _parse_json_loose(text, provider="gemini")


# ------------------------------------------------------------------ parsing
def _parse_json_loose(text: str | None, *, provider: str) -> dict[str, Any] | None:
    """Parse model output as JSON, tolerating common near-misses:
    markdown code fences, and Python-repr-style single-quoted dicts.
    Returns None (and logs the raw text) only if nothing works.
    """
    if not text:
        return None
    candidate = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", candidate, re.S)
    if fence:
        candidate = fence.group(1).strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    try:
        obj = ast.literal_eval(candidate)  # tolerates {'a': 'b', 'c': True} etc.
        if isinstance(obj, dict):
            return json.loads(json.dumps(obj))  # normalize (e.g. True -> true) and validate
    except (ValueError, SyntaxError):
        pass
    log.warning("%s returned unparseable output; falling back to rules. Raw (truncated): %r", provider, text[:300])
    return None


# ------------------------------------------------------------------ Public
def _api_key(cfg: Config) -> str | None:
    return _gemini_api_key() if cfg.llm_provider == "gemini" else _anthropic_api_key()


def available(cfg: Config) -> bool:
    if not (cfg.llm_enabled and _api_key(cfg)):
        return False
    if cfg.llm_provider == "gemini" and _gemini_on_cooldown():
        return False
    return True


def structured(cfg: Config, *, system: str, user: str, schema: dict[str, Any], max_tokens: int = 2000) -> dict[str, Any] | None:
    """Call the configured model with a JSON schema output constraint. Returns dict or None on failure."""
    if not available(cfg):
        return None
    try:
        if cfg.llm_provider == "gemini":
            return _structured_gemini(cfg, system, user, schema, max_tokens)
        return _structured_anthropic(cfg, system, user, schema, max_tokens)
    except Exception as e:  # network, auth, parse — never let a classifier crash the sync
        log.warning("LLM call failed (%s): %s", cfg.llm_provider, e)
        return None

"""Thin wrapper around the Anthropic SDK that returns structured JSON.

The model is never the source of truth for grades, due dates or senders; it
only classifies and summarizes. If no API key is present (Keychain or
ANTHROPIC_API_KEY env), `available()` is False and callers fall back to rules.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from .. import secrets
from ..config import Config

log = logging.getLogger(__name__)

_client = None


def _api_key() -> str | None:
    return os.environ.get("ANTHROPIC_API_KEY") or secrets.get_secret(secrets.ANTHROPIC_API_KEY)


def available(cfg: Config) -> bool:
    return bool(cfg.llm_enabled and _api_key())


def _get_client():
    global _client
    if _client is None:
        import anthropic

        _client = anthropic.Anthropic(api_key=_api_key(), max_retries=2, timeout=60.0)
    return _client


def structured(cfg: Config, *, system: str, user: str, schema: dict[str, Any], max_tokens: int = 2000) -> dict[str, Any] | None:
    """Call the model with a JSON schema output constraint. Returns dict or None on failure."""
    if not available(cfg):
        return None
    try:
        client = _get_client()
        resp = client.messages.create(
            model=cfg.llm_model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
        if resp.stop_reason == "refusal":
            log.warning("LLM refused request")
            return None
        text = next((b.text for b in resp.content if b.type == "text"), None)
        if not text:
            return None
        return json.loads(text)
    except Exception as e:  # network, auth, parse
        log.warning("LLM call failed: %s", e)
        return None

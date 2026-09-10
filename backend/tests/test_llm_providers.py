import os

from morningbrief.config import Config
from morningbrief.services import llm


def test_available_false_with_no_key(cfg):
    cfg.llm_enabled = True
    cfg.llm_provider = "anthropic"
    assert not llm.available(cfg)


def test_anthropic_key_from_env(cfg, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    cfg.llm_enabled = True
    cfg.llm_provider = "anthropic"
    assert llm.available(cfg)


def test_gemini_key_from_env(cfg, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    cfg.llm_enabled = True
    cfg.llm_provider = "gemini"
    assert llm.available(cfg)
    monkeypatch.delenv("GEMINI_API_KEY")
    assert not llm.available(cfg)


def test_gemini_key_from_keychain(cfg):
    from morningbrief import secrets

    secrets.set_secret(secrets.GEMINI_API_KEY, "stored-key")
    cfg.llm_enabled = True
    cfg.llm_provider = "gemini"
    assert llm.available(cfg)
    secrets.delete_secret(secrets.GEMINI_API_KEY)


def test_structured_returns_none_when_disabled(cfg):
    cfg.llm_enabled = False
    assert llm.structured(cfg, system="s", user="u", schema={"type": "object"}) is None


def test_gemini_structured_bad_key_returns_none_gracefully(cfg, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "definitely-not-a-real-key")
    cfg.llm_enabled = True
    cfg.llm_provider = "gemini"
    out = llm.structured(
        cfg,
        system="reply with field a",
        user="go",
        schema={"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"], "additionalProperties": False},
    )
    assert out is None


def test_parse_json_loose_variants():
    from morningbrief.services.llm import _parse_json_loose

    assert _parse_json_loose('{"a": 1}', provider="t") == {"a": 1}
    assert _parse_json_loose('```json\n{"a": 1}\n```', provider="t") == {"a": 1}
    assert _parse_json_loose("{'a': 1, 'b': True}", provider="t") == {"a": 1, "b": True}
    assert _parse_json_loose("", provider="t") is None
    assert _parse_json_loose("not json", provider="t") is None
    assert _parse_json_loose(None, provider="t") is None


def test_gemini_cooldown_short_circuits(cfg, monkeypatch):
    import morningbrief.services.llm as llm_mod

    monkeypatch.setenv("GEMINI_API_KEY", "x")
    cfg.llm_enabled = True
    cfg.llm_provider = "gemini"
    assert llm.available(cfg)

    llm_mod._start_gemini_cooldown(60)
    assert not llm.available(cfg)
    # structured() must not attempt a call while on cooldown (no client built)
    assert llm.structured(cfg, system="s", user="u", schema={"type": "object"}) is None

    llm_mod._gemini_cooldown_until = 0.0  # reset for other tests


def test_retry_after_seconds_parses_message():
    from morningbrief.services.llm import _retry_after_seconds

    class Fake(Exception):
        pass

    e = Fake("Please retry in 42.99s")
    assert 43.0 < _retry_after_seconds(e) < 44.5

    e2 = Fake("no timing info here")
    from morningbrief.services.llm import DEFAULT_COOLDOWN_SECONDS
    assert _retry_after_seconds(e2) == DEFAULT_COOLDOWN_SECONDS

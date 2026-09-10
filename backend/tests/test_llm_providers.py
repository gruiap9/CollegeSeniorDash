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

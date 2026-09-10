"""Secrets storage backed by the macOS Keychain via the `security` CLI.

No passwords are ever stored; only OAuth tokens / API keys the user grants.
Falls back to an in-memory store when MORNINGBRIEF_FAKE_KEYCHAIN=1 (tests).
"""

from __future__ import annotations

import os
import subprocess

SERVICE = "com.gruiapascale.morningbrief"
_fake: dict[str, str] = {}


def _use_fake() -> bool:
    return os.environ.get("MORNINGBRIEF_FAKE_KEYCHAIN") == "1"


def get_secret(name: str) -> str | None:
    if _use_fake():
        return _fake.get(name)
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-s", SERVICE, "-a", name, "-w"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    if out.returncode != 0:
        return None
    return out.stdout.rstrip("\n") or None


def set_secret(name: str, value: str) -> None:
    if _use_fake():
        _fake[name] = value
        return
    # -U updates an existing item in place instead of failing.
    subprocess.run(
        ["security", "add-generic-password", "-s", SERVICE, "-a", name, "-w", value, "-U"],
        check=True,
        capture_output=True,
    )


def delete_secret(name: str) -> None:
    if _use_fake():
        _fake.pop(name, None)
        return
    subprocess.run(
        ["security", "delete-generic-password", "-s", SERVICE, "-a", name],
        check=False,
        capture_output=True,
    )


# Well-known secret names
GMAIL_TOKEN = "gmail_token_json"
OUTLOOK_TOKEN_CACHE = "outlook_msal_cache"
CANVAS_TOKEN = "canvas_token"
ANTHROPIC_API_KEY = "anthropic_api_key"

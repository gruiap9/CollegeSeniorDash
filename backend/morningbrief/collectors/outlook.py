"""UMass email via Microsoft Graph (Mail.Read, delegated, OAuth device-code flow).

Setup: register a *public client* app in Azure (or use one your org allows),
enable "Allow public client flows", add delegated permission Mail.Read, set
`outlook_client_id` (and `outlook_tenant`, e.g. "umass.edu" or "common") in
config.json, then run `morningbrief setup-outlook`. The MSAL token cache
(refresh token) lives in the Keychain. No password is ever stored.

If your UMass mailbox is actually Google Workspace, use the Gmail collector
with that account instead.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr

import httpx

from .. import secrets
from ..config import Config
from ..db.database import Database
from ..db.models import Email
from ..db.repo import upsert_email
from ..utils.html import html_to_text
from .base import CollectResult, Collector

log = logging.getLogger(__name__)
SOURCE = "outlook"
SCOPES = ["Mail.Read"]
GRAPH = "https://graph.microsoft.com/v1.0"


def _app(cfg: Config):
    import msal

    cache = msal.SerializableTokenCache()
    raw = secrets.get_secret(secrets.OUTLOOK_TOKEN_CACHE)
    if raw:
        cache.deserialize(raw)
    app = msal.PublicClientApplication(
        cfg.outlook_client_id,
        authority=f"https://login.microsoftonline.com/{cfg.outlook_tenant or 'common'}",
        token_cache=cache,
    )
    return app, cache


def _persist(cache) -> None:
    if cache.has_state_changed:
        secrets.set_secret(secrets.OUTLOOK_TOKEN_CACHE, cache.serialize())


def interactive_setup(cfg: Config) -> int:
    if not cfg.outlook_client_id:
        print("Set outlook_client_id in config.json first (Azure public-client app id).")
        return 1
    app, cache = _app(cfg)
    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        print(f"device flow failed: {flow}")
        return 1
    print(flow["message"])
    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        print(f"auth failed: {result.get('error_description')}")
        return 1
    _persist(cache)
    cfg.outlook_enabled = True
    cfg.save()
    print("Outlook authorized (Mail.Read). Token cache stored in Keychain; outlook_enabled=true.")
    return 0


def access_token(cfg: Config) -> str:
    app, cache = _app(cfg)
    accounts = app.get_accounts()
    result = app.acquire_token_silent(SCOPES, account=accounts[0]) if accounts else None
    _persist(cache)
    if not result or "access_token" not in result:
        raise RuntimeError("Outlook not authorized; run `morningbrief setup-outlook`")
    return result["access_token"]


def parse_message(m: dict, account: str = SOURCE) -> Email:
    frm = (m.get("from") or {}).get("emailAddress") or {}
    body = m.get("body") or {}
    content = body.get("content") or ""
    text = html_to_text(content) if body.get("contentType", "").lower() == "html" else content
    text = re.sub(r"\n{3,}", "\n\n", text)[:20000]
    received = m.get("receivedDateTime")
    if received:
        received = datetime.fromisoformat(received.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    return Email(
        message_id=m["id"],
        account=account,
        thread_id=m.get("conversationId"),
        sender=frm.get("name") or frm.get("address") or "",
        sender_email=(frm.get("address") or parseaddr(frm.get("name") or "")[1]).lower(),
        subject=m.get("subject") or "(no subject)",
        received_at=received,
        snippet=(m.get("bodyPreview") or "")[:300],
        body=text,
        url=m.get("webLink"),
    )


class OutlookCollector(Collector):
    name = SOURCE

    def enabled(self, cfg: Config) -> bool:
        return cfg.outlook_enabled

    def collect(self, cfg: Config, db: Database) -> CollectResult:
        res = CollectResult(SOURCE)
        token = access_token(cfg)
        state = db.get_sync(SOURCE)
        if state and state["last_success"]:
            since = datetime.fromisoformat(state["last_success"]) - timedelta(hours=6)
        else:
            since = datetime.now(timezone.utc) - timedelta(days=7)
        params = {
            "$filter": f"receivedDateTime ge {since.strftime('%Y-%m-%dT%H:%M:%SZ')}",
            "$orderby": "receivedDateTime desc",
            "$select": "id,conversationId,subject,from,receivedDateTime,bodyPreview,body,webLink",
            "$top": "50",
        }
        url = f"{GRAPH}/me/messages"
        known = {r["message_id"] for r in db.rows("SELECT message_id FROM emails WHERE account=?", (SOURCE,))}
        with httpx.Client(timeout=30, headers={"Authorization": f"Bearer {token}", "Prefer": 'outlook.body-content-type="text"'}) as c:
            pages = 0
            while url and pages < 20:
                r = c.get(url, params=params)
                r.raise_for_status()
                js = r.json()
                for m in js.get("value", []):
                    if m["id"] in known:
                        continue
                    if upsert_email(db, parse_message(m)):
                        res.new += 1
                url = js.get("@odata.nextLink")
                params = None
                pages += 1
        return res

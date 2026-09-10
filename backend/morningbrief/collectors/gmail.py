"""Gmail collector using the official Gmail API (read-only scope).

Setup (one-time): create an OAuth "Desktop app" client in Google Cloud Console,
download the client JSON, set `gmail_client_secret_file` in config.json to its
path (outside the repo), then run `morningbrief setup-gmail`.
The refresh token is stored in the macOS Keychain.
"""

from __future__ import annotations

import base64
import logging
import re
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr, parsedate_to_datetime

from .. import secrets
from ..config import Config
from ..db.database import Database
from ..db.models import Email
from ..db.repo import upsert_email
from ..utils.html import html_to_text
from .base import CollectResult, Collector

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
SOURCE = "gmail"


def _credentials():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    raw = secrets.get_secret(secrets.GMAIL_TOKEN)
    if not raw:
        return None
    creds = Credentials.from_authorized_user_info(__import__("json").loads(raw), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        secrets.set_secret(secrets.GMAIL_TOKEN, creds.to_json())
    return creds


def interactive_setup(cfg: Config) -> int:
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not cfg.gmail_client_secret_file:
        print("Set gmail_client_secret_file in config.json to your OAuth client JSON path first.")
        return 1
    flow = InstalledAppFlow.from_client_secrets_file(cfg.gmail_client_secret_file, SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    secrets.set_secret(secrets.GMAIL_TOKEN, creds.to_json())
    cfg.gmail_enabled = True
    cfg.save()
    print("Gmail authorized (read-only). Token stored in Keychain; gmail_enabled=true.")
    return 0


def _service():
    from googleapiclient.discovery import build

    creds = _credentials()
    if creds is None:
        raise RuntimeError("Gmail not authorized; run `morningbrief setup-gmail`")
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _walk_parts(payload) -> tuple[str, str]:
    """Return (text_plain, text_html) concatenated across MIME parts."""
    plain, html = [], []

    def visit(p):
        mime = p.get("mimeType", "")
        body = p.get("body", {})
        data = body.get("data")
        if data and mime.startswith("text/"):
            try:
                decoded = base64.urlsafe_b64decode(data + "===").decode("utf-8", errors="replace")
            except Exception:
                decoded = ""
            (plain if mime == "text/plain" else html).append(decoded)
        for child in p.get("parts", []) or []:
            visit(child)

    visit(payload)
    return "\n".join(plain), "\n".join(html)


def parse_message(msg: dict, account: str = SOURCE) -> Email:
    headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
    sender_name, sender_email = parseaddr(headers.get("from", ""))
    received = None
    if msg.get("internalDate"):
        received = datetime.fromtimestamp(int(msg["internalDate"]) / 1000, tz=timezone.utc).isoformat()
    elif headers.get("date"):
        try:
            received = parsedate_to_datetime(headers["date"]).astimezone(timezone.utc).isoformat()
        except Exception:
            received = None
    plain, html = _walk_parts(msg.get("payload", {}))
    body = plain.strip() or html_to_text(html)
    body = re.sub(r"\n{3,}", "\n\n", body)[:20000]
    return Email(
        message_id=msg["id"],
        account=account,
        thread_id=msg.get("threadId"),
        sender=sender_name or sender_email,
        sender_email=sender_email.lower(),
        subject=headers.get("subject", "(no subject)"),
        received_at=received,
        snippet=msg.get("snippet", ""),
        body=body,
        url=f"https://mail.google.com/mail/u/0/#all/{msg['id']}",
    )


class GmailCollector(Collector):
    name = SOURCE

    def enabled(self, cfg: Config) -> bool:
        return cfg.gmail_enabled

    def collect(self, cfg: Config, db: Database) -> CollectResult:
        res = CollectResult(SOURCE)
        svc = _service()
        state = db.get_sync(SOURCE)
        # Gmail search `after:` takes epoch seconds. First run: last 7 days.
        if state and state["last_success"]:
            since = datetime.fromisoformat(state["last_success"]) - timedelta(hours=6)
        else:
            since = datetime.now(timezone.utc) - timedelta(days=7)
        query = f"after:{int(since.timestamp())} -in:spam -in:trash"
        ids: list[str] = []
        page = None
        while True:
            resp = svc.users().messages().list(userId="me", q=query, maxResults=200, pageToken=page).execute()
            ids.extend(m["id"] for m in resp.get("messages", []))
            page = resp.get("nextPageToken")
            if not page or len(ids) >= 1000:
                break
        known = {r["message_id"] for r in db.rows("SELECT message_id FROM emails WHERE account=?", (SOURCE,))}
        for mid in ids:
            if mid in known:
                continue
            msg = svc.users().messages().get(userId="me", id=mid, format="full").execute()
            if upsert_email(db, parse_message(msg)):
                res.new += 1
        return res

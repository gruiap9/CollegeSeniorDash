# Setup

All commands run from the repo root unless noted. The backend lives in
`backend/` with its own virtualenv at `backend/.venv`.

## 0. Install

```bash
scripts/install.sh
```

This creates the venv, installs dependencies, runs `morningbrief init`
(creating `~/Library/Application Support/MorningBrief/`), and builds the app
to `mac/build/Morning Brief.app`.

Alias for convenience:

```bash
alias mb=backend/.venv/bin/morningbrief
```

## 1. Course sites and news (no setup)

`mb sync` already scrapes the CS520 and CS461 sites and the RSS feed set in
`config.json`. Edit `course_sites` / `news_feeds` there to add or remove
sources. `mb events` lists what changed.

## 2. Gmail (read-only, multiple accounts supported)

1. Google Cloud Console → create a project → enable **Gmail API**.
2. OAuth consent screen: External, add every Google account you plan to
   connect as a test user (if the app is still in "Testing" publishing
   status, only listed test users can authorize it).
3. Credentials → Create OAuth client ID → **Desktop app** → download JSON.
4. Move it somewhere outside the repo, e.g. `~/Library/Application Support/MorningBrief/google_client.json`.
5. In `config.json` set `"gmail_client_secret_file"` to that path. This one
   OAuth client is shared by every Gmail account you connect — you don't need
   a separate one per account.
6. `mb setup-gmail` → browser consent → sign in with the account you want to
   add. The address is discovered automatically from the account you signed
   into and appended to `gmail_accounts` in `config.json`; its token is
   stored in the Keychain under a name unique to that address.
7. To add another account (a second personal address, a custom domain that's
   actually a Google account, etc.), just run `mb setup-gmail` again and sign
   in with the other account. It adds to `gmail_accounts` rather than
   replacing the first one — nothing about the first account changes.

Scope requested: `gmail.readonly` only, for every connected account.

Each account syncs and tracks "since last sync" independently, so adding a
new one doesn't re-fetch or duplicate anything from accounts already
connected — and each account's first sync only pulls the last 7 days.

## 3. UMass email (Microsoft 365 / Outlook)

First confirm your UMass mailbox is Microsoft 365 (outlook.office.com). If it
is Google Workspace, use the Gmail steps with that account instead.

1. You need an Azure app registration that allows public-client (device code)
   sign-in with delegated `Mail.Read`. If UMass IT does not allow personal app
   registrations in the UMass tenant, register the app in a personal Azure
   account as *multi-tenant* ("Accounts in any organizational directory") and
   use tenant `common`; sign-in will still require UMass admin consent if the
   tenant blocks unverified apps. **If consent is refused, stop there** — do
   not work around it. The Gmail-forwarding fallback below is the safe option.
2. `config.json`: set `"outlook_client_id"` and `"outlook_tenant"` (`"common"` or the UMass tenant id).
3. `mb setup-outlook` → follow the device-code prompt → token cache goes to Keychain.

Fallback: forward UMass mail to Gmail (allowed by UMass mail settings) and rely
on the Gmail collector; the school classifier keys on `@umass.edu` senders, not
on the mailbox.

## 4. Canvas

1. Canvas → Account → Settings → **+ New Access Token** (give it a purpose and, optionally, an expiry).
2. `mb setup-canvas` → paste the token (hidden) → verified against `/api/v1/users/self` → stored in Keychain.

Base URL defaults to `https://umass.instructure.com`.

## 5. Gradescope and Piazza

Email-based. In Gradescope, keep "email me when grades are released / when I
submit" on. In Piazza, set email notifications to *instant* for each course
(at least for instructor posts). The email pipeline parses them into
assignments, grades and posts.

## 6. AI classification (optional)

Rules alone classify most email. For ambiguous messages, Piazza summaries and
news ranking, add an API key for one of two supported providers. Pick one —
`llm_provider` in `config.json` controls which is used (`"anthropic"` is the
default).

**Anthropic (Claude):**

```bash
mb secret set anthropic_api_key
```

Uses `llm_model` in `config.json` (default `claude-haiku-4-5`).

**Google (Gemini):**

```bash
mb secret set gemini_api_key
```

Then set `"llm_provider": "gemini"` in `config.json`. Uses `llm_model_gemini`
(default `gemini-3.5-flash-lite`) — deliberately a lite model: this workload
is many small per-email classification calls per sync, not a few hard ones,
and the newest full-size `gemini-3.x` models carry a much smaller free-tier
quota. If you switch to a bigger Gemini model and see sync logs warning about
rate limits, the backend backs off automatically and falls back to rules for
the rest of that sync — nothing crashes, but you'll get fewer LLM-assisted
classifications until the next run.

Both keys can be stored at the same time; only the one named by
`llm_provider` is used. Set `"llm_enabled": false` to run fully offline on
rules alone regardless of provider.

## 7. Background sync + app

```bash
mb install-agent        # launchd LaunchAgent, every 30 min (sync_interval_minutes)
open "mac/build/Morning Brief.app"
```

In the menu-bar menu enable **Launch at login**. The dashboard appears
automatically on the first login / wake / unlock of each day and can be
reopened from the ☀ menu any time. `mb install-agent --uninstall` removes the
agent.

## Where things live

```
~/Library/Application Support/MorningBrief/
  config.json         sources, feeds, model
  morningbrief.db     SQLite (assignments, emails, piazza_posts, news, page_sections, events)
  morning_brief.json  the cached brief the app renders
  backend.json        interpreter path the app uses for "Refresh"
  app_state.json      last_brief_shown_date, preferences
  logs/
Keychain service "com.gruiapascale.morningbrief": gmail_token_json:<address> (one per connected Gmail account), outlook_msal_cache, canvas_token, anthropic_api_key, gemini_api_key
```

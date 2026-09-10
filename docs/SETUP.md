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

## 2. Gmail (read-only)

1. Google Cloud Console → create a project → enable **Gmail API**.
2. OAuth consent screen: External, add yourself as a test user.
3. Credentials → Create OAuth client ID → **Desktop app** → download JSON.
4. Move it somewhere outside the repo, e.g. `~/Library/Application Support/MorningBrief/google_client.json`.
5. In `config.json` set `"gmail_client_secret_file"` to that path.
6. `mb setup-gmail` → browser consent → token is stored in Keychain, `gmail_enabled` flips to true.

Scope requested: `gmail.readonly` only.

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
(default `gemini-3.8-flash`).

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
Keychain service "com.gruiapascale.morningbrief": gmail_token_json, outlook_msal_cache, canvas_token, anthropic_api_key, gemini_api_key
```

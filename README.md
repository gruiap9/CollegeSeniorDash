# Morning Brief (CollegeSeniorDash)

A local macOS "Morning Brief": a Python backend collects your job-search email,
school email, Canvas, the CS520 / CS461 course sites, Gradescope and Piazza
notifications, and a fixed set of tech-news feeds into a local SQLite
database. It detects **what changed since yesterday**, builds a cached
`morning_brief.json`, and a SwiftUI menu-bar app shows it on the first unlock
of each day. Every item is clickable and opens the original email, assignment,
post or article.

Everything stays on your Mac. OAuth tokens and API keys live in the macOS
Keychain. No passwords are ever stored.

```
Gmail API ─┐
MS Graph  ─┤
Canvas API─┤                              ┌─ change detection
CS520 site─┼─▶ collectors ─▶ SQLite ──────┼─ AI classification / summaries
CS461 site─┤                              └─ brief builder ─▶ morning_brief.json ─▶ SwiftUI app
Gradescope─┤ (email)
Piazza    ─┤ (email)
RSS feeds ─┘
```

## Quick start

```bash
scripts/install.sh          # venv, deps, init data dir, build the .app
backend/.venv/bin/morningbrief sync     # first sync (course sites + news work with zero setup)
open "mac/build/Morning Brief.app"
```

Then follow [docs/SETUP.md](docs/SETUP.md) to connect Gmail, UMass Outlook,
Canvas and (optionally) the Anthropic API key for smarter classification.

## Layout

```
backend/            Python package `morningbrief` (collectors, classifiers, summarizers, services, db)
backend/tests/      pytest suite (fixtures include real snapshots of the course sites)
mac/MorningBrief/   SwiftUI menu-bar app (SwiftPM; no Xcode required)
scripts/            install.sh, build_app.sh
docs/               SETUP.md, ARCHITECTURE.md
```

## Branching

- `main` — releases only.
- `dev` — integration branch. Feature branches (`feature/*`) are cut from and merged into `dev`.

## Status

| Phase | What | State |
|---|---|---|
| 1 | Python + SQLite foundation | done |
| 2–3 | Gmail collector + job-email classifier | done |
| 4 | Canvas | done |
| 5 | CS520 + CS461 scrapers with change detection | done |
| 6 | UMass Outlook (Microsoft Graph) | done |
| 7–8 | Brief generator, tech news | done |
| 9–10 | SwiftUI dashboard, auto-launch / first-open | done |
| 11–12 | Gradescope, Piazza (email-based v1) | done |
| 13 | Notifications | done |

Piazza and Gradescope use their email notifications on purpose: direct
authenticated access would require storing your password. Turn on instant
email notifications in both services for best results.

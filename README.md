# Morning Brief (CollegeSeniorDash)

A local macOS "Morning Brief" app: a Python backend collects email, Canvas,
course-site, Gradescope, Piazza and tech-news data into a local SQLite
database, detects what changed since yesterday, and renders a cached brief
that a SwiftUI menu-bar app shows on the first unlock of the day.

Everything stays on your Mac. Secrets live in the macOS Keychain.

## Branching

- `main` — releases only.
- `dev` — integration branch. All feature branches are cut from and merged into `dev`.
- `feature/*` — one branch per unit of work.

See `docs/` for setup and architecture.

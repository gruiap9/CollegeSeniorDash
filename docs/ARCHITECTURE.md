# Architecture

## Pipeline (`morningbrief sync`)

1. **Collectors** (`backend/morningbrief/collectors/`) fetch raw data and
   upsert normalized rows. Each is independent; a failure is recorded in
   `sync_state.last_error` and never stops the others.
   - `gmail.py` / `outlook.py` — messages since last success (first run: 7 days).
   - `canvas.py` — active courses → assignments with submission state.
   - `course_sites.py` — CS520 (`parse_cs520`) and CS461 (`parse_cs461`):
     deterministic deadline parsing (`utils/dates.parse_due_text`) and
     per-section hashing (`page_sections`).
   - `news.py` — RSS/Atom feed set, canonical-URL dedupe.
   - `piazza.py` — email-based; prunes old posts.
2. **Email pipeline** (`services/email_pipeline.py`) routes each unclassified
   email: gradescope → `classifiers/gradescope_email.py`; piazza →
   `classifiers/piazza_email.py`; `@umass.edu` → `classifiers/school_email.py`;
   everything else → `classifiers/job_email.py`. Rules first; the LLM only
   sees ambiguous cases and returns JSON (`services/llm.py`, provider
   selectable between Anthropic and Gemini via `llm_provider`).
3. **Change detection** (`services/change_detector.py` + inline in
   collectors) writes to the `events` table with a `dedupe_key`:
   `job.*`, `email.important`, `assignment.new|due_changed|due_soon|overdue|submitted`,
   `grade.new`, `piazza.instructor`, `site.changed`.
4. **Brief builder** (`services/brief_builder.py`) reads the DB and writes
   `morning_brief.json` atomically. Piazza and news summaries come from
   `summarizers/`.

The model is never the source of truth for grades, due dates, submission
status, senders or times.

## macOS app (`mac/MorningBrief`)

- `BriefStore` decodes the JSON and watches the data directory; **Refresh**
  runs `python -m morningbrief.main sync` using `backend.json`.
- `DashboardWindow` is an AppKit `NSWindow` hosting `DashboardView`
  (collapsible sections: Since yesterday, Job search, Important email,
  School, Piazza, Tech).
- `FirstOpenController` opens the dashboard once per calendar day on launch,
  wake, unlock or session activation (`app_state.json`).
- `Notifier` posts local notifications for importance-3 events and new grades only.
- `LaunchAtLogin` uses `SMAppService`.

## Schema

See `backend/morningbrief/db/database.py`. Every row carries `first_seen` /
`last_seen` so "new since yesterday" is a query, not a guess.

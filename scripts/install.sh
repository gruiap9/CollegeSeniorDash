#!/bin/bash
# One-shot local install: backend venv + init + app build. Safe to re-run.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"
if [[ ! -x .venv/bin/python ]]; then python3 -m venv .venv; fi
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -e ".[dev]"
.venv/bin/morningbrief init
.venv/bin/pytest -q
"$ROOT/scripts/build_app.sh"
echo
echo "Next: see docs/SETUP.md to connect Gmail / Outlook / Canvas, then:"
echo "  backend/.venv/bin/morningbrief sync && open \"/Applications/Morning Brief.app\""

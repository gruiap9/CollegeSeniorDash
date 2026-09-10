"""Run all collectors, classify, detect changes, rebuild the brief.

Also installs a launchd LaunchAgent so this runs in the background.
"""

from __future__ import annotations

import logging
import os
import plistlib
import subprocess
import sys
from pathlib import Path

from ..config import Config, data_dir, log_dir
from ..db.database import Database

log = logging.getLogger(__name__)

LAUNCH_AGENT_LABEL = "com.gruiapascale.morningbrief.sync"


def collectors():
    from ..collectors.canvas import CanvasCollector
    from ..collectors.course_sites import CourseSiteCollector
    from ..collectors.gmail import GmailCollector
    from ..collectors.news import NewsCollector
    from ..collectors.outlook import OutlookCollector
    from ..collectors.piazza import PiazzaCollector

    return [GmailCollector(), OutlookCollector(), CanvasCollector(), CourseSiteCollector(), PiazzaCollector(), NewsCollector()]


def run_sync(cfg: Config, db: Database, only: str | None = None) -> dict[str, str]:
    from .brief_builder import build_brief, write_brief
    from .change_detector import detect_changes
    from .email_pipeline import process_unclassified

    wanted = {s.strip() for s in only.split(",")} if only else None
    results: dict[str, str] = {}
    for c in collectors():
        if wanted and c.name not in wanted:
            continue
        if not c.enabled(cfg):
            results[c.name] = "disabled"
            continue
        db.mark_sync_attempt(c.name)
        try:
            r = c.collect(cfg, db)
            db.mark_sync_success(c.name)
            results[c.name] = str(r)
        except Exception as e:
            log.exception("collector %s failed", c.name)
            db.mark_sync_error(c.name, repr(e))
            results[c.name] = f"ERROR {e!r}"

    try:
        n = process_unclassified(cfg, db)
        results["classify"] = f"{n} emails"
    except Exception as e:
        log.exception("classification failed")
        results["classify"] = f"ERROR {e!r}"
    try:
        n = detect_changes(cfg, db)
        results["changes"] = f"{n} events"
    except Exception as e:
        log.exception("change detection failed")
        results["changes"] = f"ERROR {e!r}"
    try:
        write_brief(build_brief(cfg, db))
        results["brief"] = "written"
    except Exception as e:
        log.exception("brief build failed")
        results["brief"] = f"ERROR {e!r}"
    return results


# ---------------------------------------------------------------- launchd
def _plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"


def install_launch_agent(cfg: Config) -> int:
    python = sys.executable
    plist = {
        "Label": LAUNCH_AGENT_LABEL,
        "ProgramArguments": [python, "-m", "morningbrief.main", "sync"],
        "StartInterval": max(300, cfg.sync_interval_minutes * 60),
        "RunAtLoad": True,
        "StandardOutPath": str(log_dir() / "launchd.out.log"),
        "StandardErrorPath": str(log_dir() / "launchd.err.log"),
        "EnvironmentVariables": {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin", "HOME": str(Path.home())},
        "ProcessType": "Background",
        "Nice": 10,
    }
    p = _plist_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "wb") as f:
        plistlib.dump(plist, f)
    uid = os.getuid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}", str(p)], capture_output=True)
    r = subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(p)], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"launchctl bootstrap failed: {r.stderr.strip()}")
        return 1
    print(f"Installed LaunchAgent {LAUNCH_AGENT_LABEL} (every {plist['StartInterval']//60} min) using {python}")
    print(f"Data: {data_dir()}")
    return 0


def uninstall_launch_agent() -> int:
    p = _plist_path()
    uid = os.getuid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}", str(p)], capture_output=True)
    if p.exists():
        p.unlink()
    print("LaunchAgent removed")
    return 0

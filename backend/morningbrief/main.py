"""Command-line entry point.

    morningbrief init                 create data dir, config and database
    morningbrief config               print config path and contents
    morningbrief secret set NAME      store a secret in Keychain (prompted, hidden)
    morningbrief sync [--only src]    run collectors + classifiers, emit events
    morningbrief brief [--print]      build morning_brief.json (and print)
    morningbrief events [--days N]    list recent events
    morningbrief setup-gmail          run Google OAuth flow (opens browser)
    morningbrief setup-outlook        run Microsoft device-code flow
    morningbrief setup-canvas         store a Canvas access token
    morningbrief install-agent        install launchd background sync
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys

from . import secrets
from .config import Config, brief_path, config_path, data_dir, db_path
from .db.database import Database
from .logging_setup import setup as setup_logging


def cmd_init(args) -> int:
    cfg = Config.load()
    Database().close()
    print(f"Data dir : {data_dir()}")
    print(f"Config   : {config_path()}")
    print(f"Database : {db_path()}")
    print(f"Brief    : {brief_path()}")
    print("Edit config.json to enable sources, then run the setup-* commands.")
    return 0


def cmd_config(args) -> int:
    cfg = Config.load()
    print(config_path())
    print(json.dumps(json.loads(config_path().read_text()), indent=2))
    return 0


def cmd_secret(args) -> int:
    if args.action == "set":
        value = getpass.getpass(f"Value for {args.name} (hidden): ")
        if not value:
            print("empty value, aborting")
            return 1
        secrets.set_secret(args.name, value)
        print(f"stored {args.name} in Keychain")
    elif args.action == "delete":
        secrets.delete_secret(args.name)
        print(f"deleted {args.name}")
    elif args.action == "check":
        print("present" if secrets.get_secret(args.name) else "missing")
    return 0


def cmd_sync(args) -> int:
    from .services.scheduler import run_sync

    cfg = Config.load()
    db = Database()
    try:
        results = run_sync(cfg, db, only=args.only)
    finally:
        db.close()
    for src, res in results.items():
        print(f"{src:12s} {res}")
    return 0


def cmd_brief(args) -> int:
    from .services.brief_builder import build_brief, write_brief

    cfg = Config.load()
    db = Database()
    try:
        brief = build_brief(cfg, db)
        path = write_brief(brief)
    finally:
        db.close()
    if args.print:
        print(json.dumps(brief, indent=2))
    else:
        print(f"wrote {path}")
    return 0


def cmd_events(args) -> int:
    from datetime import datetime, timedelta, timezone

    db = Database()
    since = (datetime.now(timezone.utc) - timedelta(days=args.days)).isoformat()
    for e in db.events_since(since):
        print(f"[{e['created_at']}] ({e['importance']}) {e['kind']:24s} {e['title']}  {e['detail'] or ''}")
    db.close()
    return 0


def cmd_setup_gmail(args) -> int:
    from .collectors.gmail import interactive_setup

    return interactive_setup(Config.load())


def cmd_setup_outlook(args) -> int:
    from .collectors.outlook import interactive_setup

    return interactive_setup(Config.load())


def cmd_setup_canvas(args) -> int:
    from .collectors.canvas import interactive_setup

    return interactive_setup(Config.load())


def cmd_install_agent(args) -> int:
    from .services.scheduler import install_launch_agent, uninstall_launch_agent

    if args.uninstall:
        return uninstall_launch_agent()
    return install_launch_agent(Config.load())


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="morningbrief", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init").set_defaults(fn=cmd_init)
    sub.add_parser("config").set_defaults(fn=cmd_config)

    s = sub.add_parser("secret")
    s.add_argument("action", choices=["set", "delete", "check"])
    s.add_argument("name")
    s.set_defaults(fn=cmd_secret)

    s = sub.add_parser("sync")
    s.add_argument("--only", help="comma-separated source names")
    s.set_defaults(fn=cmd_sync)

    s = sub.add_parser("brief")
    s.add_argument("--print", action="store_true")
    s.set_defaults(fn=cmd_brief)

    s = sub.add_parser("events")
    s.add_argument("--days", type=int, default=1)
    s.set_defaults(fn=cmd_events)

    sub.add_parser("setup-gmail").set_defaults(fn=cmd_setup_gmail)
    sub.add_parser("setup-outlook").set_defaults(fn=cmd_setup_outlook)
    sub.add_parser("setup-canvas").set_defaults(fn=cmd_setup_canvas)

    s = sub.add_parser("install-agent")
    s.add_argument("--uninstall", action="store_true")
    s.set_defaults(fn=cmd_install_agent)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(args.verbose)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())

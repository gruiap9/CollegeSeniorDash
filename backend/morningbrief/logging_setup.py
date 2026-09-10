from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .config import log_dir


def setup(verbose: bool = False) -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    level = logging.DEBUG if verbose else logging.INFO
    root.setLevel(level)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    fh = RotatingFileHandler(log_dir() / "morningbrief.log", maxBytes=2_000_000, backupCount=3)
    fh.setFormatter(fmt)
    root.addHandler(fh)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    sh.setLevel(level)
    root.addHandler(sh)
    for noisy in ("httpx", "googleapiclient", "urllib3", "msal"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

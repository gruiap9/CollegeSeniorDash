"""Collector protocol and shared result type."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..config import Config
from ..db.database import Database


@dataclass
class CollectResult:
    source: str
    ok: bool = True
    new: int = 0
    updated: int = 0
    events: int = 0
    error: str | None = None
    notes: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        if not self.ok:
            return f"ERROR {self.error}"
        s = f"ok new={self.new} updated={self.updated} events={self.events}"
        if self.notes:
            s += " " + "; ".join(self.notes)
        return s


class Collector:
    name: str = "base"

    def enabled(self, cfg: Config) -> bool:
        return True

    def collect(self, cfg: Config, db: Database) -> CollectResult:  # pragma: no cover
        raise NotImplementedError

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from obsidian_agent.config import Config
from obsidian_agent.index.store import IndexStore


@dataclass
class JobContext:
    """Runtime context passed to every job."""
    store: IndexStore
    config: Config
    today: date

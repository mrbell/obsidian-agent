from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

from obsidian_agent.config import Config
from obsidian_agent.index.store import IndexStore


@dataclass
class JobContext:
    """Runtime context passed to every job.

    ``delivery`` and ``worker`` are optional so Class A (deterministic) jobs
    can be constructed without them. ``today`` is injected for testability.
    """
    store: IndexStore
    config: Config
    today: date
    delivery: object | None = None   # SmtpDelivery (or any Delivery), if configured
    worker: object | None = None     # ClaudeCodeWorker, for Class B/C jobs (future)
    logger: logging.Logger = field(
        default_factory=lambda: logging.getLogger("obsidian_agent.jobs")
    )

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

from obsidian_agent.config import Config
from obsidian_agent.index.store import IndexStore

if TYPE_CHECKING:
    from obsidian_agent.agent.worker import ClaudeCodeWorker
    from obsidian_agent.delivery.base import Delivery


@dataclass
class JobContext:
    """Runtime context passed to every job.

    ``delivery`` and ``worker`` are optional so Class A (deterministic) jobs
    can be constructed without them. ``today`` is injected for testability.
    """
    store: IndexStore
    config: Config
    today: date
    delivery: Delivery | None = None
    worker: ClaudeCodeWorker | None = None
    logger: logging.Logger = field(
        default_factory=lambda: logging.getLogger("obsidian_agent.jobs")
    )

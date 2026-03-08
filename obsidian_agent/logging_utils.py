from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path


def setup_logging(state_dir: Path, verbose: bool = False) -> None:
    """Configure root logger with stderr and rotating file handlers.

    Args:
        state_dir: Base state directory; logs go to state_dir/logs/.
        verbose: If True, set stderr handler to DEBUG level.
    """
    log_dir = state_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stderr_handler = logging.StreamHandler()
    stderr_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    stderr_handler.setFormatter(formatter)

    file_handler = logging.handlers.RotatingFileHandler(
        filename=log_dir / "obsidian-agent.log",
        maxBytes=1 * 1024 * 1024,  # 1 MB per file
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(stderr_handler)
    root.addHandler(file_handler)

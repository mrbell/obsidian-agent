from __future__ import annotations

from pathlib import Path

from obsidian_agent.agent.base import AgentWorker
from obsidian_agent.agent.claude import ClaudeBackendAdapter
from obsidian_agent.config import AgentConfig


class AgentBackendError(Exception):
    """Raised when the configured agent backend cannot be instantiated."""


def build_agent_worker(
    cfg: AgentConfig,
    *,
    vault_path: Path,
    db_path: Path,
    config_path: Path | None = None,
) -> AgentWorker:
    if cfg.backend == "claude":
        return ClaudeBackendAdapter(
            cfg=cfg,
            vault_path=vault_path,
            db_path=db_path,
            config_path=config_path,
        )
    if cfg.backend == "codex":
        raise AgentBackendError(
            "Configured agent backend 'codex' is not implemented yet. "
            "Complete issue 11-5 before selecting it."
        )
    raise AgentBackendError(f"Unsupported agent backend: {cfg.backend}")

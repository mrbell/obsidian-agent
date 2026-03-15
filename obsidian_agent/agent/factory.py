from __future__ import annotations

from pathlib import Path

from obsidian_agent.agent.base import AgentWorker
from obsidian_agent.agent.claude import ClaudeBackendAdapter
from obsidian_agent.agent.codex import CodexBackendAdapter
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
        return CodexBackendAdapter(
            cfg=cfg,
            vault_path=vault_path,
            db_path=db_path,
            config_path=config_path,
        )
    raise AgentBackendError(f"Unsupported agent backend: {cfg.backend}")

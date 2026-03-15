from __future__ import annotations

from pathlib import Path

from obsidian_agent.agent.claude import ClaudeBackendAdapter
from obsidian_agent.agent.codex import CodexBackendAdapter
from obsidian_agent.agent.factory import build_agent_worker
from obsidian_agent.config import AgentConfig


def _cfg(tmp_path: Path, backend: str) -> AgentConfig:
    return AgentConfig(
        backend=backend,
        command="agent-cli",
        args=[],
        timeout_seconds=30,
        work_dir=tmp_path / "workdir",
    )


def test_factory_builds_claude_adapter(tmp_path: Path) -> None:
    worker = build_agent_worker(
        _cfg(tmp_path, "claude"),
        vault_path=tmp_path / "vault",
        db_path=tmp_path / "index.duckdb",
    )
    assert isinstance(worker, ClaudeBackendAdapter)


def test_factory_builds_codex_adapter(tmp_path: Path) -> None:
    worker = build_agent_worker(
        _cfg(tmp_path, "codex"),
        vault_path=tmp_path / "vault",
        db_path=tmp_path / "index.duckdb",
    )
    assert isinstance(worker, CodexBackendAdapter)

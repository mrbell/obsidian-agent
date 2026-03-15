from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml
from unittest.mock import MagicMock
from typer.testing import CliRunner

from obsidian_agent.cli import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_config(tmp_path: Path, *, with_agent: bool = True) -> Path:
    vault = tmp_path / "vault"
    vault.mkdir()
    cfg: dict = {
        "paths": {
            "vault": str(vault),
            "outbox": str(tmp_path / "outbox"),
            "state_dir": str(tmp_path / "state"),
            "bot_inbox_rel": "BotInbox",
        },
        "cache": {"duckdb_path": str(tmp_path / "index.duckdb")},
    }
    if with_agent:
        cfg["agent"] = {
            "backend": "claude",
            "command": sys.executable,
            # Emit a valid --output-format json result object
            "args": [
                "-c",
                f"import json; print(json.dumps({{'type':'result','is_error':False,'result':'READY'}}))",
            ],
            "timeout_seconds": 10,
            "work_dir": str(tmp_path / "workdir"),
        }
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.dump(cfg))
    return cfg_path


def _write_fake_codex(tmp_path: Path) -> Path:
    script = tmp_path / "fake-codex.py"
    script.write_text(
        """#!/usr/bin/env python3
import pathlib
import sys

args = sys.argv[1:]
output_path = None
for idx, arg in enumerate(args[:-1]):
    if arg in {"-o", "--output-last-message"}:
        output_path = pathlib.Path(args[idx + 1])
if output_path is not None:
    if "NOTE_COUNT" in args[-1]:
        output_path.write_text("NOTE_COUNT: 1", encoding="utf-8")
    else:
        output_path.write_text("READY", encoding="utf-8")
""",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_agent_test_passes_when_worker_succeeds(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    result = runner.invoke(app, ["agent", "test", "--config", str(cfg)])
    assert result.exit_code == 0
    assert "PASS" in result.output


def test_agent_test_shows_output(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    result = runner.invoke(app, ["agent", "test", "--config", str(cfg)])
    assert "READY" in result.output


def test_agent_test_fails_when_command_not_found(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.dump({
        "paths": {
            "vault": str(vault),
            "outbox": str(tmp_path / "outbox"),
            "state_dir": str(tmp_path / "state"),
            "bot_inbox_rel": "BotInbox",
        },
        "cache": {"duckdb_path": str(tmp_path / "index.duckdb")},
        "agent": {
            "backend": "claude",
            "command": "no-such-command-xyz",
            "args": [],
            "timeout_seconds": 5,
            "work_dir": str(tmp_path),
        },
    }))
    result = runner.invoke(app, ["agent", "test", "--config", str(cfg_path)])
    assert result.exit_code == 1
    assert "FAIL" in result.output


def test_agent_test_fails_without_agent_config(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path, with_agent=False)
    result = runner.invoke(app, ["agent", "test", "--config", str(cfg)])
    assert result.exit_code == 1
    assert "agent" in result.output.lower()


def test_agent_test_uses_backend_factory(monkeypatch, tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)

    worker = MagicMock()
    worker.backend.backend_id = "claude"
    worker.backend.capabilities.mcp = True
    worker.run.return_value = json.loads('{"returncode": 0, "output": "READY", "stderr": ""}')

    from obsidian_agent.agent.base import WorkerResult

    worker.run.return_value = WorkerResult(0, "READY", "", backend_id="claude")
    factory = MagicMock(return_value=worker)
    monkeypatch.setattr("obsidian_agent.cli.build_agent_worker", factory)

    result = runner.invoke(app, ["agent", "test", "--config", str(cfg)])

    assert result.exit_code == 0
    factory.assert_called_once()


def test_agent_test_passes_with_codex_backend(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    fake_codex = _write_fake_codex(tmp_path)
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.dump({
        "paths": {
            "vault": str(vault),
            "outbox": str(tmp_path / "outbox"),
            "state_dir": str(tmp_path / "state"),
            "bot_inbox_rel": "BotInbox",
        },
        "cache": {"duckdb_path": str(tmp_path / "index.duckdb")},
        "agent": {
            "backend": "codex",
            "command": str(fake_codex),
            "args": [],
            "timeout_seconds": 5,
            "work_dir": str(tmp_path),
        },
    }))
    result = runner.invoke(app, ["agent", "test", "--config", str(cfg_path)])
    assert result.exit_code == 0
    assert "PASS" in result.output

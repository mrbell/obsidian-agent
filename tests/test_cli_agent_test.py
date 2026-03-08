from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml
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

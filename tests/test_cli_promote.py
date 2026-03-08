from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from obsidian_agent.cli import app


runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write_config(tmp_path: Path) -> Path:
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
        "cache": {
            "duckdb_path": str(tmp_path / "index.duckdb"),
        },
    }))
    return cfg_path


def _write(path: Path, content: str = "# Note\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_promote_copies_artifact(tmp_path: Path) -> None:
    cfg = write_config(tmp_path)
    outbox = tmp_path / "outbox"
    _write(outbox / "task_notification" / "note.md")

    result = runner.invoke(app, ["promote", "--config", str(cfg)])

    assert result.exit_code == 0
    assert (tmp_path / "vault" / "BotInbox" / "task_notification" / "note.md").exists()
    assert "promoted" in result.output


def test_promote_exits_zero_when_nothing_to_promote(tmp_path: Path) -> None:
    cfg = write_config(tmp_path)

    result = runner.invoke(app, ["promote", "--config", str(cfg)])

    assert result.exit_code == 0
    assert "promoted" in result.output


def test_promote_dry_run_does_not_copy(tmp_path: Path) -> None:
    cfg = write_config(tmp_path)
    outbox = tmp_path / "outbox"
    _write(outbox / "task_notification" / "note.md")

    result = runner.invoke(app, ["promote", "--config", str(cfg), "--dry-run"])

    assert result.exit_code == 0
    assert not (tmp_path / "vault" / "BotInbox" / "task_notification" / "note.md").exists()
    assert "dry-run" in result.output


def test_promote_exits_nonzero_on_errors(tmp_path: Path) -> None:
    cfg = write_config(tmp_path)
    outbox = tmp_path / "outbox"
    bad = outbox / "task_notification" / "export.txt"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("not markdown")

    result = runner.invoke(app, ["promote", "--config", str(cfg)])

    assert result.exit_code == 1

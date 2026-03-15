from __future__ import annotations

import json
from pathlib import Path

from obsidian_agent.agent.codex import CodexBackendAdapter
from obsidian_agent.config import AgentConfig


def _make_fake_codex(tmp_path: Path) -> Path:
    script = tmp_path / "fake-codex.py"
    script.write_text(
        """#!/usr/bin/env python3
import json
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
print(json.dumps(args))
""",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def _make_worker(tmp_path: Path, args: list[str] | None = None) -> CodexBackendAdapter:
    cfg = AgentConfig(
        backend="codex",
        command=str(_make_fake_codex(tmp_path)),
        args=args or [],
        timeout_seconds=5,
        work_dir=tmp_path / "workdir",
    )
    return CodexBackendAdapter(
        cfg=cfg,
        vault_path=tmp_path / "vault",
        db_path=tmp_path / "index.duckdb",
        config_path=tmp_path / "config.yaml",
    )


class TestBasicExecution:
    def test_reads_output_from_output_file(self, tmp_path: Path) -> None:
        worker = _make_worker(tmp_path)
        result = worker.run("Say READY and nothing else.", with_mcp=False)
        assert result.returncode == 0
        assert result.output == "READY"
        assert result.backend_id == "codex"
        assert result.model_version == "codex/gpt-5.4"

    def test_backend_metadata_uses_explicit_model_arg(self, tmp_path: Path) -> None:
        worker = _make_worker(tmp_path, args=["--model", "gpt-5-mini"])
        assert worker.backend.model_version == "codex/gpt-5-mini"


class TestCommandShape:
    def test_includes_exec_defaults(self, tmp_path: Path) -> None:
        worker = _make_worker(tmp_path)
        result = worker.run("Say READY and nothing else.", with_mcp=False)
        args = json.loads(result.stderr)
        assert "exec" in args
        assert "--skip-git-repo-check" in args
        assert "--ephemeral" in args
        assert "--sandbox" in args
        assert "read-only" in args
        assert "-a" in args
        assert "never" in args

    def test_web_search_adds_top_level_flag(self, tmp_path: Path) -> None:
        worker = _make_worker(tmp_path)
        result = worker.run("Say READY and nothing else.", web_search=True, with_mcp=False)
        args = json.loads(result.stderr)
        assert "--search" in args

    def test_with_mcp_adds_mcp_overrides(self, tmp_path: Path) -> None:
        worker = _make_worker(tmp_path)
        result = worker.run("Call NOTE_COUNT", with_mcp=True)
        args = json.loads(result.stderr)
        assert args.count("-c") == 3
        assert any("mcp_servers.obsidian.command" in arg for arg in args)
        assert any("mcp_servers.obsidian.args" in arg for arg in args)
        assert any("mcp_servers.obsidian.required=true" in arg for arg in args)

    def test_without_mcp_omits_mcp_overrides(self, tmp_path: Path) -> None:
        worker = _make_worker(tmp_path)
        result = worker.run("Say READY", with_mcp=False)
        args = json.loads(result.stderr)
        assert not any("mcp_servers.obsidian" in arg for arg in args)

    def test_preserves_existing_exec_subcommand(self, tmp_path: Path) -> None:
        worker = _make_worker(
            tmp_path,
            args=["--model", "gpt-5", "exec", "--sandbox", "workspace-write"],
        )
        result = worker.run("Say READY", with_mcp=False)
        args = json.loads(result.stderr)
        assert args.count("exec") == 1
        assert "--model" in args
        assert "gpt-5" in args
        assert args.count("--sandbox") == 1


class TestMcpValidation:
    def test_with_mcp_requires_config_path(self, tmp_path: Path) -> None:
        cfg = AgentConfig(
            backend="codex",
            command=str(_make_fake_codex(tmp_path)),
            args=[],
            timeout_seconds=5,
            work_dir=tmp_path / "workdir",
        )
        worker = CodexBackendAdapter(
            cfg=cfg,
            vault_path=tmp_path / "vault",
            db_path=tmp_path / "index.duckdb",
            config_path=None,
        )
        try:
            worker.run("Say READY", with_mcp=True)
        except ValueError as exc:
            assert "config_path" in str(exc)
        else:
            raise AssertionError("Expected missing config_path to raise")

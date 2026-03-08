from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from obsidian_agent.agent.worker import ClaudeCodeWorker, WorkerResult
from obsidian_agent.config import AgentConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_worker(tmp_path: Path, command: str, args: list[str] | None = None) -> ClaudeCodeWorker:
    cfg = AgentConfig(
        command=command,
        args=args or [],
        timeout_seconds=5,
        work_dir=tmp_path / "workdir",
    )
    return ClaudeCodeWorker(
        cfg=cfg,
        vault_path=tmp_path / "vault",
        db_path=tmp_path / "index.duckdb",
    )


def _json_result(text: str) -> str:
    """Produce a fake --output-format json response."""
    return json.dumps({"type": "result", "is_error": False, "result": text})


# ---------------------------------------------------------------------------
# Basic execution
# ---------------------------------------------------------------------------

class TestBasicExecution:
    def test_captures_stdout(self, tmp_path: Path) -> None:
        worker = _make_worker(tmp_path, sys.executable, ["-c", "import sys; print('hello')"])
        result = worker.run("ignored", with_mcp=False)
        assert result.returncode == 0
        # Raw stdout is returned when not valid JSON
        assert "hello" in result.output

    def test_json_output_extracted(self, tmp_path: Path) -> None:
        response = _json_result("the model response")
        # Use python to emit the JSON result
        worker = _make_worker(
            tmp_path,
            sys.executable,
            ["-c", f"print({response!r})"],
        )
        result = worker.run("ignored", with_mcp=False)
        assert result.output == "the model response"

    def test_nonzero_exit_returned(self, tmp_path: Path) -> None:
        worker = _make_worker(tmp_path, sys.executable, ["-c", "import sys; sys.exit(1)"])
        result = worker.run("ignored", with_mcp=False)
        assert result.returncode == 1

    def test_stderr_captured(self, tmp_path: Path) -> None:
        worker = _make_worker(
            tmp_path,
            sys.executable,
            ["-c", "import sys; sys.stderr.write('err msg\\n')"],
        )
        result = worker.run("ignored", with_mcp=False)
        assert "err msg" in result.stderr


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------

class TestTimeout:
    def test_timeout_returns_nonzero(self, tmp_path: Path) -> None:
        cfg = AgentConfig(
            command=sys.executable,
            args=["-c", "import time; time.sleep(60)"],
            timeout_seconds=1,
            work_dir=tmp_path,
        )
        worker = ClaudeCodeWorker(cfg=cfg, vault_path=tmp_path, db_path=tmp_path)
        result = worker.run("ignored", with_mcp=False)
        assert result.returncode != 0
        assert "timeout" in result.stderr.lower()

    def test_timeout_output_is_empty(self, tmp_path: Path) -> None:
        cfg = AgentConfig(
            command=sys.executable,
            args=["-c", "import time; time.sleep(60)"],
            timeout_seconds=1,
            work_dir=tmp_path,
        )
        worker = ClaudeCodeWorker(cfg=cfg, vault_path=tmp_path, db_path=tmp_path)
        result = worker.run("ignored", with_mcp=False)
        assert result.output == ""


# ---------------------------------------------------------------------------
# Command not found
# ---------------------------------------------------------------------------

class TestCommandNotFound:
    def test_missing_command_returns_nonzero(self, tmp_path: Path) -> None:
        worker = _make_worker(tmp_path, "no-such-command-xyz")
        result = worker.run("ignored", with_mcp=False)
        assert result.returncode != 0

    def test_missing_command_stderr_describes_error(self, tmp_path: Path) -> None:
        worker = _make_worker(tmp_path, "no-such-command-xyz")
        result = worker.run("ignored", with_mcp=False)
        assert "no-such-command-xyz" in result.stderr


# ---------------------------------------------------------------------------
# MCP config file
# ---------------------------------------------------------------------------

class TestMcpConfig:
    def test_with_mcp_passes_mcp_config_flag(self, tmp_path: Path) -> None:
        # Command that prints its argv so we can inspect flags
        worker = _make_worker(
            tmp_path,
            sys.executable,
            ["-c", "import sys, json; print(json.dumps(sys.argv[1:]))"],
        )
        result = worker.run("myprompt", with_mcp=True)
        args = json.loads(result.output)
        assert "--mcp-config" in args

    def test_without_mcp_no_mcp_config_flag(self, tmp_path: Path) -> None:
        worker = _make_worker(
            tmp_path,
            sys.executable,
            ["-c", "import sys, json; print(json.dumps(sys.argv[1:]))"],
        )
        result = worker.run("myprompt", with_mcp=False)
        args = json.loads(result.output)
        assert "--mcp-config" not in args

    def test_mcp_config_file_cleaned_up(self, tmp_path: Path) -> None:
        # Capture the mcp config path from argv, then check it's gone after run
        worker = _make_worker(
            tmp_path,
            sys.executable,
            ["-c", "import sys, json; print(json.dumps(sys.argv[1:]))"],
        )
        result = worker.run("myprompt", with_mcp=True)
        args = json.loads(result.output)
        idx = args.index("--mcp-config")
        mcp_path = Path(args[idx + 1])
        assert not mcp_path.exists()


# ---------------------------------------------------------------------------
# Web search flag
# ---------------------------------------------------------------------------

class TestWebSearch:
    def test_web_search_false_adds_disallowed_tools(self, tmp_path: Path) -> None:
        worker = _make_worker(
            tmp_path,
            sys.executable,
            ["-c", "import sys, json; print(json.dumps(sys.argv[1:]))"],
        )
        result = worker.run("myprompt", web_search=False, with_mcp=False)
        args = json.loads(result.output)
        assert "--disallowed-tools" in args
        assert "WebSearch" in args
        assert "WebFetch" in args

    def test_web_search_true_no_disallowed_tools(self, tmp_path: Path) -> None:
        worker = _make_worker(
            tmp_path,
            sys.executable,
            ["-c", "import sys, json; print(json.dumps(sys.argv[1:]))"],
        )
        result = worker.run("myprompt", web_search=True, with_mcp=False)
        args = json.loads(result.output)
        assert "--disallowed-tools" not in args


# ---------------------------------------------------------------------------
# Temp dir cleanup
# ---------------------------------------------------------------------------

class TestCleanup:
    def test_working_dir_cleaned_up(self, tmp_path: Path) -> None:
        # Track temp dirs before and after
        import glob
        before = set(glob.glob("/tmp/obsidian-agent-worker-*"))
        worker = _make_worker(tmp_path, sys.executable, ["-c", "pass"])
        worker.run("ignored", with_mcp=False)
        after = set(glob.glob("/tmp/obsidian-agent-worker-*"))
        # No new dirs should remain
        assert not (after - before)

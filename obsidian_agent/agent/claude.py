from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from obsidian_agent.agent.base import AgentBackend, AgentCapabilities, WorkerResult
from obsidian_agent.config import AgentConfig

log = logging.getLogger(__name__)

# MCP server name as declared in the mcpServers config written by this worker.
_MCP_SERVER = "obsidian-vault"

# All tools exposed by the obsidian-vault MCP server. Must be listed explicitly
# in --allowedTools; wildcards (mcp__server__*) have a known Claude Code bug where
# they silently fail. Update this list when tools are added or removed in mcp/server.py.
_MCP_TOOLS = [
    "search_notes", "get_note", "list_notes", "get_daily_notes",
    "query_tasks", "get_note_links", "find_notes_by_tag", "get_vault_stats",
    "search_similar", "get_note_summary", "find_related_notes", "list_concepts",
    "search_by_concept", "get_entity_context", "get_recent_concepts",
    "get_stale_concepts", "fetch_feed", "get_implicit_items",
    "get_unlinked_related_notes",
]
_MCP_ALLOWED = ",".join(f"mcp__{_MCP_SERVER}__{t}" for t in _MCP_TOOLS)
_DEFAULT_MODEL_VERSION = "claude/claude-sonnet-4-6"


@dataclass
class ClaudeBackendAdapter:
    """Invoke Claude Code headlessly with the vault MCP server registered."""

    cfg: AgentConfig
    vault_path: Path
    db_path: Path
    config_path: Path | None = None

    @property
    def backend(self) -> AgentBackend:
        return AgentBackend(
            backend_id="claude",
            model_version=_model_version_from_args(self.cfg.args),
            capabilities=AgentCapabilities(
                mcp=True,
                web_search=True,
                structured_output=True,
            ),
        )

    def run(
        self,
        prompt: str,
        *,
        web_search: bool = False,
        with_mcp: bool = True,
    ) -> WorkerResult:
        tmp_dir = Path(tempfile.mkdtemp(prefix="obsidian-agent-worker-"))

        try:
            cmd = [self.cfg.command, *self.cfg.args]

            if with_mcp:
                mcp_args = ["mcp"]
                if self.config_path:
                    mcp_args += ["--config", str(self.config_path)]
                mcp_config = {
                    "mcpServers": {
                        "obsidian-vault": {
                            "command": str(_find_mcp_binary()),
                            "args": mcp_args,
                        }
                    }
                }
                mcp_config_path = tmp_dir / f"{uuid.uuid4().hex}-mcp.json"
                mcp_config_path.write_text(
                    json.dumps(mcp_config, indent=2), encoding="utf-8"
                )
                cmd += ["--mcp-config", str(mcp_config_path)]

            if web_search and with_mcp:
                cmd += ["--allowedTools", f"WebSearch,WebFetch,{_MCP_ALLOWED}"]
            elif web_search:
                cmd += ["--allowedTools", "WebSearch,WebFetch"]
            elif with_mcp:
                cmd += ["--allowedTools", _MCP_ALLOWED]
            else:
                cmd += ["--disallowed-tools", "WebSearch", "WebFetch"]

            cmd += ["--", prompt]

            log.info(
                "Running Claude backend. command=%s web_search=%s with_mcp=%s",
                self.cfg.command,
                web_search,
                with_mcp,
            )
            log.debug("Full command: %s", cmd)

            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=str(tmp_dir),
                    timeout=self.cfg.timeout_seconds,
                )
            except subprocess.TimeoutExpired as exc:
                log.error(
                    "Claude backend timed out after %ds. command=%s",
                    self.cfg.timeout_seconds,
                    self.cfg.command,
                )
                stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
                return WorkerResult(
                    returncode=1,
                    output="",
                    stderr=f"timeout: {stderr}",
                    backend_id=self.backend.backend_id,
                    model_version=self.backend.model_version,
                )
            except FileNotFoundError:
                log.error("Claude backend command not found: %s", self.cfg.command)
                return WorkerResult(
                    returncode=1,
                    output="",
                    stderr=f"command not found: {self.cfg.command}",
                    backend_id=self.backend.backend_id,
                    model_version=self.backend.model_version,
                )

            if proc.returncode != 0:
                log.error(
                    "Claude backend exited %d. stderr=%s",
                    proc.returncode,
                    proc.stderr[:500],
                )

            output = _extract_output(proc.stdout)
            return WorkerResult(
                returncode=proc.returncode,
                output=output,
                stderr=proc.stderr,
                backend_id=self.backend.backend_id,
                model_version=self.backend.model_version,
            )

        finally:
            _cleanup(tmp_dir)


def _model_version_from_args(args: list[str]) -> str:
    for idx, arg in enumerate(args[:-1]):
        if arg == "--model":
            return f"claude/{args[idx + 1]}"
    return _DEFAULT_MODEL_VERSION


def _find_mcp_binary() -> Path:
    """Resolve the absolute path to the obsidian-agent binary for the MCP config."""
    venv_candidate = Path(sys.executable).parent / "obsidian-agent"
    if venv_candidate.exists():
        return venv_candidate
    on_path = shutil.which("obsidian-agent")
    if on_path:
        return Path(on_path)
    return Path("obsidian-agent")


def _extract_output(stdout: str) -> str:
    """Extract the model response text from --output-format json stdout."""
    if not stdout.strip():
        return ""
    try:
        data = json.loads(stdout)
        if isinstance(data, dict):
            if data.get("is_error"):
                log.error(
                    "Claude backend returned is_error=true. result=%r",
                    data.get("result", "")[:300],
                )
            return data.get("result", "") or ""
    except json.JSONDecodeError:
        pass
    log.warning(
        "Claude backend stdout was not valid JSON result object; using raw output. stdout[:200]=%r",
        stdout[:200],
    )
    return stdout


def _cleanup(path: Path) -> None:
    """Remove a temp directory tree, ignoring errors."""
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass

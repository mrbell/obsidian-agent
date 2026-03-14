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

from obsidian_agent.config import AgentConfig

log = logging.getLogger(__name__)

# MCP server name as declared in the mcpServers config written by this worker.
_MCP_SERVER = "obsidian-vault"

# All tools exposed by the obsidian-vault MCP server.  Must be listed explicitly
# in --allowedTools; wildcards (mcp__server__*) have a known Claude Code bug where
# they silently fail.  Update this list when tools are added or removed in mcp/server.py.
_MCP_TOOLS = [
    "search_notes", "get_note", "list_notes", "get_daily_notes",
    "query_tasks", "get_note_links", "find_notes_by_tag", "get_vault_stats",
    "search_similar", "get_note_summary", "find_related_notes", "list_concepts",
    "search_by_concept", "get_entity_context", "get_recent_concepts",
    "get_stale_concepts", "fetch_feed", "get_implicit_items",
]
_MCP_ALLOWED = ",".join(f"mcp__{_MCP_SERVER}__{t}" for t in _MCP_TOOLS)


@dataclass(frozen=True)
class WorkerResult:
    returncode: int
    output: str   # model response text (parsed from --output-format json)
    stderr: str


@dataclass
class ClaudeCodeWorker:
    """Invokes Claude Code headlessly with the vault MCP server registered.

    Uses stdlib only (subprocess, tempfile, pathlib) — no project imports
    beyond config types.
    """
    cfg: AgentConfig
    vault_path: Path
    db_path: Path
    config_path: Path | None = None

    def run(
        self,
        prompt: str,
        *,
        web_search: bool = False,
        with_mcp: bool = True,
    ) -> WorkerResult:
        """Run Claude Code with the given prompt.

        Args:
            prompt: The task description to pass to Claude Code.
            web_search: If False, explicitly disables WebSearch and WebFetch.
            with_mcp: If False, skips MCP server registration (used for smoke tests).
        """
        tmp_dir = Path(tempfile.mkdtemp(prefix="obsidian-agent-worker-"))
        mcp_config_path: Path | None = None

        try:
            # Build command from configured base args
            cmd = [self.cfg.command, *self.cfg.args]

            # MCP server config
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

            # In headless mode there is no user to approve permission prompts.
            # --allowedTools creates an explicit allowlist (MCP tools are always
            # included when this flag is used).  --disallowed-tools blocks specific
            # tools but leaves everything else requiring permission — which in headless
            # mode means MCP tools also get blocked.  So: use --allowedTools whenever
            # MCP is active; only fall back to --disallowed-tools for pure non-MCP runs.
            if web_search and with_mcp:
                cmd += ["--allowedTools", f"WebSearch,WebFetch,{_MCP_ALLOWED}"]
            elif web_search:
                cmd += ["--allowedTools", "WebSearch,WebFetch"]
            elif with_mcp:
                cmd += ["--allowedTools", _MCP_ALLOWED]
            else:
                cmd += ["--disallowed-tools", "WebSearch", "WebFetch"]

            # Terminate option parsing before the prompt so variadic flags
            # (e.g. --disallowed-tools <tools...>) don't consume it.
            cmd += ["--", prompt]

            log.info(
                "Running worker. command=%s web_search=%s with_mcp=%s",
                self.cfg.command, web_search, with_mcp,
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
                    "Worker timed out after %ds. command=%s",
                    self.cfg.timeout_seconds, self.cfg.command,
                )
                stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
                return WorkerResult(returncode=1, output="", stderr=f"timeout: {stderr}")
            except FileNotFoundError:
                log.error("Worker command not found: %s", self.cfg.command)
                return WorkerResult(
                    returncode=1,
                    output="",
                    stderr=f"command not found: {self.cfg.command}",
                )

            if proc.returncode != 0:
                log.error(
                    "Worker exited %d. stderr=%s", proc.returncode, proc.stderr[:500]
                )

            output = _extract_output(proc.stdout)
            return WorkerResult(
                returncode=proc.returncode,
                output=output,
                stderr=proc.stderr,
            )

        finally:
            _cleanup(tmp_dir)


def _find_mcp_binary() -> Path:
    """Resolve the absolute path to the obsidian-agent binary for the MCP config.

    Prefers the binary sitting next to the current Python interpreter (i.e.
    inside the active venv), then falls back to PATH.  Using an absolute path
    here is critical because the MCP subprocess is spawned by Claude Code in
    an environment where cron's minimal PATH may not include the venv bin dir.
    """
    venv_candidate = Path(sys.executable).parent / "obsidian-agent"
    if venv_candidate.exists():
        return venv_candidate
    on_path = shutil.which("obsidian-agent")
    if on_path:
        return Path(on_path)
    # Last resort: let the shell resolve it; will likely fail in cron but
    # produces a clearer error than a silent MCP startup failure.
    return Path("obsidian-agent")


def _extract_output(stdout: str) -> str:
    """Extract the model response text from --output-format json stdout.

    Falls back to the raw stdout if the JSON cannot be parsed, so the
    worker stays functional even if the output format changes.
    """
    if not stdout.strip():
        return ""
    try:
        data = json.loads(stdout)
        if isinstance(data, dict):
            if data.get("is_error"):
                log.error("Worker returned is_error=true. result=%r", data.get("result", "")[:300])
            return data.get("result", "") or ""
        # Valid JSON but not the expected object shape — fall through to raw
    except json.JSONDecodeError:
        pass
    log.warning("Worker stdout was not valid JSON result object; using raw output. stdout[:200]=%r", stdout[:200])
    return stdout


def _cleanup(path: Path) -> None:
    """Remove a temp directory tree, ignoring errors."""
    try:
        import shutil
        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass

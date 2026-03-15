from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from obsidian_agent.agent.base import AgentBackend, AgentCapabilities, WorkerResult
from obsidian_agent.config import AgentConfig

log = logging.getLogger(__name__)

_DEFAULT_MODEL_VERSION = "codex/gpt-5.4"


@dataclass
class CodexBackendAdapter:
    """Invoke Codex non-interactively with per-run MCP configuration."""

    cfg: AgentConfig
    vault_path: Path
    db_path: Path
    config_path: Path | None = None

    @property
    def backend(self) -> AgentBackend:
        return AgentBackend(
            backend_id="codex",
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
        output_path = tmp_dir / "codex-last-message.txt"

        try:
            cmd = _build_codex_command(
                self.cfg,
                prompt=prompt,
                output_path=output_path,
                config_path=self.config_path,
                web_search=web_search,
                with_mcp=with_mcp,
            )

            log.info(
                "Running Codex backend. command=%s web_search=%s with_mcp=%s",
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
                    "Codex backend timed out after %ds. command=%s",
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
                log.error("Codex backend command not found: %s", self.cfg.command)
                return WorkerResult(
                    returncode=1,
                    output="",
                    stderr=f"command not found: {self.cfg.command}",
                    backend_id=self.backend.backend_id,
                    model_version=self.backend.model_version,
                )

            output = _extract_output(proc.stdout, output_path)
            if proc.returncode != 0:
                log.error(
                    "Codex backend exited %d. stderr=%s stdout=%s",
                    proc.returncode,
                    proc.stderr[:500],
                    proc.stdout[:500],
                )

            return WorkerResult(
                returncode=proc.returncode,
                output=output,
                stderr=proc.stderr or proc.stdout,
                backend_id=self.backend.backend_id,
                model_version=self.backend.model_version,
            )
        finally:
            _cleanup(tmp_dir)


def _build_codex_command(
    cfg: AgentConfig,
    *,
    prompt: str,
    output_path: Path,
    config_path: Path | None,
    web_search: bool,
    with_mcp: bool,
) -> list[str]:
    pre_exec, exec_args = _split_exec_args(cfg.args)
    pre_exec = _without_arg_pair(pre_exec, {"-a", "--ask-for-approval"})
    exec_args = _without_arg_pair(exec_args, {"-o", "--output-last-message"})

    cmd = [cfg.command, *pre_exec]
    if web_search and "--search" not in pre_exec:
        cmd.append("--search")
    cmd += ["-a", "never", "exec"]
    cmd += _ensure_exec_defaults(exec_args)
    cmd += ["-o", str(output_path)]

    if with_mcp:
        if config_path is None:
            raise ValueError("Codex backend requires config_path when with_mcp=True")
        cmd += [
            "-c", 'mcp_servers.obsidian.command="uv"',
            "-c", (
                "mcp_servers.obsidian.args="
                f'["run","obsidian-agent","mcp","--config","{config_path}"]'
            ),
            "-c", "mcp_servers.obsidian.required=true",
        ]

    cmd.append(prompt)
    return cmd


def _split_exec_args(args: list[str]) -> tuple[list[str], list[str]]:
    if "exec" in args:
        idx = args.index("exec")
        return list(args[:idx]), list(args[idx + 1 :])
    return [], list(args)


def _ensure_exec_defaults(args: list[str]) -> list[str]:
    out = list(args)
    if "--sandbox" not in out and "-s" not in out:
        out = ["--sandbox", "read-only", *out]
    if "--ephemeral" not in out:
        out = ["--ephemeral", *out]
    if "--skip-git-repo-check" not in out:
        out = ["--skip-git-repo-check", *out]
    return out


def _without_arg_pair(args: list[str], option_names: set[str]) -> list[str]:
    result: list[str] = []
    skip_next = False
    for arg in args:
        if skip_next:
            skip_next = False
            continue
        if arg in option_names:
            skip_next = True
            continue
        result.append(arg)
    return result


def _model_version_from_args(args: list[str]) -> str:
    for idx, arg in enumerate(args[:-1]):
        if arg in {"--model", "-m"}:
            return f"codex/{args[idx + 1]}"
    return _DEFAULT_MODEL_VERSION


def _extract_output(stdout: str, output_path: Path) -> str:
    if output_path.exists():
        return output_path.read_text(encoding="utf-8").strip()
    return stdout.strip()


def _cleanup(path: Path) -> None:
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass

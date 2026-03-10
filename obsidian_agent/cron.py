"""Cron entry management for obsidian-agent scheduled jobs.

Managed entries are bracketed with BEGIN/END markers so that reinstalling
replaces rather than appends. Entries outside the markers are untouched.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from obsidian_agent.config import Config

_BEGIN = "### BEGIN obsidian-agent — do not edit this section manually ###"
_END = "### END obsidian-agent ###"


# ---------------------------------------------------------------------------
# Binary discovery
# ---------------------------------------------------------------------------

def find_binary() -> Path:
    """Return the absolute path to the obsidian-agent binary.

    Looks in the same bin directory as the current Python interpreter
    (i.e. inside the active virtual environment), then falls back to
    searching PATH via shutil.which.

    Raises FileNotFoundError if the binary cannot be located.
    """
    import shutil

    venv_candidate = Path(sys.executable).parent / "obsidian-agent"
    if venv_candidate.exists():
        return venv_candidate

    on_path = shutil.which("obsidian-agent")
    if on_path:
        return Path(on_path)

    raise FileNotFoundError(
        "obsidian-agent binary not found. "
        "Ensure the package is installed in the active environment."
    )


# ---------------------------------------------------------------------------
# Crontab read / write
# ---------------------------------------------------------------------------

def get_crontab() -> str:
    """Return the current user crontab, or '' if none exists."""
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if result.returncode != 0:
        return ""
    return result.stdout


def set_crontab(content: str) -> None:
    """Write content as the user's crontab."""
    subprocess.run(["crontab", "-"], input=content, text=True, check=True)


# ---------------------------------------------------------------------------
# Section management
# ---------------------------------------------------------------------------

def remove_managed_section(crontab: str) -> str:
    """Return crontab with the obsidian-agent managed section removed."""
    lines = crontab.splitlines(keepends=True)
    result = []
    inside = False
    for line in lines:
        stripped = line.rstrip()
        if stripped == _BEGIN:
            inside = True
            continue
        if stripped == _END:
            inside = False
            continue
        if not inside:
            result.append(line)
    return "".join(result)


def build_managed_section(
    config: Config,
    config_path: Path,
    binary: Path,
) -> str:
    """Build the obsidian-agent managed crontab section from config.

    Each job entry runs ``index`` first (fast, ensures structural freshness),
    then the job itself. The nightly ``index-semantic`` runs on its own
    schedule after the structural index.
    """
    log_dir = config.paths.state_dir
    cmd = str(binary)
    cfg_flag = f"--config {config_path}"

    lines = [_BEGIN, ""]

    # Structural index
    lines.append(f"# structural index")
    lines.append(
        f"{config.indexing.schedule} "
        f"{cmd} index {cfg_flag} "
        f">> {log_dir}/index.log 2>&1"
    )
    lines.append("")

    # Semantic index
    lines.append(f"# semantic index (embeddings + concept extraction)")
    lines.append(
        f"{config.indexing.semantic_schedule} "
        f"{cmd} index-semantic {cfg_flag} "
        f">> {log_dir}/index-semantic.log 2>&1"
    )

    # Jobs
    for job_name, job_cfg in _enabled_jobs(config):
        lines.append("")
        lines.append(f"# {job_name}")
        lines.append(
            f"{job_cfg.schedule} "
            f"{cmd} index {cfg_flag} && "
            f"{cmd} run {job_name} {cfg_flag} "
            f">> {log_dir}/{job_name}.log 2>&1"
        )

    lines.append("")
    lines.append(_END)
    return "\n".join(lines) + "\n"


def _enabled_jobs(config: Config) -> list[tuple[str, object]]:
    """Return (job_name, job_cfg) pairs for all enabled jobs."""
    jobs = config.jobs
    candidates = [
        ("task_notification", jobs.task_notification),
        ("research_digest", jobs.research_digest),
        ("vault_connections_report", jobs.vault_connections_report),
        ("vault_hygiene_report", jobs.vault_hygiene_report),
    ]
    return [(name, cfg) for name, cfg in candidates if cfg.enabled]


# ---------------------------------------------------------------------------
# Install / uninstall
# ---------------------------------------------------------------------------

def install(config: Config, config_path: Path, binary: Path) -> str:
    """Install managed cron entries. Returns the new full crontab string."""
    existing = get_crontab()
    cleaned = remove_managed_section(existing).rstrip()
    section = build_managed_section(config, config_path, binary)
    new_crontab = (cleaned + "\n\n" + section) if cleaned else section
    set_crontab(new_crontab)
    return new_crontab


def uninstall() -> str:
    """Remove managed cron entries. Returns the new full crontab string."""
    existing = get_crontab()
    new_crontab = remove_managed_section(existing).rstrip() + "\n"
    set_crontab(new_crontab)
    return new_crontab

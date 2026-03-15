import pytest
import yaml
from pathlib import Path

from obsidian_agent.config import (
    load_config,
    Config,
    ConfigError,
    AgentConfig,
    SmtpConfig,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write_config(path: Path, data: dict) -> Path:
    cfg = path / "config.yaml"
    cfg.write_text(yaml.dump(data))
    return cfg


def minimal_raw(vault: Path, tmp: Path) -> dict:
    """Minimal valid config dict — no optional sections."""
    return {
        "paths": {
            "vault": str(vault),
            "outbox": str(tmp / "outbox"),
            "state_dir": str(tmp / "state"),
            "bot_inbox_rel": "BotInbox",
        },
        "cache": {
            "duckdb_path": str(tmp / "index.duckdb"),
        },
    }


@pytest.fixture()
def vault(tmp_path: Path) -> Path:
    v = tmp_path / "vault"
    v.mkdir()
    return v


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    """A temp directory outside the vault for outbox/state."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_minimal_config_loads(vault: Path, workspace: Path, tmp_path: Path) -> None:
    cfg_file = write_config(tmp_path, minimal_raw(vault, workspace))
    cfg = load_config(cfg_file)

    assert cfg.paths.vault == vault.resolve()
    assert cfg.paths.bot_inbox_rel == "BotInbox"
    assert cfg.delivery.email is None
    assert cfg.agent is None
    # defaults
    assert cfg.jobs.task_notification.lookahead_days == 3
    assert cfg.jobs.research_digest.topics == []


def test_full_config_loads(vault: Path, workspace: Path, tmp_path: Path) -> None:
    raw = minimal_raw(vault, workspace)
    raw["delivery"] = {
        "email": {
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 587,
            "username": "me@gmail.com",
            "password_env": "MY_SMTP_PASSWORD",
            "from_address": "me@gmail.com",
            "to_address": "me@gmail.com",
        }
    }
    raw["agent"] = {
        "backend": "claude",
        "command": "claude",
        "args": ["--print"],
        "timeout_seconds": 600,
        "work_dir": str(workspace / "workdir"),
    }
    raw["jobs"] = {
        "task_notification": {
            "enabled": True,
            "lookahead_days": 5,
            "notify_if_empty": True,
        },
        "research_digest": {
            "topics": ["agentic coding", "llms"],
            "lookback_days": 14,
        },
    }
    cfg = load_config(write_config(tmp_path, raw))

    assert isinstance(cfg.delivery.email, SmtpConfig)
    assert cfg.delivery.email.smtp_host == "smtp.gmail.com"
    assert cfg.delivery.email.smtp_port == 587
    assert cfg.delivery.email.password_env == "MY_SMTP_PASSWORD"

    assert isinstance(cfg.agent, AgentConfig)
    assert cfg.agent.backend == "claude"
    assert cfg.agent.command == "claude"
    assert cfg.agent.args == ["--print"]
    assert cfg.agent.timeout_seconds == 600

    assert cfg.jobs.task_notification.lookahead_days == 5
    assert cfg.jobs.task_notification.notify_if_empty is True
    from obsidian_agent.config import ResearchTopic
    assert cfg.jobs.research_digest.topics == [
        ResearchTopic(name="agentic coding"),
        ResearchTopic(name="llms"),
    ]
    assert cfg.jobs.research_digest.lookback_days == 14


def test_tilde_paths_are_resolved(vault: Path, workspace: Path, tmp_path: Path) -> None:
    raw = minimal_raw(vault, workspace)
    # Replace outbox with a ~ path pointing somewhere valid-ish
    # We can't guarantee ~ expands to a specific place, so just verify
    # the returned path has no tilde in it.
    cfg = load_config(write_config(tmp_path, raw))
    assert "~" not in str(cfg.paths.outbox)
    assert "~" not in str(cfg.paths.state_dir)
    assert "~" not in str(cfg.cache.duckdb_path)


def test_jobs_defaults_when_section_absent(vault: Path, workspace: Path, tmp_path: Path) -> None:
    cfg = load_config(write_config(tmp_path, minimal_raw(vault, workspace)))
    tn = cfg.jobs.task_notification
    rd = cfg.jobs.research_digest
    assert tn.enabled is True
    assert tn.lookahead_days == 3
    assert tn.include_overdue is True
    assert tn.notify_if_empty is False
    assert tn.also_write_vault_artifact is False
    assert rd.enabled is True
    assert rd.lookback_days == 7
    assert rd.also_notify is True


# ---------------------------------------------------------------------------
# File-level errors
# ---------------------------------------------------------------------------

def test_missing_config_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nonexistent.yaml")


def test_invalid_yaml_raises(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("key: [unclosed")
    with pytest.raises(ConfigError, match="parse"):
        load_config(cfg_file)


def test_non_mapping_yaml_raises(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("- just\n- a\n- list\n")
    with pytest.raises(ConfigError, match="mapping"):
        load_config(cfg_file)


# ---------------------------------------------------------------------------
# Missing required fields
# ---------------------------------------------------------------------------

def test_missing_paths_section_raises(vault: Path, workspace: Path, tmp_path: Path) -> None:
    raw = minimal_raw(vault, workspace)
    del raw["paths"]
    with pytest.raises(ConfigError, match="paths"):
        load_config(write_config(tmp_path, raw))


def test_missing_paths_vault_raises(vault: Path, workspace: Path, tmp_path: Path) -> None:
    raw = minimal_raw(vault, workspace)
    del raw["paths"]["vault"]
    with pytest.raises(ConfigError, match="paths.vault"):
        load_config(write_config(tmp_path, raw))


def test_missing_cache_section_raises(vault: Path, workspace: Path, tmp_path: Path) -> None:
    raw = minimal_raw(vault, workspace)
    del raw["cache"]
    with pytest.raises(ConfigError, match="cache"):
        load_config(write_config(tmp_path, raw))


def test_missing_cache_duckdb_path_raises(vault: Path, workspace: Path, tmp_path: Path) -> None:
    raw = minimal_raw(vault, workspace)
    del raw["cache"]["duckdb_path"]
    with pytest.raises(ConfigError, match="cache.duckdb_path"):
        load_config(write_config(tmp_path, raw))


# ---------------------------------------------------------------------------
# paths.vault validation
# ---------------------------------------------------------------------------

def test_vault_does_not_exist_raises(workspace: Path, tmp_path: Path) -> None:
    raw = minimal_raw(tmp_path / "nonexistent", workspace)
    with pytest.raises(ConfigError, match="does not exist"):
        load_config(write_config(tmp_path, raw))


def test_vault_is_file_not_dir_raises(workspace: Path, tmp_path: Path) -> None:
    fake_vault = tmp_path / "not_a_dir.md"
    fake_vault.write_text("hello")
    raw = minimal_raw(fake_vault, workspace)
    with pytest.raises(ConfigError, match="not a directory"):
        load_config(write_config(tmp_path, raw))


# ---------------------------------------------------------------------------
# bot_inbox_rel validation
# ---------------------------------------------------------------------------

def test_bot_inbox_rel_absolute_raises(vault: Path, workspace: Path, tmp_path: Path) -> None:
    raw = minimal_raw(vault, workspace)
    raw["paths"]["bot_inbox_rel"] = "/absolute/path"
    with pytest.raises(ConfigError, match="relative"):
        load_config(write_config(tmp_path, raw))


def test_bot_inbox_rel_with_dotdot_raises(vault: Path, workspace: Path, tmp_path: Path) -> None:
    raw = minimal_raw(vault, workspace)
    raw["paths"]["bot_inbox_rel"] = "../escape"
    with pytest.raises(ConfigError, match=r"\.\."):
        load_config(write_config(tmp_path, raw))


# ---------------------------------------------------------------------------
# outbox / state_dir inside vault
# ---------------------------------------------------------------------------

def test_outbox_inside_vault_raises(vault: Path, tmp_path: Path) -> None:
    raw = minimal_raw(vault, tmp_path)
    raw["paths"]["outbox"] = str(vault / "outbox")
    with pytest.raises(ConfigError, match="outbox"):
        load_config(write_config(tmp_path, raw))


def test_state_dir_inside_vault_raises(vault: Path, workspace: Path, tmp_path: Path) -> None:
    raw = minimal_raw(vault, workspace)
    raw["paths"]["state_dir"] = str(vault / "state")
    with pytest.raises(ConfigError, match="state_dir"):
        load_config(write_config(tmp_path, raw))


# ---------------------------------------------------------------------------
# Optional section partial configs
# ---------------------------------------------------------------------------

def test_delivery_section_present_but_no_email(
    vault: Path, workspace: Path, tmp_path: Path
) -> None:
    raw = minimal_raw(vault, workspace)
    raw["delivery"] = {}
    cfg = load_config(write_config(tmp_path, raw))
    assert cfg.delivery.email is None


def test_agent_section_absent_gives_none(vault: Path, workspace: Path, tmp_path: Path) -> None:
    cfg = load_config(write_config(tmp_path, minimal_raw(vault, workspace)))
    assert cfg.agent is None


def test_agent_backend_defaults_to_claude_when_omitted(
    vault: Path, workspace: Path, tmp_path: Path
) -> None:
    raw = minimal_raw(vault, workspace)
    raw["agent"] = {
        "command": "claude",
        "args": ["--print"],
        "timeout_seconds": 60,
        "work_dir": str(workspace / "workdir"),
    }
    cfg = load_config(write_config(tmp_path, raw))
    assert cfg.agent is not None
    assert cfg.agent.backend == "claude"


def test_agent_backend_parses_explicit_codex(
    vault: Path, workspace: Path, tmp_path: Path
) -> None:
    raw = minimal_raw(vault, workspace)
    raw["agent"] = {
        "backend": "codex",
        "command": "codex",
        "args": ["exec"],
        "timeout_seconds": 60,
        "work_dir": str(workspace / "workdir"),
    }
    cfg = load_config(write_config(tmp_path, raw))
    assert cfg.agent is not None
    assert cfg.agent.backend == "codex"

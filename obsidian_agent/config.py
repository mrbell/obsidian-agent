from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ConfigError(Exception):
    """Raised when configuration is invalid or missing required fields."""


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PathsConfig:
    vault: Path
    outbox: Path
    state_dir: Path
    bot_inbox_rel: str  # relative path inside vault, kept as str


@dataclass(frozen=True)
class CacheConfig:
    duckdb_path: Path


@dataclass(frozen=True)
class SmtpConfig:
    smtp_host: str
    smtp_port: int
    username: str
    password_env: str   # name of env var holding the password
    from_address: str
    to_address: str


@dataclass(frozen=True)
class DeliveryConfig:
    email: SmtpConfig | None = None


@dataclass(frozen=True)
class AgentConfig:
    command: str
    args: list[str]
    timeout_seconds: int
    work_dir: Path


@dataclass(frozen=True)
class TaskNotificationConfig:
    enabled: bool = True
    schedule: str = "0 7 * * *"
    lookahead_days: int = 3
    include_overdue: bool = True
    notify_if_empty: bool = False
    also_write_vault_artifact: bool = False


@dataclass(frozen=True)
class ResearchDigestConfig:
    enabled: bool = True
    schedule: str = "0 18 * * 0"
    lookback_days: int = 7
    topics: list[str] = field(default_factory=list)
    also_notify: bool = True


@dataclass(frozen=True)
class VaultConnectionsReportConfig:
    enabled: bool = True
    schedule: str = "0 9 * * 1"   # Monday 09:00
    lookback_recent_days: int = 14
    lookback_old_days: int = 30
    max_connections: int = 5
    also_notify: bool = True


@dataclass(frozen=True)
class VaultHygieneReportConfig:
    enabled: bool = True
    schedule: str = "0 10 1,15 * *"   # 1st and 15th of the month
    also_notify: bool = True


@dataclass(frozen=True)
class JobsConfig:
    task_notification: TaskNotificationConfig = field(
        default_factory=TaskNotificationConfig
    )
    research_digest: ResearchDigestConfig = field(
        default_factory=ResearchDigestConfig
    )
    vault_connections_report: VaultConnectionsReportConfig = field(
        default_factory=VaultConnectionsReportConfig
    )
    vault_hygiene_report: VaultHygieneReportConfig = field(
        default_factory=VaultHygieneReportConfig
    )


@dataclass(frozen=True)
class SemanticConfig:
    model: str = "all-MiniLM-L6-v2"
    max_notes_per_run: int | None = None  # None = unlimited


@dataclass(frozen=True)
class IndexingConfig:
    schedule: str = "0 3 * * *"           # structural index — nightly at 03:00
    semantic_schedule: str = "5 3 * * *"  # semantic index — nightly at 03:05


@dataclass(frozen=True)
class Config:
    paths: PathsConfig
    cache: CacheConfig
    delivery: DeliveryConfig
    agent: AgentConfig | None
    jobs: JobsConfig
    semantic: SemanticConfig = field(default_factory=SemanticConfig)
    indexing: IndexingConfig = field(default_factory=IndexingConfig)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve(raw: str) -> Path:
    return Path(raw).expanduser().resolve()


def _require(d: dict, key: str, context: str) -> Any:
    if key not in d:
        raise ConfigError(f"Missing required config field: {context}.{key}")
    return d[key]


# ---------------------------------------------------------------------------
# Section parsers
# ---------------------------------------------------------------------------

def _parse_paths(raw: dict) -> PathsConfig:
    vault = _resolve(_require(raw, "vault", "paths"))
    if not vault.exists():
        raise ConfigError(f"paths.vault does not exist: {vault}")
    if not vault.is_dir():
        raise ConfigError(f"paths.vault is not a directory: {vault}")

    outbox = _resolve(_require(raw, "outbox", "paths"))
    state_dir = _resolve(_require(raw, "state_dir", "paths"))

    bot_inbox_rel = _require(raw, "bot_inbox_rel", "paths")
    if not isinstance(bot_inbox_rel, str):
        raise ConfigError("paths.bot_inbox_rel must be a string")
    if Path(bot_inbox_rel).is_absolute():
        raise ConfigError(
            f"paths.bot_inbox_rel must be a relative path, got: {bot_inbox_rel!r}"
        )
    if ".." in Path(bot_inbox_rel).parts:
        raise ConfigError(
            f"paths.bot_inbox_rel must not contain '..', got: {bot_inbox_rel!r}"
        )

    if outbox.is_relative_to(vault):
        raise ConfigError(
            f"paths.outbox must not be inside paths.vault.\n"
            f"  vault:  {vault}\n"
            f"  outbox: {outbox}"
        )
    if state_dir.is_relative_to(vault):
        raise ConfigError(
            f"paths.state_dir must not be inside paths.vault.\n"
            f"  vault:     {vault}\n"
            f"  state_dir: {state_dir}"
        )

    return PathsConfig(
        vault=vault,
        outbox=outbox,
        state_dir=state_dir,
        bot_inbox_rel=bot_inbox_rel,
    )


def _parse_cache(raw: dict) -> CacheConfig:
    return CacheConfig(
        duckdb_path=_resolve(_require(raw, "duckdb_path", "cache"))
    )


def _parse_smtp(raw: dict) -> SmtpConfig:
    return SmtpConfig(
        smtp_host=_require(raw, "smtp_host", "delivery.email"),
        smtp_port=int(_require(raw, "smtp_port", "delivery.email")),
        username=_require(raw, "username", "delivery.email"),
        password_env=_require(raw, "password_env", "delivery.email"),
        from_address=_require(raw, "from_address", "delivery.email"),
        to_address=_require(raw, "to_address", "delivery.email"),
    )


def _parse_delivery(raw: dict | None) -> DeliveryConfig:
    if not raw:
        return DeliveryConfig()
    email_raw = raw.get("email")
    return DeliveryConfig(email=_parse_smtp(email_raw) if email_raw else None)


def _parse_agent(raw: dict | None) -> AgentConfig | None:
    if not raw:
        return None
    return AgentConfig(
        command=_require(raw, "command", "agent"),
        args=list(raw.get("args", [])),
        timeout_seconds=int(raw.get("timeout_seconds", 300)),
        work_dir=_resolve(_require(raw, "work_dir", "agent")),
    )


def _parse_task_notification(raw: dict | None) -> TaskNotificationConfig:
    if not raw:
        return TaskNotificationConfig()
    return TaskNotificationConfig(
        enabled=bool(raw.get("enabled", True)),
        schedule=str(raw.get("schedule", "0 7 * * *")),
        lookahead_days=int(raw.get("lookahead_days", 3)),
        include_overdue=bool(raw.get("include_overdue", True)),
        notify_if_empty=bool(raw.get("notify_if_empty", False)),
        also_write_vault_artifact=bool(raw.get("also_write_vault_artifact", False)),
    )


def _parse_research_digest(raw: dict | None) -> ResearchDigestConfig:
    if not raw:
        return ResearchDigestConfig()
    return ResearchDigestConfig(
        enabled=bool(raw.get("enabled", True)),
        schedule=str(raw.get("schedule", "0 18 * * 0")),
        lookback_days=int(raw.get("lookback_days", 7)),
        topics=list(raw.get("topics", [])),
        also_notify=bool(raw.get("also_notify", True)),
    )


def _parse_vault_connections_report(raw: dict | None) -> VaultConnectionsReportConfig:
    if not raw:
        return VaultConnectionsReportConfig()
    return VaultConnectionsReportConfig(
        enabled=bool(raw.get("enabled", True)),
        schedule=str(raw.get("schedule", "0 9 * * 1")),
        lookback_recent_days=int(raw.get("lookback_recent_days", 14)),
        lookback_old_days=int(raw.get("lookback_old_days", 30)),
        max_connections=int(raw.get("max_connections", 5)),
        also_notify=bool(raw.get("also_notify", True)),
    )


def _parse_vault_hygiene_report(raw: dict | None) -> VaultHygieneReportConfig:
    if not raw:
        return VaultHygieneReportConfig()
    return VaultHygieneReportConfig(
        enabled=bool(raw.get("enabled", True)),
        schedule=str(raw.get("schedule", "0 10 1,15 * *")),
        also_notify=bool(raw.get("also_notify", True)),
    )


def _parse_jobs(raw: dict | None) -> JobsConfig:
    if not raw:
        return JobsConfig()
    return JobsConfig(
        task_notification=_parse_task_notification(raw.get("task_notification")),
        research_digest=_parse_research_digest(raw.get("research_digest")),
        vault_connections_report=_parse_vault_connections_report(
            raw.get("vault_connections_report")
        ),
        vault_hygiene_report=_parse_vault_hygiene_report(
            raw.get("vault_hygiene_report")
        ),
    )


def _parse_indexing(raw: dict | None) -> IndexingConfig:
    if not raw:
        return IndexingConfig()
    return IndexingConfig(
        schedule=str(raw.get("schedule", "0 3 * * *")),
        semantic_schedule=str(raw.get("semantic_schedule", "5 3 * * *")),
    )


def _parse_semantic(raw: dict | None) -> SemanticConfig:
    if not raw:
        return SemanticConfig()
    max_notes = raw.get("max_notes_per_run")
    return SemanticConfig(
        model=str(raw.get("model", "all-MiniLM-L6-v2")),
        max_notes_per_run=int(max_notes) if max_notes is not None else None,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_config(config_path: Path) -> Config:
    """Load and validate configuration from a YAML file.

    Raises ConfigError for any missing required field or invalid value.
    Validation is structural only — components validate their own prerequisites
    at instantiation time (lazy validation).
    """
    if not config_path.exists():
        raise ConfigError(f"Config file not found: {config_path}")

    try:
        raw = yaml.safe_load(config_path.read_text())
    except yaml.YAMLError as exc:
        raise ConfigError(f"Failed to parse config file: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError("Config file must contain a YAML mapping at the top level")

    return Config(
        paths=_parse_paths(_require(raw, "paths", "<root>")),
        cache=_parse_cache(_require(raw, "cache", "<root>")),
        delivery=_parse_delivery(raw.get("delivery")),
        agent=_parse_agent(raw.get("agent")),
        jobs=_parse_jobs(raw.get("jobs")),
        semantic=_parse_semantic(raw.get("semantic")),
        indexing=_parse_indexing(raw.get("indexing")),
    )

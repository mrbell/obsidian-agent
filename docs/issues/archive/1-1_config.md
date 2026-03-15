# 1-1 — Config Loading and Validation

**Status**: `completed`
**Parent**: 1
**Children**: —
**Depends on**: —

## Description

Implement `obsidian_agent/config.py`. Load `config.yaml`, resolve `~` paths, validate required
fields, and expose a typed `Config` dataclass to the rest of the application.

## Implementation Notes

- Use `pyyaml` to load the config file
- Resolve all paths with `Path.expanduser().resolve()`
- Validate on load:
  - `paths.vault` exists and is a directory
  - `paths.bot_inbox_rel` is relative (no leading `/`, no `..`)
  - `paths.outbox` is not inside `paths.vault`
  - `paths.state_dir` is not inside `paths.vault`
  - SMTP config present if any job with `Notification` output is enabled
  - `agent.command` present if any Class B/C job is enabled
- Raise a clear `ConfigError` with a human-readable message on any validation failure
- Config path defaults to `config/config.yaml`; overridable via `--config` CLI flag

## Testing & Validation

- Valid config loads without error
- Missing required field raises `ConfigError` with field name in message
- `bot_inbox_rel` as absolute path raises `ConfigError`
- `outbox` inside `vault` raises `ConfigError`
- `~` paths are resolved correctly

## Definition of Done

`Config` dataclass instantiates correctly from a valid `config.yaml`. Invalid configs fail fast
with clear error messages.

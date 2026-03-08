# 1-2 — Logging Setup

**Status**: `completed`
**Parent**: 1
**Children**: —
**Depends on**: 1-1

## Description

Implement `obsidian_agent/logging_utils.py`. Configure structured logging to both stderr
and a rotating log file under `state_dir/logs/`.

## Implementation Notes

- Log to stderr at INFO level (configurable via `--verbose` flag for DEBUG)
- Log to `state_dir/logs/obsidian-agent.log` with rotation (e.g. 7 days or 5 files max)
- Use stdlib `logging` — no third-party logging libraries needed
- Log format: `YYYY-MM-DD HH:MM:SS [LEVEL] message`
- Each CLI command logs start, key config paths, and completion with counts

## Testing & Validation

- Logger writes to both handlers
- Log file is created under `state_dir/logs/` if it does not exist

## Definition of Done

`setup_logging(state_dir, verbose)` initialises logging. Subsequent `logging.getLogger(__name__)`
calls produce correctly formatted output to both stderr and file.

# 10-3 — Cron: Quote Commands and Redirect the Full Job Chain

**Status**: `open`
**Parent**: 10
**Children**: —
**Depends on**: 2-4

## Description

Cron entries currently build shell command chains where log redirection applies only to the
final `promote` command, and command/config/log paths are not shell-quoted. This makes logs
incomplete and causes breakage when paths contain spaces or shell-significant characters.

## Implementation Notes

- Update `obsidian_agent/cron.py`
- Build each managed cron entry so the entire command chain is executed as one shell command
- Apply `>> logfile 2>&1` to the grouped command, not just the final segment
- Quote binary path, config path, and log path using `shlex.quote`
- Preserve the current high-level behavior:
  - structural index on its own schedule
  - semantic index on its own schedule
  - job schedule runs `index && run && promote`

Preferred shape:

```sh
/bin/sh -lc '<quoted command chain>' >> '<quoted log>' 2>&1
```

## Testing & Validation

Red/green TDD:

- Add failing tests for generated cron lines
- Verify the full command chain is grouped before redirection
- Verify paths with spaces are quoted safely
- Verify existing managed section behavior remains unchanged

## Definition of Done

- All output from `index`, `run`, and `promote` lands in the intended log file
- Generated cron entries are robust to spaces in paths

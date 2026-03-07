# 3-2 — CLI: promote Command

**Status**: `open`
**Parent**: 3
**Children**: —
**Depends on**: 1-6, 3-1

## Description

Add the `promote` command to `obsidian_agent/cli.py`.

## Implementation Notes

```
obsidian-agent promote [--dry-run]
```

1. Load config and setup logging
2. Call `promote(outbox_root, vault_path, bot_inbox_rel)`
3. Print and log result summary: promoted N, skipped M, errors K
4. Exit non-zero if any errors occurred

`--dry-run` flag: log what would be promoted without copying anything.

## Testing & Validation

- `--dry-run` produces output but does not copy files
- Exit code 1 if any promotion errors

## Definition of Done

`obsidian-agent promote` runs end-to-end and reports results accurately.

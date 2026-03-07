# 2-5 — CLI: run Command

**Status**: `open`
**Parent**: 2
**Children**: —
**Depends on**: 1-6, 2-4

## Description

Add the `run` command to `obsidian_agent/cli.py`.

## Implementation Notes

```
obsidian-agent run <job_name>
```

1. Load config and setup logging
2. Open `IndexStore`
3. Look up job by name from registry
4. Build `JobContext` (instantiate delivery, worker as needed)
5. Execute job
6. Write `VaultArtifact` outputs to outbox; send `Notification` outputs via delivery
7. Log counts: artifacts written, notifications sent, errors

Fail clearly if the job name is not registered. Print available job names.

## Testing & Validation

- Running an unknown job name exits non-zero with a clear error message
- Successful run logs artifact/notification counts

## Definition of Done

`obsidian-agent run task_notification` executes end-to-end.

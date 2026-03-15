# 2-3 — Task Notification Job

**Status**: `completed`
**Parent**: 2
**Children**: —
**Depends on**: 1-5, 2-1, 2-2

## Description

Implement `obsidian_agent/jobs/task_notification.py`. Queries the index for open tasks with
upcoming or overdue due dates and produces a `Notification` (and optionally a `VaultArtifact`).

## Implementation Notes

### Job function signature

```python
def run(ctx: JobContext) -> list[JobOutput]: ...
```

### Query

```sql
SELECT t.note_relpath, t.line_no, t.text, t.due_date
FROM tasks t
WHERE t.status = 'open'
  AND t.due_date IS NOT NULL
  AND t.due_date <= :cutoff_date
ORDER BY t.due_date, t.note_relpath
```

Where `cutoff_date = today + lookahead_days`.

Overdue tasks: `due_date < today`.
Due today: `due_date = today`.
Upcoming: `today < due_date <= cutoff_date`.

### Email format

See `DESIGN.md §9` for the exact format. Sections:
- Due today
- Due in the next N days
- Overdue

Include note path next to each task for traceability.

### Config options (from `JobConfig`)

- `lookahead_days: int` (default 3)
- `include_overdue: bool` (default true)
- `notify_if_empty: bool` (default false) — skip sending if no tasks qualify
- `also_write_vault_artifact: bool` (default false)

## Testing & Validation

- Tasks due today appear in "Due today" section
- Tasks due in range appear in "Upcoming" section
- Overdue tasks appear in "Overdue" section when `include_overdue=true`
- No output produced when no tasks qualify and `notify_if_empty=false`
- Tasks without due dates are not included
- Done/cancelled tasks are not included

## Definition of Done

Job produces correctly formatted `Notification` from fixture index data. All test cases pass.

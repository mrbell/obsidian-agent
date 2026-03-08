from __future__ import annotations

from datetime import date, timedelta

from obsidian_agent.context import JobContext
from obsidian_agent.outputs import JobOutput, Notification, VaultArtifact

# Row tuple indices from the query
_COL_RELPATH = 0
_COL_TEXT = 1
_COL_DUE = 2

_Task = tuple[str, str, date]  # (note_relpath, text, due_date)


def run(ctx: JobContext) -> list[JobOutput]:
    """Query the index for due/overdue tasks and return notification outputs."""
    cfg = ctx.config.jobs.task_notification
    today = ctx.today
    cutoff = today + timedelta(days=cfg.lookahead_days)

    rows = ctx.store.conn.execute(
        """
        SELECT t.note_relpath, t.text, t.due_date
        FROM tasks t
        WHERE t.status = 'open'
          AND t.due_date IS NOT NULL
          AND t.due_date <= ?
        ORDER BY t.due_date, t.note_relpath
        """,
        [cutoff],
    ).fetchall()

    overdue: list[_Task] = []
    due_today: list[_Task] = []
    upcoming: list[_Task] = []

    for row in rows:
        relpath, text, due_date = row[_COL_RELPATH], row[_COL_TEXT], row[_COL_DUE]
        # DuckDB returns DATE as datetime.date, guard against string just in case
        if isinstance(due_date, str):
            due_date = date.fromisoformat(due_date)
        task: _Task = (relpath, text, due_date)
        if due_date < today:
            overdue.append(task)
        elif due_date == today:
            due_today.append(task)
        else:
            upcoming.append(task)

    if not cfg.include_overdue:
        overdue = []

    total = len(due_today) + len(upcoming) + len(overdue)

    if total == 0 and not cfg.notify_if_empty:
        return []

    subject = f"Task Reminder \u2014 {total} task{'s' if total != 1 else ''} due soon"
    body = _format_body(due_today, upcoming, overdue, cfg.lookahead_days)

    outputs: list[JobOutput] = [Notification(subject=subject, body=body)]

    if cfg.also_write_vault_artifact:
        outputs.append(
            VaultArtifact(
                job_name="task_notification",
                filename=f"{today.isoformat()}_task-reminder.md",
                content=f"# {subject}\n\n{body}\n",
            )
        )

    return outputs


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def _basename(relpath: str) -> str:
    return relpath.rsplit("/", 1)[-1]


def _format_body(
    due_today: list[_Task],
    upcoming: list[_Task],
    overdue: list[_Task],
    lookahead_days: int,
) -> str:
    sections: list[str] = []

    if due_today:
        lines = ["## Due today"]
        for relpath, text, _ in due_today:
            lines.append(f"- [ ] {text} (Note: {_basename(relpath)})")
        sections.append("\n".join(lines))

    if upcoming:
        lines = [f"## Due in the next {lookahead_days} days"]
        for relpath, text, due_date in upcoming:
            lines.append(f"- [ ] {text} \u2014 due {due_date} (Note: {_basename(relpath)})")
        sections.append("\n".join(lines))

    if overdue:
        lines = ["## Overdue"]
        for relpath, text, due_date in overdue:
            lines.append(f"- [ ] {text} \u2014 due {due_date} (Note: {_basename(relpath)})")
        sections.append("\n".join(lines))

    return "\n\n".join(sections)

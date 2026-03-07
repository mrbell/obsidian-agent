# 2 — Task Notification

**Status**: `open`
**Parent**: —
**Children**: 2-1, 2-2, 2-3, 2-4, 2-5
**Depends on**: 1

## Description

Implement the task notification job and the infrastructure it requires: the output model,
job registry/runner, SMTP email delivery, and the `run` CLI command.

This milestone produces a working daily task notification email driven by the DuckDB index.

## Prerequisites

Milestone 1 (Foundation) must be complete.

## Definition of Done

- `obsidian-agent run task_notification` queries the index and sends an email
- Email contains correctly grouped tasks (due today, upcoming, overdue)
- No email sent when no tasks are due and `notify_if_empty: false`
- SMTP delivery tested with mocked transport
- Job logic unit tested against fixture index data

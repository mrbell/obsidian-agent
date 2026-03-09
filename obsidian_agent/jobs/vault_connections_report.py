"""vault_connections_report — weekly Class B job.

Surfaces old vault content that is semantically connected to what the user
has been writing about recently. Corrects the recency bias that causes good
ideas and useful notes to be forgotten.

Uses the Claude Code worker with MCP vault tools (no web search). Claude
drives the exploration — the job provides a task description and date
parameters; Claude decides which MCP tools to call and how deep to go.
"""
from __future__ import annotations

import re

from obsidian_agent.context import JobContext
from obsidian_agent.jobs.registry import register
from obsidian_agent.outputs import JobOutput, Notification, VaultArtifact


def _validate_output(output: str) -> bool:
    """Non-empty and contains at least one ## heading."""
    if not output or not output.strip():
        return False
    return bool(re.search(r"^##\s+", output, re.MULTILINE))


def _has_semantic_data(ctx: JobContext) -> bool:
    """Return True if the semantic index has note_intelligence rows."""
    count = ctx.store.conn.execute(
        "SELECT count(*) FROM note_intelligence"
    ).fetchone()[0]
    return count > 0


def _build_prompt(
    today_str: str,
    lookback_recent_days: int,
    lookback_old_days: int,
    max_connections: int,
) -> str:
    return f"""\
You have access to the user's Obsidian vault through MCP tools.

Task:
Produce a weekly vault connections report for {today_str}.

The goal is to surface old vault content that is semantically connected to what the
user has been thinking about recently — correcting the recency bias that causes good
ideas to be forgotten.

What to do:
1. Identify the user's recent conceptual activity: use get_recent_concepts and
   get_daily_notes (covering the last {lookback_recent_days} days from {today_str})
   to understand what themes and ideas the user has been engaging with recently.

2. Find old connections: use find_related_notes, search_by_concept, search_similar,
   and get_implicit_items to find notes and ideas that:
   - Are NOT from the recent {lookback_recent_days}-day window
   - Connect meaningfully to the user's current themes
   - Have not been touched in at least {lookback_old_days} days

3. Synthesise the most interesting connections — explain concretely why each is
   relevant to what the user is working on now, not just that they share keywords.
   Use get_note_summary and get_note to deepen on notes you want to understand better.

4. Surface any implicit items (ideas, questions, intentions) from older notes that
   resonate with recent themes. Use get_implicit_items to find them.

Target: {max_connections} connections worth revisiting.

Required output format (markdown only, no preamble):

# Vault Connections — {today_str}

## What you've been thinking about (last {lookback_recent_days} days)
[Brief synthesis of recent themes — 3-5 sentences]

## Connections worth revisiting
[For each connection, using ### subheadings:]
### [Note Title or descriptive heading]
**Note**: [path]  **Last touched**: [date if available]
[2-3 sentences on why this connects to recent themes and what might be worth revisiting.]

## Implicit items that connect to your recent thinking
[Informal ideas or questions from older notes that relate to current themes.
Omit this section entirely if no strong matches are found.]

Do not pad with weak connections. If fewer than 3 strong connections exist, say so
rather than stretching the criteria.
"""


@register("vault_connections_report")
def run(ctx: JobContext) -> list[JobOutput]:
    job_cfg = ctx.config.jobs.vault_connections_report

    if ctx.worker is None:
        ctx.logger.error(
            "vault_connections_report: no worker configured. "
            "Add an 'agent' section to config.yaml."
        )
        return []

    if not _has_semantic_data(ctx):
        ctx.logger.warning(
            "vault_connections_report: no semantic data found. "
            "Run 'obsidian-agent index-semantic' first."
        )
        return []

    today_str = ctx.today.isoformat()
    prompt = _build_prompt(
        today_str,
        job_cfg.lookback_recent_days,
        job_cfg.lookback_old_days,
        job_cfg.max_connections,
    )

    ctx.logger.info("vault_connections_report: invoking worker")
    result = ctx.worker.run(prompt, web_search=False)

    if result.returncode != 0:
        ctx.logger.error(
            "vault_connections_report: worker failed returncode=%d stderr=%s",
            result.returncode, result.stderr[:300],
        )
        return []

    if not _validate_output(result.output):
        ctx.logger.error(
            "vault_connections_report: invalid output (empty or missing ## headings). "
            "output preview: %r",
            result.output[:500] if result.output else "<empty>",
        )
        return []

    filename = f"{today_str}_vault-connections-report.md"
    outputs: list[JobOutput] = [
        VaultArtifact(
            job_name="vault_connections_report",
            filename=filename,
            content=result.output,
        )
    ]
    ctx.logger.info(
        "vault_connections_report: artifact written filename=%s", filename
    )

    if job_cfg.also_notify:
        outputs.append(Notification(
            subject=f"Vault Connections Report — {today_str}",
            body=f"Weekly connections report is ready: {filename}",
        ))

    return outputs

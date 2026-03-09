"""vault_hygiene_report — bi-weekly Class B job.

Compares the implicit structure inferred by the semantic layer against the
explicit structure in the vault, and produces a report of suggestions for
improvement. All output is suggestions only — no automated edits.

Four categories of suggestions:
1. Implied tasks not formally captured
2. Ideas that may deserve a standalone note
3. Possible missing wikilinks (semantically related notes with no explicit link)
4. Orphaned threads (ideas/concepts that were active but have gone quiet)

Uses the Claude Code worker with MCP vault tools (no web search). Claude
drives the exploration — the job provides a task description; Claude decides
which MCP tools to call and how deep to go.
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
    """Return True if the semantic index has note_intelligence or implicit_items rows."""
    intel = ctx.store.conn.execute(
        "SELECT count(*) FROM note_intelligence"
    ).fetchone()[0]
    implicit = ctx.store.conn.execute(
        "SELECT count(*) FROM implicit_items"
    ).fetchone()[0]
    return intel > 0 or implicit > 0


def _build_prompt(today_str: str) -> str:
    return f"""\
You have access to the user's Obsidian vault through MCP tools.

Task:
Produce a vault hygiene report for {today_str}.

The goal is to surface suggestions that help the user keep their vault organised
and intentional. All output must be suggestions only — never criticise the user's
existing structure or imply a specific system. Work with whatever structure exists.

Look for four types of issues:

1. Implied tasks not formally captured
   Use get_implicit_items (type='task') and get_implicit_items (type='intention')
   to find action-oriented items buried in prose. Cross-reference with query_tasks
   to check whether a corresponding formal task already exists in the same note.
   Flag items that appear informal but have no matching open task.

2. Ideas that may deserve a standalone note
   Use get_implicit_items (type='idea') to find recurring ideas. An idea is worth
   flagging if it appears across multiple notes or if it appears to be developed
   enough that a dedicated note would help. Use search_by_concept or search_similar
   to check how widely an idea recurs. Reference the specific notes where it appears.

3. Possible missing wikilinks
   Use find_related_notes to identify pairs of notes that are highly conceptually
   related but likely not linked. Cross-check with get_note_links to confirm neither
   note already links to the other. Only surface strong, specific relationships —
   not generic overlaps. Describe concretely what the relationship is.

4. Orphaned threads
   Use get_stale_concepts with a date roughly 90 days ago ({_ninety_days_before(today_str)})
   to find concepts that were active in older notes but haven't appeared in recently
   modified notes. Cross-reference with get_implicit_items or search_by_concept to
   find the actual content. Flag threads where the user expressed clear intent or
   enthusiasm that seems to have been dropped without resolution.

Be specific: reference actual note names and actual text, not generic advice.
Be selective: include only the most actionable suggestions per category (3-5 each).
If a category yields nothing interesting, omit it entirely rather than padding.

Required output format (markdown only, no preamble):

# Vault Hygiene Report — {today_str}

## Implied tasks not formally captured
[Bullet list. Each item: the implied task text, source note in [[wikilink]] format,
and a one-line suggestion. Omit section if none found.]

## Ideas that might deserve their own note
[Bullet list. Each item: the idea, which notes it appears in, why it seems developed
enough for a standalone note. Omit section if none found.]

## Possible missing wikilinks
[Bullet list. Each item: the two notes, what connects them specifically.
Omit section if none found.]

## Threads that went quiet
[Bullet list. Each item: the concept or thread, when it was last active, what the
user seemed to intend. Omit section if none found.]

If none of the four categories yield anything interesting, say so briefly.
"""


def _ninety_days_before(today_str: str) -> str:
    """Return ISO date string 90 days before today_str."""
    from datetime import date, timedelta
    today = date.fromisoformat(today_str)
    return (today - timedelta(days=90)).isoformat()


@register("vault_hygiene_report")
def run(ctx: JobContext) -> list[JobOutput]:
    job_cfg = ctx.config.jobs.vault_hygiene_report

    if ctx.worker is None:
        ctx.logger.error(
            "vault_hygiene_report: no worker configured. "
            "Add an 'agent' section to config.yaml."
        )
        return []

    if not _has_semantic_data(ctx):
        ctx.logger.warning(
            "vault_hygiene_report: no semantic data found. "
            "Run 'obsidian-agent index-semantic' first."
        )
        return []

    today_str = ctx.today.isoformat()
    prompt = _build_prompt(today_str)

    ctx.logger.info("vault_hygiene_report: invoking worker")
    result = ctx.worker.run(prompt, web_search=False)

    if result.returncode != 0:
        ctx.logger.error(
            "vault_hygiene_report: worker failed returncode=%d stderr=%s",
            result.returncode, result.stderr[:300],
        )
        return []

    if not _validate_output(result.output):
        ctx.logger.error(
            "vault_hygiene_report: invalid output (empty or missing ## headings). "
            "output preview: %r",
            result.output[:500] if result.output else "<empty>",
        )
        return []

    filename = f"{today_str}_vault-hygiene-report.md"
    outputs: list[JobOutput] = [
        VaultArtifact(
            job_name="vault_hygiene_report",
            filename=filename,
            content=result.output,
        )
    ]
    ctx.logger.info("vault_hygiene_report: artifact written filename=%s", filename)

    if job_cfg.also_notify:
        outputs.append(Notification(
            subject=f"Vault Hygiene Report — {today_str}",
            body=f"Hygiene report ready: {filename}",
        ))

    return outputs

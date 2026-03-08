from __future__ import annotations

import re
from datetime import timedelta

from obsidian_agent.context import JobContext
from obsidian_agent.jobs.registry import register
from obsidian_agent.outputs import JobOutput, Notification, VaultArtifact


def _topic_slug(topic: str) -> str:
    """Convert a topic string to a filename-safe slug."""
    return re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")


def _build_prompt(topic: str, lookback_days: int, today_str: str, since_str: str) -> str:
    return f"""\
You have access to the user's Obsidian vault through MCP tools and can search the web.

Task:
Produce a weekly research digest on the topic: {topic}

Cover only content published or updated in the last {lookback_days} days (since {since_str}).

You may use the vault MCP tools to understand what the user already knows or finds
interesting about this topic — look for relevant notes to inform what is genuinely
new or useful to them.

Required output format (markdown only, no preamble):

# Weekly Research Digest: {topic}
**Period**: {since_str} to {today_str}

## Trends
[3-5 sentences on what is happening in this space this week]

## Notable Articles
[For each of the 5-10 most relevant items:]
### [Title]
**Source**: [site]  **Date**: [date]  **URL**: [url]
[2-4 sentence summary. Why it matters to someone interested in this topic.]

## Follow-up Questions
[2-3 questions this week's reading raises]

If fewer than 3 relevant articles are found for the period, say so explicitly rather \
than padding with older content.
"""


def _validate_output(output: str) -> bool:
    """Minimal validation: non-empty and contains at least one ## heading."""
    if not output or not output.strip():
        return False
    return bool(re.search(r"^##\s+", output, re.MULTILINE))


@register("research_digest")
def run(ctx: JobContext) -> list[JobOutput]:
    job_cfg = ctx.config.jobs.research_digest
    outputs: list[JobOutput] = []

    if not job_cfg.topics:
        ctx.logger.warning("research_digest: no topics configured, nothing to do.")
        return outputs

    if ctx.worker is None:
        ctx.logger.error(
            "research_digest: no worker configured. "
            "Add an 'agent' section to config.yaml."
        )
        return outputs

    today_str = ctx.today.isoformat()
    since = ctx.today - timedelta(days=job_cfg.lookback_days)
    since_str = since.isoformat()

    produced: list[str] = []   # topic names that produced an artifact

    for topic in job_cfg.topics:
        ctx.logger.info("research_digest: processing topic=%r", topic)

        prompt = _build_prompt(topic, job_cfg.lookback_days, today_str, since_str)

        result = ctx.worker.run(prompt, web_search=True)

        if result.returncode != 0:
            ctx.logger.error(
                "research_digest: worker failed for topic=%r returncode=%d stderr=%s",
                topic, result.returncode, result.stderr[:300],
            )
            continue

        if not _validate_output(result.output):
            ctx.logger.error(
                "research_digest: invalid output for topic=%r (empty or missing ## headings)",
                topic,
            )
            continue

        slug = _topic_slug(topic)
        filename = f"{today_str}_research-digest-{slug}.md"
        outputs.append(VaultArtifact(
            job_name="research_digest",
            filename=filename,
            content=result.output,
        ))
        produced.append(topic)
        ctx.logger.info("research_digest: artifact written for topic=%r filename=%s", topic, filename)

    if job_cfg.also_notify and produced:
        slug_lines = "\n".join(
            f"- {topic} → {ctx.today.isoformat()}_research-digest-{_topic_slug(topic)}.md"
            for topic in produced
        )
        outputs.append(Notification(
            subject=f"Research Digest — {len(produced)} topic{'s' if len(produced) != 1 else ''} processed",
            body=slug_lines,
        ))

    return outputs

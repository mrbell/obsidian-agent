# 5-2 — Research Digest Job

**Status**: `completed`
**Parent**: 5
**Children**: —
**Depends on**: 2-4, 3-1, 5-1

## Description

Implement `obsidian_agent/jobs/research_digest.py`. For each configured topic, invokes the
Claude Code worker with web search enabled to gather and summarize recent articles, producing
a `VaultArtifact` per topic.

## Implementation Notes

### Job function

```python
@register("research_digest")
def run(ctx: JobContext) -> list[JobOutput]: ...
```

For each topic in `ctx.cfg.jobs.research_digest.topics`:
1. Build prompt (see `DESIGN.md §9`)
2. Call `ctx.worker.run(prompt, web_search=True)`
3. Validate output: non-empty, contains expected section headers
4. If invalid: log error, skip this topic (do not write to outbox)
5. If valid: create `VaultArtifact` with a dated filename
6. If `also_notify`: create a `Notification` with a brief summary line per topic

### Output filename format

```
YYYY-MM-DD_research-digest-<topic-slug>.md
```

Where `topic-slug` is the topic lowercased with spaces replaced by hyphens.

### Prompt

See `DESIGN.md §9` for the full prompt template. Key requirements:
- State the topic and lookback period explicitly
- Instruct Claude to use vault MCP tools to understand existing knowledge before searching
- Require specific markdown sections: Trends, Notable Articles, Follow-up Questions
- Require markdown-only output

### Output validation

Minimal validation: output is non-empty string, contains at least one `##` heading.
Do not attempt to parse or transform the LLM output — promote it as-is.

## Testing & Validation

- Job produces one `VaultArtifact` per topic with expected filename
- Empty output from worker is rejected (no artifact written)
- Output missing required headings is rejected
- `also_notify=true` produces a `Notification` in addition to artifacts
- Tested with mocked `ClaudeCodeWorker`

## Definition of Done

`obsidian-agent run research_digest` produces valid markdown artifact(s) in the outbox.
All test cases pass with mocked worker.

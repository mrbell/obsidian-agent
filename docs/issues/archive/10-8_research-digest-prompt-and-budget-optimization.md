# 10-8 — Research Digest: Prompt and Budget Optimization

**Status**: `completed`
**Parent**: 10
**Children**: —
**Depends on**: 10-7

## Description

Use data collected from the per-topic instrumentation added in 10-7
(`prompt_chars`, `output_chars`, `elapsed`) to identify where
`research_digest` usage is going and implement targeted reductions.

## Context

10-7 established that `search_notes` is now index-backed (no disk scan)
and added per-topic logging. The outstanding questions — where does the
remaining session cost come from — are now answerable from observed runs:

- How much of `elapsed` is vault exploration vs. web search/fetch?
- Is `prompt_chars` large because of feed payloads or prompt structure?
- Are any MCP tools being called excessively or returning oversized results?

## Investigation Steps

1. Run `research_digest` with the new instrumentation and review
   `~/.local/share/obsidian-agent/research_digest.log`.
2. Identify the dominant cost driver from the logged metrics and any
   patterns visible in the worker `stderr` (Claude's session trace).
3. Choose an intervention from the options below based on what the data shows.

## Implementation Options

- **Prompt tightening**: Replace the open-ended vault exploration instruction
  with specific tool guidance (e.g. prefer `search_by_concept` and
  `get_note_summary` over pulling full notes).
- **`--max-turns` guardrail**: Add a per-topic turn cap to the worker
  invocation to bound runaway sessions.
- **MCP payload limits**: Add a `max_chars` cap to `get_note` and/or
  `get_daily_notes` to prevent full-note retrievals from flooding context.
- **Per-topic timeout**: Tighten `timeout_seconds` for `research_digest`
  runs relative to the global agent config default.

## Testing & Validation

- Follow red/green TDD for any code change.
- Validate with at least one measured `research_digest` run before and
  after to confirm the chosen intervention reduces elapsed time or output
  size without degrading digest quality.

## Findings (2026-03-17)

Ran `research_digest` manually with the 10-7 instrumentation in place. Results:

| Topic | elapsed | prompt_chars | output_chars | MCP calls | First MCP call |
|---|---|---|---|---|---|
| agentic coding | 321s | 1,638 | 9,137 | 4 | +11s |
| electronic warfare in space | 405s | 1,543 | 5,842 | 2 | +344s |

**Web search/fetch accounts for ~99% of elapsed time.** Vault MCP calls are
minimal (2–4 per topic, totalling ~4–12 seconds). The prompt is small. Output
size is proportionate to the number of articles summarised.

The dominant "cost" is doing exactly what the job is supposed to do: fetching
and summarising 5–10 articles per topic. This is intentional and worthwhile.
No wasteful patterns (excessive vault calls, oversized payloads, repeated
lookups) were observed.

**No code changes warranted.** The investigated options (prompt tightening,
`--max-turns` cap, MCP payload limits, per-topic timeout) would either have
minimal impact or would degrade output quality by cutting off legitimate work.

## Definition of Done

Profiling data collected and reviewed. No action needed — token usage reflects
real work, not inefficiency.

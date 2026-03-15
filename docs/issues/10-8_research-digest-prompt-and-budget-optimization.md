# 10-8 — Research Digest: Prompt and Budget Optimization

**Status**: `open`
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

## Definition of Done

- At least one optimization is implemented and tested.
- A measured run confirms the improvement.
- The issue records what the profiling data showed so future work has context.

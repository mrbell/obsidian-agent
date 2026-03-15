# 10-7 — Research Digest Token Usage and Context-Budget Profiling

**Status**: `open`
**Parent**: 10
**Children**: —
**Depends on**: 4-1, 6-5, 8-2

## Description

Profile and reduce excessive agent usage during `research_digest`, with particular attention
to how vault retrieval, MCP search behavior, and broad web exploration contribute to total
token/session consumption.

`search_notes` is part of the problem space because it currently reads note bodies directly
from disk and performs a substring scan in Python on every call, but the concern is broader
than that. A research-digest run can consume far more usage than expected due to a mix of:

- broad or repeated MCP discovery calls
- repeated full-note retrievals (`get_note`, `get_daily_notes`)
- overly large excerpts or retrieved note payloads
- wide web-search / web-fetch exploration
- one full agent run per configured topic with no budget guardrails

This issue is a profiling and optimization follow-up, not a required correctness fix for the
current hardening pass.

## Questions to Answer

- How much total usage does a typical `research_digest` run consume per topic?
- How often do `research_digest` and other Claude-driven flows call `search_notes` in practice?
- How many MCP calls are made per topic, and which tools dominate?
- How often are full notes pulled versus short excerpts?
- Is token usage high because MCP search is returning too much low-value context?
- Is the bigger cost broad web exploration rather than vault retrieval?
- Would indexed full-text search materially reduce both latency and noisy retrieval?
- Should MCP search tools return tighter excerpts / fewer fields by default?
- Should `research_digest` enforce per-topic guardrails or a budget-aware strategy?

## Investigation / Implementation Options

- Instrument `research_digest` runs with per-topic accounting:
  - prompt size
  - MCP tool-call counts by tool
  - estimated payload size returned by each tool
  - worker output size
- Instrument MCP tool usage and result sizes during agent runs
- Add stricter limits or excerpt sizing to `search_notes`
- Review `get_note` / `get_daily_notes` usage patterns to see whether too much full-note content
  is being pulled into the model
- Move keyword search into DuckDB FTS or another indexed path
- Review prompts/tool guidance so jobs retrieve less broad context by default
- Add per-topic usage guardrails or a “good enough, stop searching” strategy if needed

## Testing & Validation

If work begins here, follow red/green TDD for any chosen code change:

- add a failing profiling, budgeting, or behavior regression test first
- then implement the minimal instrumentation or retrieval/path change needed

Validation should include at least one measured `research_digest` run so decisions are driven
by observed usage rather than guesswork.

## Definition of Done

- The project has measured evidence about where `research_digest` usage is going
- Either a concrete optimization is implemented and tested, or the issue records enough
  profiling data to drive the next implementation step

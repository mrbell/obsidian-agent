# 10-7 — MCP Search Performance and Context-Budget Follow-up

**Status**: `open`
**Parent**: 10
**Children**: —
**Depends on**: 4-1, 6-5, 8-2

## Description

`search_notes` currently reads note bodies directly from disk and performs a substring scan
in Python on every call. This was acceptable for v1, but it is now worth revisiting because
Claude-driven jobs and interactive MCP use can call search tools repeatedly, increasing both
latency and the amount of retrieved context that may be sent back into the model.

This issue is a follow-up / backlog item, not a required correctness fix for the current
hardening pass.

## Questions to Answer

- How often do `research_digest` and other Claude-driven flows call `search_notes` in practice?
- Is token usage high because MCP search is returning too much low-value context?
- Would indexed full-text search materially reduce both latency and noisy retrieval?
- Should MCP search tools return tighter excerpts / fewer fields by default?

## Investigation / Implementation Options

- Instrument MCP tool usage and result sizes during agent runs
- Add stricter limits or excerpt sizing to `search_notes`
- Move keyword search into DuckDB FTS or another indexed path
- Review prompts/tool guidance so jobs retrieve less broad context by default

## Testing & Validation

If work begins here, follow red/green TDD for any chosen change:

- add a failing performance-oriented or behavior regression test first
- then implement the minimal retrieval/path change needed

## Definition of Done

- Either a concrete optimization is implemented and tested, or the issue records enough
  measured evidence to drive the next implementation step

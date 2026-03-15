# 11-5 — Implement Codex Backend Adapter

**Status**: `completed`
**Parent**: 11
**Children**: —
**Depends on**: 11-1, 11-3, 11-4

## Description

Implement a Codex backend adapter that satisfies the shared worker contract closely enough
to run the existing jobs and semantic extraction pipeline without job-specific branching.

## Implementation Notes

- Add a concrete Codex adapter under `obsidian_agent/agent/`
- Map shared worker flags to Codex behavior:
  - `web_search=True`
  - `with_mcp=True`
  - non-interactive prompt execution
- Implement Codex-specific output parsing
- Handle any MCP registration constraints discovered in 11-4
- If Codex cannot support a capability identically, fail clearly and document it

Avoid embedding Codex-specific conditionals throughout jobs. Differences should live in the
adapter or backend factory.

## Testing & Validation

Red/green TDD:

- Add failing adapter tests using a fake Codex command where possible
- Add CLI/backend-selection tests for `backend: codex`
- Add at least one end-to-end smoke path if the environment makes it practical

Target scenarios:

- no-MCP smoke prompt
- MCP-enabled vault access
- optional web-search-enabled run
- clean failure on unsupported capability combinations

## Definition of Done

- Codex can be selected as the configured backend
- The existing job layer runs through the shared abstraction without modification
- Known Codex limitations, if any, are enforced and documented

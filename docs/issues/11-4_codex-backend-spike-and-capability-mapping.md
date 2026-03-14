# 11-4 — Codex Backend Spike and Capability Mapping

**Status**: `open`
**Parent**: 11
**Children**: —
**Depends on**: 11-1

## Description

Run a focused spike on the Codex CLI to determine how closely it can match the required
agent capabilities for this project and where adapter design needs to compensate for
behavioral differences.

This issue should reduce uncertainty before committing to a full Codex adapter.

## Questions to Answer

- How should non-interactive Codex runs be invoked for this project?
- What is the most reliable machine-readable output format for final model output?
- How should MCP servers be registered or supplied for an isolated run?
- Is per-run MCP configuration possible, or must Codex rely on pre-registered/global MCP state?
- How should web search be enabled/disabled in a backend-neutral way?
- What sandbox/approval settings are appropriate for scheduled local runs?

## Deliverables

- A concrete capability matrix: Claude vs Codex
- A recommended invocation pattern for Codex
- A list of functionality that is:
  - fully supported
  - supported with adaptation
  - unsupported or risky

## Testing & Validation

Prefer executable spike notes and small verification scripts/tests over prose-only conclusions.

If possible, validate:

- simple prompt execution
- MCP connectivity to `obsidian-agent mcp`
- search-enabled run shape
- structured output extraction path

## Definition of Done

- The project has a clear go/no-go decision for Codex support
- Backend adapter implementation can proceed with known constraints rather than guesses

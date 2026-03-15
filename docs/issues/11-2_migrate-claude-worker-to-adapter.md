# 11-2 — Migrate Claude Worker to Backend Adapter

**Status**: `completed`
**Parent**: 11
**Children**: —
**Depends on**: 11-1

## Description

Refactor the existing Claude integration into a concrete backend adapter that implements the
new worker abstraction without changing behavior.

This issue is about preserving current functionality while isolating Claude-specific logic.

## Implementation Notes

- Move or rename `ClaudeCodeWorker` so it is clearly a backend adapter, not the core worker model
- Keep current Claude features intact:
  - non-interactive execution
  - per-run MCP config injection
  - explicit tool allowlisting
  - optional web search
  - JSON result parsing
- Remove Claude-specific type references from unrelated modules where possible
- Keep current smoke tests and MCP connectivity tests working through the adapter

## Testing & Validation

Red/green TDD:

- First pin down current Claude behavior with tests if needed
- Then refactor behind the new abstraction
- Verify existing worker, CLI, and job tests still pass

## Definition of Done

- Claude support works exactly as before, but behind the backend abstraction
- No job needs to know that Claude is the concrete backend

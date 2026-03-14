# 11-1 — Agent Backend Abstraction and Capability Contract

**Status**: `open`
**Parent**: 11
**Children**: —
**Depends on**: 5-1

## Description

Introduce a backend-agnostic worker contract so jobs and semantic extraction no longer
depend on a Claude-specific class name or Claude-specific assumptions leaking through the
type surface.

The abstraction should preserve the current job call pattern while making backend
capabilities explicit.

## Implementation Notes

- Define a stable worker interface in `obsidian_agent/agent/`
- Define a backend-neutral result type
- Define capability semantics for:
  - prompt execution
  - MCP availability
  - web search availability
  - structured output handling
- Decide how unsupported capabilities are surfaced:
  - adapter-level validation
  - clean runtime failure with actionable error
  - capability introspection for the caller

Likely shape:

```python
class AgentWorker(Protocol):
    def run(self, prompt: str, *, web_search: bool, with_mcp: bool) -> WorkerResult: ...
```

But the issue should also define:

- backend identifier / metadata
- optional capability reporting
- how backend-specific model/version strings are stored in semantic metadata

## Testing & Validation

Red/green TDD:

- Add failing tests around the new interface and shared result contract
- Verify existing job code can target the abstract type rather than a Claude concrete class

## Definition of Done

- A backend-neutral worker contract exists and is tested
- Higher-level code can depend on the abstraction without referring to Claude by name

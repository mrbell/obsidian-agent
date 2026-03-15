# 11 — Multi-Agent Backend Abstraction

**Status**: `in_progress`
**Parent**: —
**Children**: 11-1, 11-2, 11-3, 11-4, 11-5, 11-6
**Depends on**: 4, 5, 6, 8, 10-2

## Description

Abstract the LLM/agent execution layer so the system is not coupled to Claude Code as the
only supported backend. The goal is to preserve current functionality while making it
possible to choose between Claude Code, Codex, and future agent CLIs through a stable
internal interface.

Current job logic is already close to the right abstraction: jobs ask for a worker run with
a prompt plus capability flags (`web_search`, `with_mcp`). What remains is to move all
Claude-specific CLI assumptions behind a backend adapter layer, define backend capability
contracts clearly, and add at least one second concrete backend.

## Goals

- Preserve existing Claude-based functionality
- Make backend selection explicit in config
- Support Codex without forking job implementations
- Keep MCP-backed vault access as the standard mechanism for agent-side vault retrieval
- Keep room for future backends with different CLI invocation semantics

## Non-Goals

- Rewriting jobs around a different prompt model
- Removing Claude-specific optimizations if they are still useful behind the Claude adapter
- Guaranteeing every backend supports every feature on day one without declared capability checks

## Working Method

All implementation work under this milestone should follow red/green TDD:

1. Add a failing test for the intended abstraction or backend behavior
2. Implement the minimum change required to pass
3. Refactor only after the behavior is pinned down by tests

## Child Issues

- **11-1**: Define agent backend abstraction and capability contract
- **11-2**: Migrate Claude worker to backend adapter
- **11-3**: Config and CLI support for backend selection
- **11-4**: Codex backend spike and capability mapping
- **11-5**: Implement Codex backend adapter
- **11-6**: Docs and compatibility matrix for supported agent backends

## Definition of Done

- Jobs and semantic indexing use a backend-agnostic worker interface
- Claude remains fully supported through the new abstraction
- Codex support is either fully implemented or explicitly documented as partial with tested limits
- Config, CLI help, and docs describe backend selection and capability expectations clearly

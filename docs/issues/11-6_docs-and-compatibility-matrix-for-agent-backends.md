# 11-6 — Docs and Compatibility Matrix for Agent Backends

**Status**: `open`
**Parent**: 11
**Children**: —
**Depends on**: 11-2, 11-3, 11-5

## Description

Update project docs so agent support is described accurately and users understand which
backends are supported, how to configure them, and what capability differences exist.

The current documentation is heavily Claude-centric. After the abstraction work, the docs
should describe the generic agent layer first and then explain backend-specific setup.

## Implementation Notes

- Update `README.md`
- Update `DESIGN.md`
- Update `CLAUDE.md` where relevant
- Update `config/config.yaml.example`

Add a compatibility matrix covering at least:

| Backend | Non-interactive runs | MCP vault access | Web search | Structured output | Status |
|---|---|---|---|---|---|

Clarify:

- which backend is the reference implementation
- which commands are backend-neutral
- any limitations or setup differences for Codex

## Testing & Validation

- Review docs for consistency with actual implementation
- If any CLI help text changes, cover it with tests where practical

## Definition of Done

- User-facing docs describe the agent layer generically
- Backend-specific setup is documented clearly
- Support status and limitations are easy to understand

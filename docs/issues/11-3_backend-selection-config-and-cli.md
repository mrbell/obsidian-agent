# 11-3 — Backend Selection in Config and CLI

**Status**: `open`
**Parent**: 11
**Children**: —
**Depends on**: 11-1, 11-2

## Description

Make agent backend selection explicit in configuration and ensure the CLI instantiates the
correct backend adapter.

Today the config effectively assumes a Claude-like CLI command. That is too weak once
multiple backends are supported.

## Implementation Notes

- Extend config schema to include an explicit backend identifier, e.g.:

```yaml
agent:
  backend: claude
  command: claude
  args: [...]
```

- Define what config fields are shared across backends and what is backend-specific
- Update `cli.py` so `run`, `agent test`, `index-semantic`, and any future agent paths
  instantiate workers via a backend factory
- Decide how `agent test` behaves when a backend lacks one of the requested capabilities

## Testing & Validation

Red/green TDD:

- Add failing config parse tests for backend selection
- Add failing CLI tests ensuring the correct adapter is chosen
- Verify backward compatibility strategy if old config files omit `backend`

## Definition of Done

- Backend selection is explicit, parsed, validated, and exercised by CLI tests
- The system can instantiate the correct worker without hard-coding Claude

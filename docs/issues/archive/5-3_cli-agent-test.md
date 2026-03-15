# 5-3 — CLI: agent test Command

**Status**: `completed`
**Parent**: 5
**Children**: —
**Depends on**: 1-6, 5-1

## Description

Add the `agent test` command to `obsidian_agent/cli.py`. Verifies that the configured Claude
Code command is available, executable, and able to produce output for a trivial prompt.

## Implementation Notes

```
obsidian-agent agent test
```

1. Load config
2. Invoke `ClaudeCodeWorker.run("Say the word READY and nothing else.")`
   - Without MCP server, without web search (basic smoke test)
3. Check: exit code 0 and output is non-empty
4. Print: pass/fail + the raw output

This command is useful for initial setup verification and for debugging in CI or cron.

## Testing & Validation

- Passes when `claude` is available and working
- Fails clearly when `claude` is not found on PATH
- Prints raw output for inspection

## Definition of Done

`obsidian-agent agent test` exits 0 on success, non-zero on failure, with clear output.

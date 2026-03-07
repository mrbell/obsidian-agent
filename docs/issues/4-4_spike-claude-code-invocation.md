# 4-4 — Spike: Claude Code Headless Invocation with MCP

**Status**: `open`
**Parent**: 4
**Children**: —
**Depends on**: 4-2

## Description

Research and validate the exact mechanism for invoking Claude Code headlessly with a custom
MCP server registered. This must be resolved before implementing the Claude Code worker (5-1).

## Questions to Answer

1. What is the exact `claude` CLI command and flags for headless (non-interactive) mode?
   - Is it `claude --print "prompt"`? `claude -p "prompt"`? Something else?
2. How is a custom MCP server registered for a single invocation?
   - Via `--mcp-config <path>`? Via a JSON config file? Via an environment variable?
   - What does the MCP config JSON schema look like?
3. Does tool use (MCP tools, web search) work in `--print`/headless mode?
   - Or is tool use disabled in non-interactive mode?
4. How is web search enabled/disabled for a given invocation?
5. What does stdout contain in headless mode?
   - Just the final response text? Or structured JSON including tool calls?
6. What exit codes does `claude` use?
   - 0 on success, non-zero on error — what constitutes an error?
7. Are there rate limits or concurrency constraints relevant to scheduled job use?

## Validation

Run a test invocation:
```bash
obsidian-agent mcp &   # start MCP server
# then invoke claude headlessly with MCP registered
# verify it can call MCP tools and return a response
```

## Output

Update `DESIGN.md §4` (Claude Code Worker) and issue 5-1 with confirmed invocation details.
Update `config.yaml.example` with any additional agent config fields needed.

## Definition of Done

All questions above answered with working example invocation. Implementation approach for
`agent/worker.py` confirmed.

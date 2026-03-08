# 4-4 — Spike: Claude Code Headless Invocation with MCP

**Status**: `completed`
**Parent**: 4
**Children**: —
**Depends on**: 4-2

## Description

Research and validate the exact mechanism for invoking Claude Code headlessly with a custom
MCP server registered. This must be resolved before implementing the Claude Code worker (5-1).

## Findings

### 1. Headless (non-interactive) mode

```bash
claude -p "<prompt>"
# or equivalently:
claude --print "<prompt>"
```

`-p` / `--print` prints the response to stdout and exits. This is the correct mode for
scheduled/automated invocations.

### 2. MCP server registration

```bash
claude -p "<prompt>" --mcp-config /path/to/mcp.json
```

`--mcp-config` accepts a path to a JSON file (or a JSON string directly). The JSON schema
mirrors the Claude Desktop config format:

```json
{
  "mcpServers": {
    "obsidian-vault": {
      "command": "obsidian-agent",
      "args": ["mcp", "--config", "/path/to/config.yaml"]
    }
  }
}
```

Multiple configs can be passed: `--mcp-config file1.json file2.json`.

### 3. Tool use in `--print` mode

MCP tools and built-in tools (WebSearch, WebFetch) work in `--print` mode. This is the
primary design intent for headless agentic use. Web search is available by default; tools
can be restricted with `--tools` or `--allowedTools`.

### 4. Web search

Web search (`WebSearch`, `WebFetch`) is enabled by default. To disable: `--tools ""` or
restrict with `--allowedTools`. For Class C (research) jobs, leave defaults.

### 5. Stdout format

`--output-format text` (the default) writes just the model's response text to stdout.
Other options: `json` (structured), `stream-json` (streaming). Use `text` for simplicity.

### 6. Exit codes

- `0`: success
- `1`: error (bad invocation, API error, timeout on the Claude side)

Non-zero exit indicates no usable output was produced.

### 7. Rate limits / concurrency

No special concurrency constraints beyond the standard subscription limits. Scheduled
cron jobs running one at a time are well within limits.

### Nested session note

Claude Code detects the `CLAUDECODE` environment variable and refuses to launch inside an
existing session. This is not an issue in production cron use. In tests, use a dummy
command (e.g. `echo`) instead of `claude`.

## Recommended invocation for worker.py

```bash
claude -p "<prompt>" \
  --mcp-config /tmp/<uuid>-mcp.json \
  --output-format text \
  --no-session-persistence
```

`--no-session-persistence` prevents the invocation from writing session history to disk,
keeping each job run fully isolated.

## Output

DESIGN.md §4 (Claude Code Worker) updated with confirmed invocation details.
Issue 5-1 updated with implementation guidance.
`config.yaml.example` `agent` section is already correct — no additional fields needed.

## Definition of Done

All questions above answered with working example invocation. Implementation approach for
`agent/worker.py` confirmed. ✓

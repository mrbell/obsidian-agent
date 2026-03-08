# 4-2 — CLI: mcp Command

**Status**: `completed`
**Parent**: 4
**Children**: —
**Depends on**: 1-6, 4-1

## Description

Add the `mcp` command to `obsidian_agent/cli.py`. Starts the MCP server on stdio, used
both by the Claude Code worker and for manual registration in Claude Desktop.

## Implementation Notes

```
obsidian-agent mcp
```

Loads config, then calls `mcp.server.stdio.run(server)` (or equivalent from the `mcp` library).

The server process runs until killed. It communicates over stdin/stdout.

### Claude Desktop registration (for manual vault exploration)

Users can register the server in `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "obsidian-vault": {
      "command": "obsidian-agent",
      "args": ["mcp"],
      "env": {
        "OBSIDIAN_AGENT_CONFIG": "/path/to/config.yaml"
      }
    }
  }
}
```

Document this in the README.

## Testing & Validation

- `obsidian-agent mcp` starts without error
- Process stays alive until killed
- Can be registered and used in Claude Desktop

## Definition of Done

`obsidian-agent mcp` starts successfully and serves tool requests.

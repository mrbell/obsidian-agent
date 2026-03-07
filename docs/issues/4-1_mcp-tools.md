# 4-1 — MCP Server Tool Implementations

**Status**: `open`
**Parent**: 4
**Children**: —
**Depends on**: 1-3, 1-4

## Description

Implement the read-only MCP tools in `obsidian_agent/mcp/tools.py` and wire them into
the MCP server in `obsidian_agent/mcp/server.py` using the `mcp` Python library.

## Implementation Notes

### Tools to implement

| Tool | Inputs | Returns |
|---|---|---|
| `search_notes` | `query: str, limit: int = 10` | `list[{path, excerpt}]` |
| `get_note` | `path: str` | `str` (full content) |
| `list_notes` | `folder: str \| None, include_daily: bool = True` | `list[{path, title, mtime}]` |
| `get_daily_notes` | `start_date: str, end_date: str` | `list[{path, content}]` |
| `query_tasks` | `status: str = "open", due_before: str \| None = None` | `list[{text, note_relpath, due_date}]` |
| `get_note_links` | `path: str` | `{outgoing: [...], incoming: [...]}` |
| `find_notes_by_tag` | `tag: str` | `list[str]` |
| `get_vault_stats` | — | `{note_count, task_count, last_indexed_at}` |

### search_notes implementation

For v1, implement as a case-insensitive substring search across note content (read files
directly). DuckDB FTS extension is an option for v2 if performance warrants it.

### server.py

```python
import mcp.server.stdio
from mcp.server import Server

server = Server("obsidian-vault")

# register tools using @server.call_tool() and @server.list_tools() decorators
# tools call functions from tools.py
```

The server receives `vault_path` and `db_path` at startup (passed as CLI args or env vars).
It opens `IndexStore` on init and holds it for the lifetime of the process.

### No write tools

The server must not expose any tool that creates, modifies, or deletes files or DB records.
Code review: confirm no write operations exist anywhere in `mcp/`.

## Testing & Validation

Tests using a temp vault with known fixture notes and an in-memory DuckDB index:
- `get_note` returns correct content
- `list_notes` returns all notes; filters by folder
- `get_daily_notes` returns notes in range; excludes out-of-range notes
- `query_tasks` filters correctly by status and due_before
- `find_notes_by_tag` returns correct matches
- `get_note_links` returns outgoing and incoming links
- `search_notes` returns relevant results for a known query term

## Definition of Done

All tools implemented and tested. Server starts without error. No write operations present.

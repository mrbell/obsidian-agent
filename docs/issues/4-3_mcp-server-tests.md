# 4-3 — MCP Server Integration Tests

**Status**: `completed`
**Parent**: 4
**Children**: —
**Depends on**: 4-1, 4-2

## Description

Write integration tests that start the MCP server as a subprocess and exercise it through
the MCP protocol, verifying tool dispatch end-to-end.

## Implementation Notes

Use the `mcp` library's test client utilities if available, or communicate with the server
process over stdin/stdout directly in tests.

Fixture: a temp vault with a known set of notes covering all content types (tasks, links,
tags, daily notes, headings).

Test each tool with both valid and edge-case inputs:
- Valid query → expected result
- Empty result → empty list (not an error)
- Invalid path in `get_note` → appropriate error response (not a crash)

Also verify: the server rejects any attempt to call a write operation (should not be possible
since no write tools are registered, but confirm via `list_tools` response).

## Testing & Validation

All tools return correct results via MCP protocol in integration tests.

## Definition of Done

Integration test suite passes. `list_tools` returns only the expected read-only tools.

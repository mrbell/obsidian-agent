# 4 — MCP Server

**Status**: `open`
**Parent**: —
**Children**: 4-1, 4-2, 4-3, 4-4
**Depends on**: 1

## Description

Implement the read-only MCP server that exposes the vault and index to Claude Code. This
is the primary interface between Claude Code and vault content for all LLM-assisted jobs.

The MCP server runs as a local stdio subprocess registered with each Claude Code invocation.

## Prerequisites

Milestone 1 (Foundation) must be complete.

## Definition of Done

- `obsidian-agent mcp` starts the MCP server without errors
- All tools (search, get_note, list_notes, etc.) return correct results against a test vault
- Server exposes no write tools
- Can be registered in Claude Desktop for manual vault exploration
- See issue 4-4 (spike) for Claude Code invocation details needed before Milestone 5

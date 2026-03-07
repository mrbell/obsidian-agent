# 5 — Research Digest

**Status**: `open`
**Parent**: —
**Children**: 5-1, 5-2, 5-3
**Depends on**: 3, 4

## Description

Implement the research digest job and the Claude Code worker infrastructure it depends on.
Claude Code is invoked headlessly with the vault MCP server registered, uses web search to
gather recent articles on configured topics, and produces a structured markdown report
promoted to BotInbox.

## Prerequisites

- Milestone 3 (Promoter) must be complete
- Milestone 4 (MCP Server) must be complete, including spike 4-4 on Claude Code invocation

## Definition of Done

- `obsidian-agent run research_digest` invokes Claude Code and produces a report artifact
- Report is valid markdown with required sections (Trends, Notable Articles, Follow-up Questions)
- Malformed or empty output is rejected and logged; nothing is written to outbox
- `obsidian-agent agent test` confirms Claude Code is available and working
- Worker tested with a dummy command in place of `claude`

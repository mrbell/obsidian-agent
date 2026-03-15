# 1 — Foundation

**Status**: `completed`
**Parent**: —
**Children**: 1-1, 1-2, 1-3, 1-4, 1-5, 1-6
**Depends on**: —

## Description

Implement the core infrastructure that all jobs and components depend on: config loading,
logging, vault parsing, DuckDB index, and the CLI commands to build and inspect the index.

This milestone produces a working `obsidian-agent index` command that scans a vault and
populates the DuckDB index, and `obsidian-agent status` to inspect it.

## Prerequisites

None. This is the first milestone.

## Definition of Done

- `obsidian-agent index` runs against a real vault without errors
- `obsidian-agent status` shows accurate note/task counts
- Index correctly handles incremental updates (modify, delete, rename)
- Parser unit tests pass

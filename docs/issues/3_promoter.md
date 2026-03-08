# 3 — Promoter

**Status**: `open`
**Parent**: —
**Children**: 3-1, 3-2
**Depends on**: 1

## Description

Implement the promoter component and `obsidian-agent promote` CLI command. The promoter
is the only write path into the vault and must enforce strict safety rules.

## Prerequisites

Milestone 1 (Foundation) must be complete. Can be developed in parallel with Milestone 2.

## Definition of Done

- `obsidian-agent promote` copies eligible outbox artifacts to `BotInbox/<job>/`
- Skips files that already exist at the destination (no overwrite)
- Rejects symlinks, non-`.md` files, path traversal attempts
- Promoter safety test suite passes (see issue 3-1 for required test cases)

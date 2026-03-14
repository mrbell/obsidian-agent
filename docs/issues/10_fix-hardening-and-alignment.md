# 10 — Fix Hardening and Design Alignment

**Status**: `open`
**Parent**: —
**Children**: 10-1, 10-2, 10-3, 10-4, 10-5, 10-6, 10-7
**Depends on**: 1, 4, 5, 6, 8

## Description

Targeted follow-up fixes discovered during review of the implemented system against the
intended design. This milestone is not about adding new product surface area; it is about
closing correctness gaps, hardening runtime behavior, and tightening the contract between
docs, code, and MCP tooling.

The scope includes:

- aligning docs/config comments with actual semantic indexing behavior
- treating Claude worker `is_error` results as failures
- fixing cron command generation so logging and quoting are correct
- populating semantic entity context snippets and providing a backfill path
- normalizing wikilinks so incoming-link queries are structurally correct
- making SMTP delivery error handling match its contract
- tracking MCP search/per-token efficiency as a follow-up performance issue

## Working Method

All implementation work under this milestone should follow red/green TDD:

1. Add or update a failing test that captures the bug or contract mismatch
2. Implement the minimum change needed to make the test pass
3. Refactor only after the behavior is locked in by tests

## Child Issues

- **10-1**: Docs alignment for semantic throttling
- **10-2**: Worker handling for Claude `is_error` results
- **10-3**: Cron command quoting and full-chain log redirection
- **10-4**: Entity context snippet population and semantic backfill
- **10-5**: Wikilink normalization and incoming-link correctness
- **10-6**: SMTP delivery hardening for network/system failures
- **10-7**: MCP search performance and context-budget follow-up

## Definition of Done

- Each accepted fix has regression coverage
- Runtime behavior matches the documented contract in the touched areas
- No fix requires a full vault rebuild unless explicitly unavoidable
- DESIGN.md / README.md / config examples are updated where behavior changed or was clarified

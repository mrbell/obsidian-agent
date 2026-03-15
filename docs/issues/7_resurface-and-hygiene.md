# 7 — Resurface and Hygiene

**Status**: `completed`
**Children**: 7-1, 7-2
**Depends on**: 6 (Semantic Vault Intelligence — must be complete first)

## Vision

Two jobs that make the value of the semantic layer viscerally obvious to the user:

1. **Connections** (`vault_connections_report`): Surfaces old ideas and notes that are
   relevant to what the user has been thinking about recently. Corrects the recency bias
   and lossy memory that causes good ideas to be forgotten.

2. **Hygiene** (`vault_hygiene_report`): Compares the implicit structure inferred by the
   semantic layer against the explicit structure in the vault, and suggests improvements.
   Closes the loop — the system helps improve the vault itself.

Together, these jobs directly reinforce the virtuous cycle described in `docs/use_cases.md`:
the more richly the user writes, the more valuable these reports become, which motivates
richer writing.

## Anti-Patterns

- **No automated edits to the vault.** Both jobs produce suggestion reports only. The user
  decides what to act on. The promoter stays additive-only.
- **No rigid structure imposed.** Suggestions should work with whatever structure (or lack
  thereof) the user has. A suggestion that implies "you should use tags" or "you need a
  project folder" is wrong.

## Child Issues

- **7-1**: `vault_connections_report` — serendipitous resurface of old concepts and ideas
- **7-2**: `vault_hygiene_report` — implied tasks, standalone note suggestions, missing links

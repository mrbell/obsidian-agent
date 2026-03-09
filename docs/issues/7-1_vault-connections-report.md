# 7-1 — vault_connections_report

**Status**: `open`
**Parent**: 7
**Depends on**: 6-4, 6-5

## Description

A weekly Class B job that surfaces old vault content that is semantically connected to what
the user has been writing about recently. Corrects the recency bias and lossy memory that
causes good ideas and useful notes to be forgotten.

## What It Does

1. Identifies the user's **recent conceptual activity**: what concepts, entities, and ideas
   appear in notes modified in the last N days (default: 14).

2. Searches the **rest of the vault** for semantically related content that predates the
   recent window — notes, chunks, and implicit items that connect to recent themes but haven't
   been touched recently.

3. Generates a report highlighting the most interesting connections, with brief synthesis of
   why they are relevant to what's on the user's mind now.

## Why This Is Valuable

Human memory is recency-biased and lossy. Ideas written months or years ago are effectively
invisible until something triggers recall. This job acts as that trigger — systematically,
weekly, without the user having to remember to look.

The virtuous cycle effect: the more richly the user writes, the more raw material there is
for connections. A brief note logged today about a book or idea may surface as a valuable
connection months later.

## Output

`VaultArtifact` deposited in `BotInbox/vault_connections_report/`. Weekly.

Suggested format:

```markdown
# Vault Connections — 2026-03-09

## What you've been thinking about (last 14 days)
[Brief synthesis of recent themes from recent note activity]

## Connections worth revisiting

### [Old Note Title]
**Written**: [date]  **Last touched**: [date]
[2-3 sentences on why this connects to recent themes. What was interesting about it then.
What might be worth revisiting now.]

### [Another Note]
...

## Implicit items that connect to your recent thinking
[Informal ideas or questions extracted from older notes that relate to current themes]
```

## Implementation

**Class B job** (LLM synthesis, no web search).

Inputs to the prompt:
- Recent notes summary: titles + summaries (from `note_intelligence`) for notes modified
  in the last `lookback_recent_days` (default: 14)
- Top recent concepts: from `chunk_concepts` for those notes
- Related older content: results from `find_related_notes` and `search_by_concept` scoped
  to notes *outside* the recent window
- Implicit items from older notes that match recent concepts

The prompt asks Claude to synthesize the connections — not just list them — and explain
concretely why each is relevant to what the user is working on now.

Claude uses MCP tools (`get_note_summary`, `find_related_notes`, `search_by_concept`,
`get_implicit_items`) rather than receiving all data injected in the prompt. This lets it
selectively deepen on the most interesting connections.

## Configuration

```yaml
jobs:
  vault_connections_report:
    enabled: true
    schedule: "0 9 * * 1"   # Monday morning
    lookback_recent_days: 14  # what counts as "recent" activity
    lookback_old_days: 30     # minimum age for "old" content to surface
    max_connections: 5        # max items in the report
    also_notify: true
```

## Definition of Done

- Job produces a coherent, non-generic report on a real vault
- Connections cited are genuinely meaningful (not just superficial keyword overlap)
- Report is not produced if insufficient semantic data exists (semantic index not built)
- Incremental safety: producing the report does not modify the semantic index

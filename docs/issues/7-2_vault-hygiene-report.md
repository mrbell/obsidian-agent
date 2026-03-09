# 7-2 — vault_hygiene_report

**Status**: `open`
**Parent**: 7
**Depends on**: 6-4, 6-5

## Description

A periodic Class B job that compares the implicit structure inferred by the semantic layer
against the explicit structure in the vault, and produces a report of suggestions for
improvement. Closes the loop: the system helps improve the vault it reads from.

All output is suggestions only. No automated edits. The user decides what to act on.

## What It Looks For

### 1. Implied tasks not formally captured

`implicit_items` of type `task` or `intention` that do not have a corresponding formal
`- [ ]` task in the same or nearby note. The user expressed something action-like in prose
but never formalized it.

Example: "I need to follow up with Alice about the proposal" buried in a daily note, with
no matching task entry.

### 2. Ideas worth a standalone note

`implicit_items` of type `idea` that appear across multiple notes or chunks, or have high
salience in concept extraction — suggesting the idea is recurring and developed enough to
deserve its own note rather than being scattered across daily entries.

Example: An idea about "the tension between structure and creativity in note-taking" that
appears in five separate daily notes over three months.

### 3. Missing wikilinks

Pairs of notes that are highly semantically related (via `find_related_notes`) but have no
explicit link between them. A suggested wikilink surfaces the implicit connection.

Only suggest links where the relationship is strong and specific — not just "both notes
mention productivity."

### 4. Orphaned threads

Ideas, intentions, or questions that appeared with high salience in a past period but have
not been mentioned since and have no formal follow-up. The user expressed strong interest
in something and then the thread went cold.

Example: Several notes in April expressing intent to learn a new skill, then silence.

## Output

`VaultArtifact` deposited in `BotInbox/vault_hygiene_report/`. Bi-weekly or monthly.

Suggested format:

```markdown
# Vault Hygiene Report — 2026-03-09

## Implied tasks not formally captured
- **"Follow up with Alice about the proposal"** — from [[2026-02-14]] daily note
  *(Consider adding as a formal task so it's trackable)*
- ...

## Ideas that might deserve their own note
- **Latent structure in knowledge bases** — mentioned across 5 daily notes since January.
  Your most developed thinking is in [[2026-01-22]] and [[2026-02-10]].
  *(Consider synthesizing into a standalone note)*

## Possible missing wikilinks
- [[Note A]] and [[Note B]] both develop the concept of "deliberate practice" but aren't linked.
- ...

## Threads that went quiet
- You wrote several times in April about learning Rust. No recent mention.
  *(Still relevant? Consider a task or an explicit decision to drop it.)*
```

## Implementation

**Class B job** (LLM synthesis, no web search).

This job queries both the structural index and the semantic index:
- Structural: formal tasks, existing wikilinks, note modification dates
- Semantic: implicit items, concept salience, note similarity scores

The cross-index comparison is the key operation. Claude is given summaries and asked to
synthesize suggestions; it can use MCP tools (`get_implicit_items`, `query_tasks`,
`get_note_links`, `find_related_notes`) to pull details on demand.

The prompt should emphasize:
- Suggestions only — no judgment about "bad" vault organization
- Work with whatever structure exists, don't suggest adopting a new system
- Be specific: reference actual note names and actual text, not generic advice

## Configuration

```yaml
jobs:
  vault_hygiene_report:
    enabled: true
    schedule: "0 10 1,15 * *"   # 1st and 15th of the month
    min_idea_note_count: 3       # min notes mentioning an idea to flag it
    min_similarity_score: 0.75   # threshold for missing wikilink suggestion
    also_notify: true
```

## Definition of Done

- Job produces a useful, specific report on a real vault (not generic platitudes)
- Each suggestion cites actual note names and text excerpts
- Report gracefully handles vaults with no implicit items (semantic index not yet built)
- Suggestions respect the anti-goal: no structural system is implied or imposed

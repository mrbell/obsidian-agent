# 6-3 — Concept and Entity Extraction (Intelligence Phase)

**Status**: `completed`
**Parent**: 6
**Depends on**: 6-1, 6-2

**Known gap**: Implementation associates all concepts and entities with `chunk_ids[0]`
rather than the chunk where they actually appear. The schema supports per-chunk
association (chunk_concepts/chunk_entities use chunk_id as PK component). Fix requires:
updating the extraction prompt to include `chunk_index` on each concept and entity,
and mapping to the correct chunk_id in `_store_extraction`. Track as a follow-up issue
before M7 jobs consume concept data.

## Description

The intelligence phase of `obsidian-agent index-semantic`. For each note with stale or missing
`note_intelligence`, call the Claude Code worker with the note's chunks and ask it to extract:
- Concepts (recurring themes, topics, ideas discussed)
- Entities (people, projects, tools, books, places explicitly mentioned)
- Implicit items (informal ideas, questions, and intentions buried in prose that were never
  formally tagged)
- A 2-4 sentence summary of the note

This phase runs after the embedding phase (6-2) and uses the same `index-semantic` command.

## What "Implicit Items" Means

The user writes stream-of-consciousness daily notes and doesn't always formalize ideas as
tasks or project notes. The extraction should surface:

- **idea**: "It would be interesting to try X" — an undeveloped concept worth revisiting
- **question**: "I wonder why Y works the way it does" — an open question
- **intention**: "I want to look into Z at some point" — a low-commitment future plan
- **task**: "Need to email Alice about the report" — an action item not captured as a `- [ ]`

These complement (not replace) formally tagged tasks. The goal is to avoid losing things
that were thought but not formalized.

## LLM Extraction Approach

Unlike Class B/C jobs, this does **not** use the MCP server. The orchestrator reads note
chunks directly from the DB (they were just indexed) and injects them into the prompt.
This avoids unnecessary MCP round-trips and keeps the prompt fully predictable.

**Per-note prompt** (send all chunks for one note in a single call):

```
You are analyzing a note from a personal Obsidian knowledge base.
Note path: {note_relpath}

Content (by paragraph):
---
{chunk_1_text}
---
{chunk_2_text}
---
...

Extract the following. Respond ONLY with valid JSON matching this schema — no preamble.

{
  "summary": "2-4 sentence summary of what this note is about.",
  "concepts": [
    {"name": "concept name (lowercase)", "salience": 0.0-1.0}
  ],
  "entities": [
    {"name": "entity name", "type": "person|project|tool|book|place|other"}
  ],
  "implicit_items": [
    {"type": "idea|question|intention|task", "text": "the item text", "chunk_index": 0}
  ]
}

Guidelines:
- concepts: recurring topics, themes, and ideas discussed. 3-10 per note is typical.
  salience: 1.0 = the note is primarily about this, 0.3 = mentioned in passing.
- entities: proper nouns — specific people, named projects, software tools, book titles,
  locations. Not generic terms.
- implicit_items: only things not already captured as formal tasks (- [ ] ...) in the note.
  Focus on items buried in prose. Do not invent items not present.
- If a field would be an empty list, return [].
```

**Output parsing**: Extract the JSON object from the worker's text output. The response
may include minor prose around the JSON if the model is verbose — use a JSON object
extraction heuristic (find `{...}` block) rather than strict parsing.

**Worker call**: Use `web_search=False, with_mcp=False`. No MCP server or web needed.
The note content is passed directly in the prompt.

## Incremental Logic

A note needs intelligence extraction when `note_intelligence` row is missing or was deleted
(which happens whenever its content changes — see 6-2).

On extraction success:
- Upsert `note_intelligence` (summary, extracted_at, model_version)
- Upsert `concepts` (insert new concept names, get IDs for existing)
- Insert `chunk_concepts` rows (linking chunk_id to concept_id with salience)
- Upsert `entities`
- Insert `chunk_entities`
- Delete old `implicit_items` for this note, insert new ones

All in a single transaction per note.

## Concept Canonicalization

Before inserting a concept, lowercase and strip it. The `concepts` table has `UNIQUE` on
`name` so duplicates are naturally deduplicated across notes. For fuzzy merging (e.g.
"note-taking" vs "note taking"), that can be a future enhancement — start simple.

## Cost and Rate Limiting

With ~316 notes and incremental processing, most runs will process 0-5 notes (those changed
since last run). Initial full-vault extraction is the expensive case: ~316 LLM calls.

Add a configurable `max_notes_per_run` option (default: unlimited) so the user can throttle
the initial run if needed. Log progress (note X of Y) so it doesn't look hung.

If a worker call fails (timeout, error), log and skip that note. It will be retried next run
since `note_intelligence` won't have been written.

## Configuration

Add to `config.yaml` under a new `semantic` section:

```yaml
semantic:
  model: all-MiniLM-L6-v2    # embedding model name
  max_notes_per_run: null     # null = unlimited; set integer to throttle initial run
```

## Tests

- `test_concept_extraction.py`:
  - Mock worker to return a fixed JSON response
  - Verify concepts, entities, implicit_items are stored correctly
  - Verify idempotency: re-running on the same note replaces (not duplicates) old results
  - Verify a worker error skips the note without writing partial results

## Definition of Done

- Intelligence phase runs after embedding phase in `index-semantic`
- Concepts, entities, and implicit items stored in DB for a real vault
- `note_intelligence.summary` populated for all processed notes
- Incremental: second run with no vault changes processes 0 notes
- Worker errors are logged and skipped gracefully

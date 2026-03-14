# 10-4 — Entity Context Snippets and Semantic Backfill

**Status**: `open`
**Parent**: 10
**Children**: —
**Depends on**: 6-3, 6-5

## Description

`get_entity_context` advertises a context snippet for each entity match, but the semantic
index currently stores `NULL` for `chunk_entities.context_snippet`. This issue makes the
field real and adds a backfill path so existing indexes can be repaired without requiring
a full rebuild.

## Implementation Notes

### Runtime behavior

- Update semantic extraction storage in `obsidian_agent/index/semantic.py`
- Populate `chunk_entities.context_snippet` using the referenced chunk text
- The snippet should be short and useful for display:
  - centered on the entity name when possible
  - otherwise a clipped excerpt from the chunk
- Update MCP docs/comments if the returned field name or shape needs tightening

### Backfill / patch path

Add a targeted maintenance path to populate missing snippets for already-indexed rows
without recomputing embeddings or rerunning Claude extraction for every note.

Possible implementations:

- a one-off CLI command under `obsidian-agent`
- a narrow patch script under `scripts/`
- a small index maintenance function invoked explicitly

The backfill should:

- scan `chunk_entities` rows with `context_snippet IS NULL`
- join to `chunks.text`
- derive snippets deterministically
- update rows in place

## Testing & Validation

Red/green TDD:

- Add failing tests for semantic extraction storage or MCP entity-context responses
- Assert snippets are populated for new writes
- Add failing tests for the backfill path against a DB fixture with `NULL` snippets
- Verify the backfill does not require re-embedding or full rebuild

## Definition of Done

- New semantic indexing writes non-null context snippets
- Existing DBs can be patched in place
- `get_entity_context` returns useful context for both new and backfilled data

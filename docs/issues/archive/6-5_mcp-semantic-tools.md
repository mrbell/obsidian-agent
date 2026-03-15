# 6-5 — MCP Semantic Tools

**Status**: `completed`
**Parent**: 6
**Depends on**: 6-4

## Description

Expose the semantic index through new MCP server tools. These tools are the payoff of the
whole milestone: they make rich vault context available to Claude during any session —
scheduled jobs, Claude Desktop, or a normal Claude Code chat — without the user having to
think about it.

The new tools are additive; all existing tools from Milestone 4 remain unchanged.

## New Tools

### `search_similar(query, n?)`

Semantic search over vault chunks. Embeds `query` using the local model and finds the N
most semantically similar chunks.

```
search_similar(query: str, n: int = 10) -> list[ChunkResult]
```

Returns: note path, section header, chunk text, similarity score. Groups results by note
so the caller can see which notes are most relevant overall.

**Use case**: "What has the user written about motivation and procrastination?" — returns
relevant paragraphs even if those exact words don't appear.

**Implementation note**: The MCP server must load the `LocalEmbedder` at startup (lazy,
first call) since it takes a moment to initialize. Cache it as a module-level singleton.

### `get_note_summary(note_relpath)`

Return the LLM-generated summary for a note, falling back to None if not yet extracted.

```
get_note_summary(note_relpath: str) -> str | None
```

**Use case**: Claude can quickly understand what a note is about without reading all of it.
Especially useful for long daily notes.

### `find_related_notes(note_relpath, n?)`

Find notes most conceptually related to a given note (by concept overlap score).

```
find_related_notes(note_relpath: str, n: int = 5) -> list[dict]
```

Returns: note path, overlap score, summary (if available).

**Use case**: "What else has the user written that's relevant to what this note is about?"

### `list_concepts(n?)`

Return the most prominent concepts across the vault, ranked by number of notes they appear in.

```
list_concepts(n: int = 30) -> list[ConceptSummary]
```

Returns: concept name, note count, average salience.

**Use case**: Gives Claude a quick map of the user's conceptual landscape before deciding
what to retrieve.

### `search_by_concept(concept, n?)`

Find notes and chunks that discuss a given concept.

```
search_by_concept(concept: str, n: int = 10) -> list[ChunkResult]
```

Does a case-insensitive substring match on concept names, then returns the top chunks by
salience.

**Use case**: "Show me everything the user has written about 'second brain'."

### `get_entity_context(name, n?)`

Find all vault chunks mentioning a named entity (person, project, tool, book, etc.).

```
get_entity_context(name: str, n: int = 10) -> list[dict]
```

Returns: note path, chunk text, context snippet.

**Use case**: "What does the user know/think about Obsidian? What projects are they tracking?"

### `get_recent_concepts(days?, n?)`

Return the most active concepts in notes modified within the last N days. Used by M7 jobs
to understand what the user has been thinking about recently before querying for older
related content.

```
get_recent_concepts(days: int = 14, n: int = 20) -> list[ConceptSummary]
```

### `get_implicit_items(type?, since?)`

Return informal ideas, questions, intentions, or tasks extracted from vault prose.

```
get_implicit_items(
    type: str | None = None,    # 'idea' | 'question' | 'intention' | 'task' | None = all
    since: str | None = None,   # ISO date string; filter by note modification date
    n: int = 20
) -> list[ImplicitItem]
```

**Use case**: "What ideas or intentions has the user had recently that they haven't acted on?"

## Graceful Degradation

All new tools should handle the case where the semantic index has not been built yet (no
rows in `chunks`, `chunk_embeddings`, etc.) by returning an empty list with an explanatory
message rather than raising an error. This lets the MCP server be registered in Claude
Desktop before `index-semantic` has ever been run.

## MCP Server Updates

- Add `LocalEmbedder` singleton initialization in `server.py` (lazy, on first `search_similar` call)
- The embedder model name should come from config (`semantic.model`)
- All new tools registered in `tools.py` alongside existing tools
- Update `server.py` to pass the embedder instance to tool handlers that need it

## Updated Tool Table (for DESIGN.md)

| Tool | Description |
|---|---|
| `search_notes(query, limit)` | Full-text keyword search across all notes |
| `get_note(path)` | Full content of a note by relative path |
| `list_notes(folder, include_daily)` | List notes, optionally filtered by folder |
| `get_daily_notes(start_date, end_date)` | Daily notes in a date range with content |
| `query_tasks(status, due_before)` | Tasks from the structural index |
| `get_note_links(path)` | Outgoing and incoming links for a note |
| `find_notes_by_tag(tag)` | Notes with a given tag |
| `get_vault_stats()` | Note count, task count, last indexed, etc. |
| `search_similar(query, n)` | **[NEW]** Semantic search over vault chunks |
| `get_note_summary(note_relpath)` | **[NEW]** LLM-generated summary for a note |
| `find_related_notes(note_relpath, n)` | **[NEW]** Notes most conceptually related to a note |
| `list_concepts(n)` | **[NEW]** Prominent concepts across the vault |
| `search_by_concept(concept, n)` | **[NEW]** Notes/chunks tagged with a concept |
| `get_entity_context(name, n)` | **[NEW]** Chunks mentioning a named entity |
| `get_recent_concepts(days, n)` | **[NEW]** Most active concepts in recently modified notes |
| `get_implicit_items(type, since, n)` | **[NEW]** Informal ideas, questions, intentions from prose |

## Tests

Extend `tests/test_mcp_tools.py`:
- Each new tool against a temp vault + DB populated with fixture semantic data
- `search_similar`: mock the embedder; verify results are ordered by score
- `get_implicit_items`: verify type filtering and ordering
- Graceful degradation: verify each tool returns empty list when semantic index is absent

## Definition of Done

- All 7 new tools implemented, registered, and returning correct results
- Graceful degradation verified for each tool when index is absent
- `search_similar` works end-to-end with real embeddings on a real vault
- Tools appear correctly when MCP server is registered in Claude Desktop
- DESIGN.md §4 (MCP Server) updated with new tool table

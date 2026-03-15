# 6 — Semantic Vault Intelligence

**Status**: `completed`
**Children**: 6-1, 6-2, 6-3, 6-4, 6-5

## Vision

Give Claude a rich, ambient understanding of the vault's conceptual landscape — not just its
file structure. The goal is that during any Claude session (chat, coding, job invocation),
Claude can retrieve semantically relevant vault content, understand recurring concepts and
entities, and surface informal ideas, intentions, and questions that were never formally tagged.

**Target use case**: When the user is working on something in Claude, the vault MCP server
can answer questions like "what has the user written about X?", "what notes are related to
this idea?", "what implicit intentions exist in recent daily notes?" — by querying a
pre-computed semantic index rather than reading every note on demand.

## Key Decisions

| Question | Decision |
|---|---|
| Embedding model | `all-MiniLM-L6-v2` (local, 384-dim); abstracted behind `Embedder` interface |
| Chunking granularity | Paragraph-level, section-aware (not note-level — notes are too diverse) |
| Concept extraction granularity | Per-chunk (same reason as above) |
| Update strategy | Incremental: only process notes changed since last run |
| Scheduling | Daily scheduled job; not on-demand |
| Command | Separate `obsidian-agent index-semantic`; does not fold into `index` |
| Intelligence extraction | Claude Code worker; prompt includes note chunks directly (no MCP round-trip needed) |

## Architecture

This milestone adds a second indexing pipeline alongside the existing structural index:

```
Vault (read-only)
    |
    |-- [existing] obsidian-agent index -------> structural index (notes, tasks, links, tags)
    |
    +-- [new] obsidian-agent index-semantic ---> semantic index
            |
            +-- Embedding phase (local model, no LLM)
            |       Chunk notes → embed chunks → store in DuckDB with VSS
            |
            +-- Intelligence phase (Claude Code worker)
                    Per changed note: extract concepts, entities, implicit items,
                    generate summary → store in DuckDB
```

The MCP server gains new tools that query the semantic index. These are available both to
scheduled jobs (Class B/C) and to the user's own Claude sessions via Claude Desktop or
Claude Code.

## New Components

| Component | Purpose |
|---|---|
| `obsidian_agent/embeddings/` | `Embedder` ABC + `LocalEmbedder` using sentence-transformers |
| `obsidian_agent/index/chunker.py` | Paragraph/section-aware note splitter |
| `obsidian_agent/index/semantic.py` | Incremental semantic index build logic |
| New DB tables | `chunks`, `chunk_embeddings`, `note_intelligence`, `concepts`, `chunk_concepts`, `entities`, `chunk_entities`, `implicit_items` |
| New MCP tools | `search_similar`, `get_note_summary`, `find_related_notes`, `list_concepts`, `search_by_concept`, `get_entity_context`, `get_implicit_items` |
| New CLI command | `obsidian-agent index-semantic` |

## Child Issues

- **6-1**: Embedding infrastructure — `Embedder` abstraction, chunking logic, DB schema, DuckDB VSS
- **6-2**: Semantic index job — incremental embedding pipeline (`index-semantic` embedding phase)
- **6-3**: Concept and entity extraction — intelligence phase; Claude Code extracts per-chunk concepts, entities, and implicit items; generates per-note summary
- **6-4**: Concept graph queries — DuckDB views and query helpers over the extracted data
- **6-5**: MCP semantic tools — new MCP tools exposing the semantic index to Claude

## Definition of Done

- `obsidian-agent index-semantic` runs successfully on a real vault, incrementally
- All new MCP tools are implemented and tested
- The MCP server registered in Claude Desktop provides meaningfully richer vault context
  than keyword search alone
- DESIGN.md updated to reflect final implementation

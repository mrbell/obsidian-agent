# 1-4 — DuckDB Schema and Store

**Status**: `open`
**Parent**: 1
**Children**: —
**Depends on**: 1-1

## Description

Implement `obsidian_agent/index/store.py` and `obsidian_agent/index/schema.sql`.

The store opens a DuckDB connection and initialises the schema. It is the single point of
access to the index database.

## Implementation Notes

### Schema (from DESIGN.md §6)

```sql
notes, frontmatter, headings, tasks, links, tags
```

Plus future tables stubbed as `CREATE TABLE IF NOT EXISTS` (note_summaries, topic_clusters)
so the schema file is the authoritative definition of all tables.

### store.py

- `class IndexStore`
  - `__init__(db_path: Path)` — opens DuckDB connection, runs schema init
  - `conn` — exposes the raw DuckDB connection for queries
  - `close()` — closes connection
  - Context manager support (`__enter__` / `__exit__`)

Schema SQL is loaded from `index/schema.sql` at init time, not hardcoded in Python.

### No ORM

Use DuckDB's Python API directly with parameterised queries. No SQLAlchemy or similar.

## Testing & Validation

- `IndexStore` initialises against a temp file path without error
- All tables exist after init
- Re-initialising against an existing DB is idempotent (`CREATE TABLE IF NOT EXISTS`)
- Context manager closes connection cleanly

## Definition of Done

`IndexStore` opens, initialises schema, and closes without errors. All tables present.

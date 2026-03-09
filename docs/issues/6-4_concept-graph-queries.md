# 6-4 — Concept Graph Queries

**Status**: `open`
**Parent**: 6
**Depends on**: 6-3

## Description

Build the query layer over the extracted semantic data. This is primarily DuckDB views and
query helper functions in `index/queries.py` (or a new `index/semantic_queries.py`). The
graph is implicit in the relational tables — notes share concepts, concepts co-occur in chunks,
entities appear across notes — and these queries make it traversable.

No new data is generated here. This is about making the data in `chunks`, `concepts`,
`entities`, `implicit_items`, and `note_intelligence` queryable in useful ways.

## Key Queries to Implement

### Time-windowed concept activity

Required by M7 jobs: "what has the user been thinking about recently?" and "what's old
enough to be worth resurfacing?"

```sql
-- Top concepts in notes modified within the last N days
SELECT con.name, COUNT(DISTINCT c.note_relpath) AS note_count, MAX(cc.salience) AS peak_salience
FROM chunk_concepts cc
JOIN chunks c ON c.id = cc.chunk_id
JOIN concepts con ON con.id = cc.concept_id
JOIN notes n ON n.note_relpath = c.note_relpath
WHERE n.mtime_ns >= $since_ns   -- epoch nanoseconds
GROUP BY con.name
ORDER BY note_count DESC, peak_salience DESC
LIMIT $n;
```

Wrap as `get_recent_concepts(conn, since_days, n) -> list[ConceptSummary]`.

Also provide the inverse: `get_older_notes_by_concepts(conn, concept_names, newer_than_days, n)`
— notes discussing those concepts whose `mtime_ns` is *older* than the recent window.
This is the core query for `vault_connections_report`.

### Cross-index: implicit vs. explicit structure

Required by `vault_hygiene_report`. Compares semantic extraction against structural index.

```sql
-- Implicit items (type=task/intention) with no nearby formal task
SELECT ii.note_relpath, ii.type, ii.text
FROM implicit_items ii
LEFT JOIN tasks t ON (
    t.note_relpath = ii.note_relpath
    AND t.status = 'open'
    AND t.text ILIKE '%' || SPLIT_PART(ii.text, ' ', 1) || '%'
)
WHERE ii.type IN ('task', 'intention')
  AND t.line_no IS NULL;

-- Highly similar note pairs with no existing wikilink between them
SELECT r.note_relpath AS note_a, r.related_relpath AS note_b, r.overlap_score
FROM (
    -- related notes query from above, across all note pairs
) r
LEFT JOIN links l ON (
    l.note_relpath = r.note_a AND l.target LIKE '%' || REPLACE(r.note_b, '.md', '') || '%'
)
WHERE l.note_relpath IS NULL
  AND r.overlap_score >= $min_score;
```

Wrap as `find_unlinked_related_notes(conn, min_score) -> list[tuple[str, str, float]]`
and `find_unformalized_tasks(conn) -> list[ImplicitItem]`.

### Semantic similarity search

Given an embedding vector (from a query string), find the N most similar chunks:

```sql
-- Requires DuckDB VSS extension (loaded in IndexStore)
SELECT
    c.note_relpath,
    c.chunk_index,
    c.section_header,
    c.text,
    array_cosine_similarity(ce.embedding, $query_vector::FLOAT[384]) AS score
FROM chunk_embeddings ce
JOIN chunks c ON c.id = ce.chunk_id
ORDER BY score DESC
LIMIT $n;
```

Wrap in `semantic_queries.search_similar(conn, query_vector, n) -> list[ChunkResult]`.

### Related notes

Given a note, find other notes that share the most concepts (weighted by salience):

```sql
SELECT
    cc2.note_relpath,
    SUM(cc1.salience * cc2.salience) AS overlap_score
FROM chunk_concepts cc1
JOIN chunks c1 ON c1.id = cc1.chunk_id AND c1.note_relpath = $note_relpath
JOIN chunk_concepts cc2 ON cc2.concept_id = cc1.concept_id
JOIN chunks c2 ON c2.id = cc2.chunk_id AND c2.note_relpath != $note_relpath
GROUP BY cc2.note_relpath
ORDER BY overlap_score DESC
LIMIT $n;
```

### Concept lookup

Find all chunks (and their notes) that discuss a given concept (exact or fuzzy match):

```sql
SELECT c.note_relpath, c.text, cc.salience
FROM chunk_concepts cc
JOIN chunks c ON c.id = cc.chunk_id
JOIN concepts con ON con.id = cc.concept_id
WHERE con.name = $concept_name
ORDER BY cc.salience DESC;
```

### Entity context

Find all chunks mentioning a named entity:

```sql
SELECT c.note_relpath, c.text, ce.context_snippet
FROM chunk_entities ce
JOIN chunks c ON c.id = ce.chunk_id
JOIN entities e ON e.id = ce.entity_id
WHERE e.name = $entity_name;
```

### Implicit items by type

```sql
SELECT note_relpath, type, text, extracted_at
FROM implicit_items
WHERE type = $type   -- 'idea' | 'question' | 'intention' | 'task'
ORDER BY extracted_at DESC;
```

### Top concepts across vault

```sql
SELECT con.name, COUNT(DISTINCT c.note_relpath) AS note_count, AVG(cc.salience) AS avg_salience
FROM chunk_concepts cc
JOIN concepts con ON con.id = cc.concept_id
JOIN chunks c ON c.id = cc.chunk_id
GROUP BY con.name
ORDER BY note_count DESC, avg_salience DESC
LIMIT $n;
```

## DuckDB Views

Consider materializing frequently-used joins as views to simplify the MCP tool implementations:

```sql
CREATE OR REPLACE VIEW note_concepts_summary AS
SELECT
    c.note_relpath,
    con.name AS concept,
    MAX(cc.salience) AS salience
FROM chunk_concepts cc
JOIN chunks c ON c.id = cc.chunk_id
JOIN concepts con ON con.id = cc.concept_id
GROUP BY c.note_relpath, con.name;

CREATE OR REPLACE VIEW note_entities_summary AS
SELECT DISTINCT c.note_relpath, e.name AS entity, e.type AS entity_type
FROM chunk_entities ce
JOIN chunks c ON c.id = ce.chunk_id
JOIN entities e ON e.id = ce.entity_id;
```

## Result Types

Define typed dataclasses for query results (in `index/semantic_queries.py`):

```python
@dataclass(frozen=True)
class ChunkResult:
    note_relpath: str
    chunk_index: int
    section_header: str | None
    text: str
    score: float        # similarity score or salience

@dataclass(frozen=True)
class ConceptSummary:
    name: str
    note_count: int
    avg_salience: float

@dataclass(frozen=True)
class ImplicitItem:
    note_relpath: str
    type: str
    text: str
```

## Tests

- `test_semantic_queries.py`: populate a temp DB with fixture data (no model, no LLM);
  verify each query function returns correct results
- Test edge cases: no results, single note, concept with no chunks

## Definition of Done

- All query functions implemented in `index/semantic_queries.py`
- Views defined and created on `IndexStore` init (or lazily)
- Each query function has at least one test with fixture data
- Query functions return typed dataclasses, not raw tuples

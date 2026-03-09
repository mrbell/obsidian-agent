# 6-1 — Embedding Infrastructure

**Status**: `open`
**Parent**: 6
**Depends on**: (none — pure infrastructure)

## Description

Lay the technical foundation for semantic indexing: the `Embedder` abstraction, paragraph-level
chunking logic, new DuckDB tables (with VSS extension), and the `sentence-transformers`
dependency. Nothing runs automatically yet — this is the plumbing that 6-2 and 6-3 build on.

## Embedder Abstraction

New package: `obsidian_agent/embeddings/`

```python
# base.py
from abc import ABC, abstractmethod

class Embedder(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Returns one vector per text."""
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Size of the embedding vectors produced by this model."""
        ...

# local.py
class LocalEmbedder(Embedder):
    """sentence-transformers with all-MiniLM-L6-v2 (384-dim, ~80MB)."""

    DEFAULT_MODEL = "all-MiniLM-L6-v2"

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None: ...
    def embed(self, texts: list[str]) -> list[list[float]]: ...

    @property
    def dimension(self) -> int:
        return 384
```

The `Embedder` ABC makes it straightforward to swap in a different model (larger local model,
OpenAI API, etc.) later without touching the indexing logic.

`sentence-transformers` downloads model weights on first use (~80MB). Subsequent runs use the
cached weights. No network access needed after initial download.

## Chunking Logic

New module: `obsidian_agent/index/chunker.py`

**Strategy**: Split note content on blank lines (paragraph boundaries). Tag each chunk with
the most recent `##`-or-deeper heading seen above it, if any.

**Rules**:
- Minimum chunk length: ~50 tokens (skip very short runs — isolated headers, single-word lines)
- Maximum chunk length: ~400 tokens (split at sentence boundaries if exceeded)
- Preserve the section header as metadata even if it doesn't appear in chunk text

**Output per chunk**:
```python
@dataclass(frozen=True)
class Chunk:
    note_relpath: str
    chunk_index: int        # 0-based position within note
    section_header: str | None  # nearest ## heading above this chunk
    text: str
    token_count: int
```

Token count can be approximate (word count × 1.3 is a reasonable estimate without loading
a tokenizer).

## Database Schema

New tables added to `index/store.py` (created alongside existing tables on `IndexStore` init):

```sql
-- Paragraph-level chunks of note content
CREATE TABLE IF NOT EXISTS chunks (
    id              TEXT PRIMARY KEY,   -- "{note_relpath}:{chunk_index}"
    note_relpath    TEXT NOT NULL,
    chunk_index     INTEGER NOT NULL,
    section_header  TEXT,               -- NULL if not under a heading
    text            TEXT NOT NULL,
    token_count     INTEGER,
    embedded_at     TIMESTAMP           -- NULL until embedding phase runs
);

-- Vector embeddings for chunks (separate table; bulk-loaded with VSS)
CREATE TABLE IF NOT EXISTS chunk_embeddings (
    chunk_id        TEXT PRIMARY KEY,
    embedding       FLOAT[384]          -- all-MiniLM-L6-v2 dimension; update if model changes
);

-- Per-note LLM-extracted intelligence
CREATE TABLE IF NOT EXISTS note_intelligence (
    note_relpath    TEXT PRIMARY KEY,
    summary         TEXT,               -- 2-4 sentence LLM-generated summary
    extracted_at    TIMESTAMP,
    model_version   TEXT                -- e.g. "claude-sonnet-4-6"
);

-- Concepts extracted from chunks
CREATE TABLE IF NOT EXISTS concepts (
    id              INTEGER PRIMARY KEY,
    name            TEXT UNIQUE         -- canonical lowercase form
);

-- Concept mentions per chunk (many-to-many)
CREATE TABLE IF NOT EXISTS chunk_concepts (
    chunk_id        TEXT NOT NULL,
    concept_id      INTEGER NOT NULL,
    salience        REAL,               -- 0.0–1.0; how central is this concept to the chunk
    PRIMARY KEY (chunk_id, concept_id)
);

-- Named entities extracted from chunks
CREATE TABLE IF NOT EXISTS entities (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    type            TEXT NOT NULL       -- person | project | tool | book | place | other
);

-- Entity mentions per chunk
CREATE TABLE IF NOT EXISTS chunk_entities (
    chunk_id        TEXT NOT NULL,
    entity_id       INTEGER NOT NULL,
    context_snippet TEXT,               -- short surrounding text for display
    PRIMARY KEY (chunk_id, entity_id)
);

-- Informal ideas, questions, and intentions extracted from chunks
-- (things never formally tagged as tasks or noted in frontmatter)
CREATE TABLE IF NOT EXISTS implicit_items (
    id              INTEGER PRIMARY KEY,
    chunk_id        TEXT NOT NULL,
    note_relpath    TEXT NOT NULL,      -- denormalized for efficient queries
    type            TEXT NOT NULL,      -- idea | question | intention | task
    text            TEXT NOT NULL,
    extracted_at    TIMESTAMP
);
```

**DuckDB VSS extension**: Load via `INSTALL vss; LOAD vss;` on connection. Required for
`array_cosine_similarity` and efficient ANN search over `chunk_embeddings`. Add to
`IndexStore.__init__` alongside existing schema init.

## Dependency

Add to `pyproject.toml`:
```
sentence-transformers>=3.0
```

This pulls in `torch` (CPU-only is fine for inference). First run will download the model
weights. Document this in the README/setup notes.

## Tests

- `test_chunker.py`: verify paragraph splitting, section header tagging, minimum length
  filtering, long-chunk splitting
- `test_embedder.py`: verify `LocalEmbedder` produces vectors of correct dimension; mock
  `sentence_transformers` to avoid loading the model in CI

## Definition of Done

- `Embedder` ABC and `LocalEmbedder` implemented and unit-tested
- Chunker implemented and unit-tested against sample note content
- All new DB tables created by `IndexStore.__init__` without error
- DuckDB VSS extension loads successfully
- `sentence-transformers` added to `pyproject.toml`

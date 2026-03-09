-- Core tables

CREATE TABLE IF NOT EXISTS notes (
    note_relpath    TEXT PRIMARY KEY,
    title           TEXT,
    is_daily_note   BOOLEAN,
    mtime_ns        BIGINT,
    size_bytes      BIGINT,
    content_sha256  TEXT,
    word_count      INTEGER
);

CREATE TABLE IF NOT EXISTS frontmatter (
    note_relpath    TEXT,
    key             TEXT,
    value           TEXT    -- JSON-encoded to handle lists and scalars uniformly
);

CREATE TABLE IF NOT EXISTS headings (
    note_relpath    TEXT,
    line_no         INTEGER,
    level           INTEGER,  -- 1-6
    heading         TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
    note_relpath    TEXT,
    line_no         INTEGER,
    status          TEXT,     -- 'open' | 'done' | 'in_progress' | 'cancelled'
    text            TEXT,
    due_date        DATE      -- NULL if not specified; parsed from 📅 YYYY-MM-DD
);

CREATE TABLE IF NOT EXISTS links (
    note_relpath    TEXT,
    line_no         INTEGER,
    target          TEXT,
    kind            TEXT      -- 'wikilink' | 'markdown'
);

CREATE TABLE IF NOT EXISTS tags (
    note_relpath    TEXT,
    tag             TEXT,
    source          TEXT      -- 'inline' | 'frontmatter'
);

-- Index metadata

CREATE TABLE IF NOT EXISTS meta (
    key     TEXT PRIMARY KEY,
    value   TEXT
);

-- Legacy placeholder tables (kept for compatibility)

CREATE TABLE IF NOT EXISTS note_summaries (
    note_relpath    TEXT PRIMARY KEY,
    summary         TEXT,
    summarized_at   TIMESTAMP,
    model_version   TEXT
);

CREATE TABLE IF NOT EXISTS topic_clusters (
    cluster_id      TEXT,
    note_relpath    TEXT,
    score           DOUBLE
);

-- Semantic index tables (Milestone 6)

CREATE TABLE IF NOT EXISTS chunks (
    id              TEXT PRIMARY KEY,   -- "{note_relpath}:{chunk_index}"
    note_relpath    TEXT NOT NULL,
    chunk_index     INTEGER NOT NULL,
    section_header  TEXT,               -- NULL if not under a ## heading
    text            TEXT NOT NULL,
    token_count     INTEGER,
    embedded_sha256 TEXT,               -- content_sha256 at time of embedding (staleness check)
    embedded_at     TIMESTAMP           -- NULL until embedding phase runs
);

CREATE TABLE IF NOT EXISTS chunk_embeddings (
    chunk_id        TEXT PRIMARY KEY,
    embedding       FLOAT[384]          -- all-MiniLM-L6-v2; update dimension if model changes
);

CREATE TABLE IF NOT EXISTS note_intelligence (
    note_relpath    TEXT PRIMARY KEY,
    summary         TEXT,               -- 2-4 sentence LLM-generated summary
    extracted_at    TIMESTAMP,
    model_version   TEXT                -- e.g. "claude-sonnet-4-6"
);

CREATE TABLE IF NOT EXISTS concepts (
    id              INTEGER PRIMARY KEY,
    name            TEXT UNIQUE         -- canonical lowercase form
);

CREATE TABLE IF NOT EXISTS chunk_concepts (
    chunk_id        TEXT NOT NULL,
    concept_id      INTEGER NOT NULL,
    salience        REAL,               -- 0.0–1.0; how central is this concept to the chunk
    PRIMARY KEY (chunk_id, concept_id)
);

CREATE TABLE IF NOT EXISTS entities (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    type            TEXT NOT NULL       -- person | project | tool | book | place | other
);

CREATE TABLE IF NOT EXISTS chunk_entities (
    chunk_id        TEXT NOT NULL,
    entity_id       INTEGER NOT NULL,
    context_snippet TEXT,               -- short surrounding text for display
    PRIMARY KEY (chunk_id, entity_id)
);

CREATE TABLE IF NOT EXISTS implicit_items (
    id              INTEGER PRIMARY KEY,
    chunk_id        TEXT NOT NULL,
    note_relpath    TEXT NOT NULL,      -- denormalized for efficient queries
    type            TEXT NOT NULL,      -- idea | question | intention | task
    text            TEXT NOT NULL,
    extracted_at    TIMESTAMP
);

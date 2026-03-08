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

-- Future tables (not used in initial implementation)

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

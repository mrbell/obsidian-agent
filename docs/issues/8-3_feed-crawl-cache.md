# 8-3 — Feed crawl cache with embedding-based pre-filter

**Status**: `open`
**Parent**: [8 Research Enhancements](8_research-enhancements.md)
**Depends on**: 8-1, 8-2, 6-1 (LocalEmbedder)

## Description

High-volume feeds (e.g. arXiv CS.LG, ~100 papers/day) are impractical to process in a
single weekly report job. This issue adds a daily Class A crawl job that fetches
configured feeds, stores items in DuckDB, and scores each abstract against configured
topics using the existing LocalEmbedder. The weekly `research_digest` job then queries
the top-K pre-scored items rather than fetching and filtering at report time.

## Data model

```sql
CREATE TABLE IF NOT EXISTS feed_items (
    id              TEXT PRIMARY KEY,       -- feed URL + item GUID/link (hashed)
    feed_url        TEXT NOT NULL,
    title           TEXT NOT NULL,
    link            TEXT NOT NULL,
    published       DATE,
    authors         TEXT,                   -- comma-separated
    summary         TEXT,                   -- abstract / RSS description
    fetched_at      TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS feed_item_scores (
    item_id         TEXT NOT NULL,
    topic_name      TEXT NOT NULL,          -- matches ResearchTopic.name
    score           REAL NOT NULL,          -- cosine similarity vs topic embedding
    scored_at       TIMESTAMP NOT NULL,
    PRIMARY KEY (item_id, topic_name)
);
```

Items older than `retention_days` (default: 30) are pruned on each crawl run.

## New job: `crawl_feeds` (Class A)

Schedule: daily (e.g. 06:00, before `index` and any report jobs).

For each topic in `research_digest.topics` that has `feeds` configured:
1. Fetch each feed URL via the `fetch_feed` MCP tool (reuses 8-2 parsing logic,
   called directly rather than via MCP in this context — extract the parsing into
   a shared helper in `index/feed_parser.py`).
2. Deduplicate against existing `feed_items` rows by `id`.
3. Insert new items.
4. For each new item, embed the abstract using `LocalEmbedder` and compute cosine
   similarity against the topic's embedded representation (name + description).
5. Store scores in `feed_item_scores`.
6. Prune items older than `retention_days`.

The topic embedding is computed once per topic per run (not per item). If the topic
name + description hasn't changed since the last scored item, the cached embedding
can be reused.

## Changes to `research_digest` job

When a topic has `feeds` configured, query `feed_items` + `feed_item_scores` instead
of calling `fetch_feed` at report time:

```python
def _get_cached_items(store, topic: ResearchTopic, since: date, top_k: int = 50):
    # query feed_item_scores JOIN feed_items
    # WHERE topic_name = topic.name AND published >= since
    # ORDER BY score DESC LIMIT top_k
```

Pass the resulting abstracts + metadata into the prompt as structured context. Claude
synthesises from this pre-filtered set rather than doing open-ended web search for
feed-backed topics.

For topics without `feeds`, behaviour is unchanged (web search as before).

## Config

```yaml
jobs:
  crawl_feeds:
    enabled: true
    schedule: "0 6 * * *"
    retention_days: 30
    top_k: 50          # items passed to the report job per topic
```

## Design notes

- Embedding quality is the primary filter quality lever. Tuning `description` on a
  topic improves embedding match without code changes.
- LLM judgment happens only at synthesis time (weekly report), over a pre-scored set
  of ≤50 abstracts. Context size is predictable.
- If embedding pre-filter misses relevant papers, the fallback is to increase `top_k`
  or improve the topic `description`. A future enhancement could add LLM scoring at
  crawl time if embedding quality proves insufficient.
- `feed_parser.py` is extracted as shared logic so both `crawl_feeds` and the
  `fetch_feed` MCP tool use the same parsing code.

## Tests

- Crawl job inserts new items and skips duplicates
- Scores are computed and stored for new items
- Items older than `retention_days` are pruned
- `research_digest` uses cached items when `feeds` is configured for a topic
- `research_digest` falls back to web search when no `feeds` configured
- `_get_cached_items` returns top-K by score, filtered by date

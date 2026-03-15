# 9-1 — Readwise ingestion job

**Status**: `completed`
**Parent**: 9

## Description

Class A job that fetches articles and highlights from the Readwise API and emits one
`VaultArtifact` per article. The promoter writes these into a permanent `Readwise/`
folder in the vault (not BotInbox). Designed to run on a daily schedule.

## Design decisions

**One note per article.** Each article gets its own file, named by a slug derived from
the article title. Notes are permanent — the user may annotate and move them freely.

**Cursor-based incremental sync.** The Readwise API supports `updated_after`. The job
stores the timestamp of the last successful sync in state and only fetches articles
updated since then.

**Promote once, track by ID.** Once an article has been promoted, its Readwise article
ID is recorded in state. It is never re-promoted, even if the user moves the file out
of `Readwise/`. New highlights added to an already-promoted article are not
automatically synced (acceptable 80% solution; a force-refresh flag can be added later).

**No LLM required.** This is a pure data-formatting job; no AI summary on initial
implementation.

**Per-job promoter destination.** The promoter is extended to support a configurable
destination path per job, defaulting to the existing `BotInbox/<job>/` behaviour. The
Readwise job sets its destination to `Readwise/`.

## Note format

```markdown
---
readwise_id: <int>
source_url: <original article URL>
readwise_url: https://readwise.io/bookreview/<id>
author: <str or null>
date_saved: <YYYY-MM-DD>
tags: [readwise]
---

# <Article Title>

**Source**: [<domain>](<source_url>) · [Readwise](<readwise_url>)
**Author**: <author>
**Saved**: <date_saved>

---

## Highlights

> <highlight text>

<user note on highlight, if any>

> <next highlight>

<user note, if any>
```

## Implementation

**`obsidian_agent/readwise/`** — new subpackage:
- `client.py` — thin wrapper around the Readwise v2 REST API (`/api/v2/highlights/`,
  `/api/v2/books/`). Auth via `READWISE_API_TOKEN` env var.
- `formatter.py` — converts a Readwise article + highlights into a markdown string and
  a filename slug.

**`obsidian_agent/jobs/readwise_ingestion.py`** — Class A job:
- Loads state from `state_dir/readwise_ingestion.json`
  (`last_sync: ISO timestamp`, `promoted_ids: list[int]`)
- Calls Readwise API for articles updated since `last_sync`
- Skips any article whose ID is already in `promoted_ids`
- For each new article: emits a `VaultArtifact` with `destination="Readwise/"`
- On success: updates `last_sync` and appends new IDs to `promoted_ids`

**`obsidian_agent/promote/promoter.py`** — extend to support per-artifact destination:
- `VaultArtifact` gains an optional `destination: str | None` field (default `None`)
- When set, promoter writes to `<vault_root>/<destination>/<filename>` instead of
  `<vault_root>/BotInbox/<job>/<filename>`

**`config.py`** — add `ReadwiseConfig`:
```python
@dataclass(frozen=True)
class ReadwiseConfig:
    enabled: bool = False
    # API token comes from READWISE_API_TOKEN env var only
```

**`config.yaml.example`** — add readwise section.

## API notes

- Auth: `Authorization: Token <READWISE_API_TOKEN>`
- List highlights: `GET https://readwise.io/api/v2/highlights/?updated_after=<iso>`
- List books (articles): `GET https://readwise.io/api/v2/books/?updated_after=<iso>`
  - Filter by `category=articles,tweets` to skip books/podcasts/etc.
- Pagination: follow `next` field in response
- Rate limits: be conservative, add a small delay between pages
- [API Docs](https://readwise.io/api_deets)

## State file

```json
{
  "last_sync": "2026-03-11T00:00:00Z",
  "promoted_ids": [12345, 67890]
}
```

On first run, `last_sync` is absent and all articles with at least one highlight are
fetched.

## Tests

- Formatter produces correct frontmatter and highlight blocks
- Articles already in `promoted_ids` are skipped
- Articles with no highlights are skipped
- `last_sync` and `promoted_ids` are updated correctly after a successful run
- Promoter writes to `destination` path when set on `VaultArtifact`
- Promoter falls back to `BotInbox/<job>/` when `destination` is None

## Out of scope

- Books, podcasts, or other Readwise content types (articles and tweets only)
- Auto-updating notes when new highlights are added to an existing article
- LLM-generated summary section
- Deduplication by vault search (overkill given ID-based state tracking)

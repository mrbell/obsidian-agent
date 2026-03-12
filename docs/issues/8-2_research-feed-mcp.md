# 8-2 — Feed MCP tool for research jobs

**Status**: `completed`
**Parent**: [8 Research Enhancements](8_research-enhancements.md)
**Depends on**: 8-1

## Description

Add a `feeds` field to `ResearchTopic` (alongside the `sources` domain-hint field from
8-1) and a `fetch_feed(url)` MCP tool that returns structured RSS/Atom items. This lets
Claude use a dedicated tool for configured feeds rather than falling back to web search,
giving deterministic, structured access to trusted sources.

## Config format

```yaml
jobs:
  research_digest:
    topics:
      - name: "machine learning"
        feeds:
          - "https://arxiv.org/rss/cs.LG"
          - "https://arxiv.org/rss/cs.AI"
        sources:
          - "nature.com"        # web search hint for sources without feeds
```

## Implementation

### `config.py`

Add `feeds: list[str]` to `ResearchTopic` (default empty list):

```python
@dataclass(frozen=True)
class ResearchTopic:
    name: str
    description: str | None = None
    sources: list[str] = field(default_factory=list)
    feeds: list[str] = field(default_factory=list)   # RSS/Atom feed URLs
```

Update `_parse_research_digest` to parse `feeds` from structured topic dicts.

### MCP server (`mcp/tools.py`)

Add a `fetch_feed(url)` tool:

- Fetches the URL with `urllib.request` (stdlib only — no new deps)
- Parses RSS 2.0 and Atom 1.0 with `xml.etree.ElementTree`
- Returns a list of items: `title`, `link`, `published`, `summary`
- Caps at 50 items to avoid overwhelming context
- Raises a clear error if the URL is not reachable or not a recognised feed format

This tool belongs in the existing MCP server (the vault server already makes HTTP calls
via stdlib for note content; feed fetching is similarly read-only data retrieval).

### `research_digest.py`

Update `_build_prompt` to distinguish feeds from web-search sources:

```
Topic: {name}
{f"Focus: {description}" if description}

{if feeds:}
Fetch the following feeds using the fetch_feed tool and include relevant items from them:
{chr(10).join(f"  - {url}" for url in feeds)}
{endif}

{if sources:}
For additional coverage, prioritise these sources in web search: {', '.join(sources)}
{endif}
```

### `config.yaml.example`

Show a topic with both `feeds` and `sources`.

## Design notes

- `feeds` and `sources` are complementary: feeds give structured access to known URLs;
  `sources` bias web search toward trusted domains when no feed is configured.
- The MCP tool is read-only and stateless — no caching, no persistence. Feed freshness
  is Claude's responsibility to check via the `published` field.
- No new dependencies: `urllib.request` + `xml.etree.ElementTree` are stdlib.
- The tool lives in the vault MCP server for simplicity. If a dedicated research MCP
  server is warranted later (e.g. for more tools), it can be split out then.

## Tests

- `fetch_feed` tool returns expected items from a minimal RSS 2.0 fixture
- `fetch_feed` tool returns expected items from a minimal Atom 1.0 fixture
- Unreachable URL raises a descriptive error
- Malformed XML raises a descriptive error
- `feeds` field parses correctly from config dict
- `feeds` appears in prompt when set; absent from prompt when empty
- Mixed topic (feeds + sources + description) produces correct prompt

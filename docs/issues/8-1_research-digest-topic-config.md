# 8-1 — Structured topic config for research_digest

**Status**: `completed`
**Parent**: 8

## Description

Topics in `research_digest` are currently plain strings passed verbatim into the prompt.
Add support for structured topic objects with optional `description` and `sources` fields,
while keeping plain strings working as-is.

## Desired config format

```yaml
jobs:
  research_digest:
    topics:
      - "agentic coding"                          # plain string still works
      - name: "Rust"                              # structured, minimal
        description: "focus on async patterns and the tokio ecosystem"
        sources:
          - "arxiv.org"
          - "news.ycombinator.com"
          - "without.boats"
```

## Implementation

**`config.py`**: Add `ResearchTopic` dataclass:

```python
@dataclass(frozen=True)
class ResearchTopic:
    name: str
    description: str | None = None
    sources: list[str] = field(default_factory=list)
```

Update `ResearchDigestConfig.topics` from `list[str]` to `list[ResearchTopic]`.

Update `_parse_research_digest` to handle both plain strings and dicts:
- Plain string → `ResearchTopic(name=string)`
- Dict → `ResearchTopic(name=d["name"], description=d.get("description"), sources=d.get("sources", []))`

**`research_digest.py`**: Update `_build_prompt` to inject description and sources when
present:

```
Topic: {name}
{f"Focus: {description}" if description}
{f"Prioritise these sources: {', '.join(sources)}" if sources}
```

Update `_topic_slug` to use `topic.name` instead of the raw string.

**`config.yaml.example`**: Show both plain string and structured examples.

## Backward compatibility

Plain string topics must continue to work without any config changes.

## Tests

- Plain string topic produces same behaviour as before
- Structured topic with only `name` behaves like plain string
- `description` appears in prompt when set
- `sources` appear in prompt when set
- Mixed list (some plain strings, some structured) works correctly
- `_topic_slug` uses `topic.name`

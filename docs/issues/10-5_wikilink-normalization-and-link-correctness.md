# 10-5 — Wikilink Normalization and Link Correctness

**Status**: `open`
**Parent**: 10
**Children**: —
**Depends on**: 1-3, 1-5, 4-1

## Description

Incoming-link queries currently miss path-qualified wikilinks such as `[[Folder/Note]]`
because the system stores raw targets and matches incoming links only against the bare note
stem. This issue normalizes wikilink targets so the link graph is structurally correct for
both bare and path-qualified note references.

## Implementation Notes

### Parsing / indexing

- Extend vault parsing or index build logic so wikilinks have a normalized target form
- Normalization should remove:
  - aliases (`[[Note|Alias]]`)
  - anchors / blocks (`[[Note#Heading]]`, `[[Note#^block]]`)
  - optional `.md` suffix
- Preserve enough raw information for debugging if needed

### Query behavior

- Update incoming-link resolution in `obsidian_agent/index/queries.py`
- For a note like `Folder/Note.md`, incoming-link lookup should recognize both:
  - `Note`
  - `Folder/Note`

### Migration / rebuild

Decide whether this is:

- a lightweight query-only fix using canonical forms generated at lookup time, or
- a schema/index improvement that requires rebuilding or patching stored link targets

Favor the minimal correct change first, but leave the model in a state where future link
queries are simpler and less error-prone.

## Testing & Validation

Red/green TDD:

- Add failing parser/query tests for:
  - `[[Note]]`
  - `[[Folder/Note]]`
  - aliases and heading anchors
- Verify outgoing links remain correct
- Verify incoming links resolve correctly through MCP tool coverage as well

## Definition of Done

- Incoming-link queries are correct for bare and path-qualified wikilinks
- Link normalization behavior is covered by tests

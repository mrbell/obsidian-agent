# 1-3 — Vault Reader and Parser

**Status**: `completed`
**Parent**: 1
**Children**: —
**Depends on**: —

## Description

Implement `obsidian_agent/vault/reader.py` and `obsidian_agent/vault/parser.py`.

The reader walks the vault directory and yields file paths and raw content.
The parser extracts structured features from note content.

## Implementation Notes

### reader.py

- `iter_markdown_files(vault_path: Path) -> Iterator[Path]`
  - Yields all `.md` files recursively
  - Skips hidden directories (`.obsidian`, `.trash`, etc.)
- `read_note(path: Path) -> str`
  - Reads and returns file content; raises on unreadable files

### parser.py

Parse a note's text content into a `ParsedNote` dataclass containing:

- `title: str` — first H1 heading, or filename stem if none
- `frontmatter: dict[str, Any]` — parsed YAML block (empty dict if none)
- `is_daily_note: bool` — filename matches `YYYY-MM-DD.md`
- `headings: list[Heading]` — `(line_no, level, text)`
- `tasks: list[Task]` — `(line_no, status, text, due_date | None)`
- `wikilinks: list[Link]` — `(line_no, target, kind='wikilink')`
- `md_links: list[Link]` — `(line_no, target, kind='markdown')`
- `tags: list[str]` — inline `#tag` and frontmatter `tags:` list
- `word_count: int`

### Task parsing

Status mapping from Obsidian checkbox syntax:
- `- [ ]` → `open`
- `- [x]` or `- [X]` → `done`
- `- [/]` → `in_progress`
- `- [-]` → `cancelled`

Due date: parse `📅` or `📆` emoji followed by a date anywhere in the task text.
Accepted formats: `YYYY-MM-DD`, `YYYY/MM/DD`, `MM/DD/YYYY`, `MM-DD-YYYY`, `MM/DD`, `MM-DD`
(last two imply the current year). Return as `datetime.date`; `None` if absent.

### Implementation approach

Use regex throughout. No full Markdown AST parser needed for v1.
Frontmatter: detect `---` block at file start, parse with `yaml.safe_load`.

## Testing & Validation

Unit tests covering:
- Note with frontmatter, headings, tasks, wikilinks, inline tags
- Daily note detection
- Task status variants (`[ ]`, `[x]`, `[/]`, `[-]`)
- Due date extraction from `📅`/`📆` + flexible date format
- Task with no due date
- Note with no frontmatter
- Empty note

## Definition of Done

`parse_note(content: str, filename: str) -> ParsedNote` handles all cases above with
passing unit tests.

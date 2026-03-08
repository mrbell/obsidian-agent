from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Heading:
    line_no: int
    level: int   # 1–6
    text: str


@dataclass(frozen=True)
class Task:
    line_no: int
    status: str  # 'open' | 'done' | 'in_progress' | 'cancelled'
    text: str
    due_date: date | None


@dataclass(frozen=True)
class Link:
    line_no: int
    target: str
    kind: str    # 'wikilink' | 'markdown'


@dataclass(frozen=True)
class Tag:
    name: str
    source: str  # 'inline' | 'frontmatter'


@dataclass
class ParsedNote:
    title: str
    frontmatter: dict[str, Any]
    is_daily_note: bool
    headings: list[Heading]
    tasks: list[Task]
    links: list[Link]
    tags: list[Tag]
    word_count: int


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

_DAILY_NOTE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)")
_TASK_RE = re.compile(r"^\s*[-*+] \[(.)\] (.*)")
_DUE_DATE_RE = re.compile(r"📅\s*(\d{4}-\d{2}-\d{2})")
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
# Inline tags: #word, #word/subword — not preceded by # or word char
_INLINE_TAG_RE = re.compile(r"(?<![#\w])#([a-zA-Z][a-zA-Z0-9_/\-]*)")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TASK_STATUS_MAP: dict[str, str] = {
    " ": "open",
    "x": "done",
    "X": "done",
    "/": "in_progress",
    "-": "cancelled",
}


def _parse_task_status(checkbox: str) -> str:
    return _TASK_STATUS_MAP.get(checkbox, "open")


def _parse_due_date(text: str) -> date | None:
    m = _DUE_DATE_RE.search(text)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_frontmatter(lines: list[str]) -> tuple[dict[str, Any], int]:
    """Parse YAML frontmatter from the start of a note.

    Returns (frontmatter_dict, body_start_index) where body_start_index is
    the index of the first non-frontmatter line.
    """
    if not lines or lines[0] != "---":
        return {}, 0
    for i in range(1, len(lines)):
        if lines[i] == "---":
            fm_text = "\n".join(lines[1:i])
            parsed = yaml.safe_load(fm_text)
            fm = parsed if isinstance(parsed, dict) else {}
            return fm, i + 1
    # Opening --- found but no closing --- — treat as no frontmatter
    return {}, 0


def _frontmatter_tags(frontmatter: dict[str, Any]) -> list[Tag]:
    raw = frontmatter.get("tags", [])
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    return [Tag(name=str(t), source="frontmatter") for t in raw if t]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_note(content: str, filename: str) -> ParsedNote:
    """Parse raw note content and filename into a ParsedNote.

    Args:
        content: Full text of the markdown file.
        filename: Bare filename (e.g. "2026-03-07.md" or "My Note.md").
    """
    lines = content.splitlines()
    frontmatter, body_start = _parse_frontmatter(lines)

    is_daily_note = bool(_DAILY_NOTE_RE.match(filename))

    headings: list[Heading] = []
    tasks: list[Task] = []
    links: list[Link] = []
    title: str | None = None
    seen_inline_tags: set[str] = set()
    inline_tags: list[Tag] = []

    for idx, line in enumerate(lines[body_start:], start=body_start + 1):
        # Headings
        hm = _HEADING_RE.match(line)
        if hm:
            level = len(hm.group(1))
            text = hm.group(2).strip()
            headings.append(Heading(line_no=idx, level=level, text=text))
            if level == 1 and title is None:
                title = text

        # Tasks
        tm = _TASK_RE.match(line)
        if tm:
            status = _parse_task_status(tm.group(1))
            task_text = tm.group(2)
            due_date = _parse_due_date(task_text)
            tasks.append(Task(line_no=idx, status=status, text=task_text, due_date=due_date))

        # Wikilinks
        for wm in _WIKILINK_RE.finditer(line):
            links.append(Link(line_no=idx, target=wm.group(1).strip(), kind="wikilink"))

        # Markdown links
        for mm in _MD_LINK_RE.finditer(line):
            links.append(Link(line_no=idx, target=mm.group(1).strip(), kind="markdown"))

        # Inline tags (deduplicated)
        for tagm in _INLINE_TAG_RE.finditer(line):
            name = tagm.group(1)
            if name not in seen_inline_tags:
                seen_inline_tags.add(name)
                inline_tags.append(Tag(name=name, source="inline"))

    if title is None:
        title = Path(filename).stem

    tags = _frontmatter_tags(frontmatter) + inline_tags

    body_text = "\n".join(lines[body_start:])
    word_count = len(body_text.split())

    return ParsedNote(
        title=title,
        frontmatter=frontmatter,
        is_daily_note=is_daily_note,
        headings=headings,
        tasks=tasks,
        links=links,
        tags=tags,
        word_count=word_count,
    )

from __future__ import annotations

import re
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_TOKENS = 50   # chunks below this are discarded (isolated headers, stubs)
MAX_TOKENS = 400  # chunks above this are split at sentence boundaries

# Matches ## and deeper headings (not H1 — those are titles, not sections)
_HEADING_RE = re.compile(r"^(#{2,6})\s+(.*)")

# Split on sentence-ending punctuation followed by whitespace
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+")

# Frontmatter delimiter
_FM_DELIM = "---"


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Chunk:
    note_relpath: str
    chunk_index: int           # 0-based position within the note
    section_header: str | None # nearest ## heading above this chunk, if any
    text: str
    token_count: int           # approximate (word_count × 1.3)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _estimate_tokens(text: str) -> int:
    return max(1, int(len(text.split()) * 1.3))


def _strip_frontmatter(content: str) -> str:
    """Return content with the YAML frontmatter block removed."""
    lines = content.splitlines()
    if not lines or lines[0].strip() != _FM_DELIM:
        return content
    for i in range(1, len(lines)):
        if lines[i].strip() == _FM_DELIM:
            return "\n".join(lines[i + 1 :])
    return content  # no closing --- found


def _collect_paragraphs(body: str) -> list[tuple[str, str | None]]:
    """Walk body line-by-line and collect (paragraph_text, section_header) pairs.

    Heading lines update the running section_header but are not included in
    paragraph text. Content lines accumulate until a blank line flushes them.
    """
    current_header: str | None = None
    current_lines: list[str] = []
    paragraphs: list[tuple[str, str | None]] = []

    def _flush() -> None:
        nonlocal current_lines
        text = "\n".join(current_lines).strip()
        current_lines = []
        if text:
            paragraphs.append((text, current_header))

    for line in body.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            _flush()
            current_header = m.group(2).strip()
        elif line.strip() == "":
            _flush()
        else:
            current_lines.append(line)

    _flush()
    return paragraphs


def _split_at_sentences(text: str) -> list[str]:
    """Split text into ≤ MAX_TOKENS pieces at sentence boundaries."""
    sentences = _SENTENCE_END_RE.split(text)
    parts: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = (current + " " + sentence).strip() if current else sentence
        if _estimate_tokens(candidate) > MAX_TOKENS and current:
            parts.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        parts.append(current.strip())
    return [p for p in parts if p.strip()]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def chunk_note(note_relpath: str, content: str) -> list[Chunk]:
    """Split a note's content into paragraph-level chunks.

    Rules:
    - Paragraph boundaries (blank lines) are the primary split points.
    - Each chunk carries the most recent ##+ heading as section_header.
    - Short paragraphs (< MIN_TOKENS) are merged into their neighbours.
    - Paragraphs exceeding MAX_TOKENS are split at sentence boundaries.
    - Final chunks below MIN_TOKENS are dropped.

    Returns an empty list for blank or frontmatter-only notes.
    """
    body = _strip_frontmatter(content).strip()
    if not body:
        return []

    paragraphs = _collect_paragraphs(body)
    if not paragraphs:
        return []

    result: list[Chunk] = []
    chunk_index = 0
    acc_text = ""
    acc_header: str | None = None

    def _emit(text: str, header: str | None) -> None:
        nonlocal chunk_index
        text = text.strip()
        if not text:
            return
        token_count = _estimate_tokens(text)
        if token_count < MIN_TOKENS:
            return
        result.append(
            Chunk(
                note_relpath=note_relpath,
                chunk_index=chunk_index,
                section_header=header,
                text=text,
                token_count=token_count,
            )
        )
        chunk_index += 1

    for para_text, para_header in paragraphs:
        para_tokens = _estimate_tokens(para_text)

        if para_tokens > MAX_TOKENS:
            # Flush current accumulation first
            if acc_text:
                _emit(acc_text, acc_header)
                acc_text = ""
                acc_header = None
            # Split this oversized paragraph at sentence boundaries
            for part in _split_at_sentences(para_text):
                _emit(part, para_header)
        else:
            if acc_text:
                combined = acc_text + "\n\n" + para_text
                if _estimate_tokens(combined) > MAX_TOKENS or para_header != acc_header:
                    # Flush before starting a new accumulation block.
                    # Section boundary (header change) always triggers a flush so
                    # each chunk stays within a single section.
                    _emit(acc_text, acc_header)
                    acc_text = para_text
                    acc_header = para_header
                else:
                    acc_text = combined
                    # acc_header stays as the first paragraph's header
            else:
                acc_text = para_text
                acc_header = para_header

    if acc_text:
        _emit(acc_text, acc_header)

    return result

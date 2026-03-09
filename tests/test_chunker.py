"""Tests for obsidian_agent.index.chunker."""
from __future__ import annotations

import pytest

from obsidian_agent.index.chunker import MIN_TOKENS, Chunk, chunk_note


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_content(paragraphs: list[str], frontmatter: str = "") -> str:
    body = "\n\n".join(paragraphs)
    if frontmatter:
        return f"---\n{frontmatter}\n---\n\n{body}"
    return body


def _words(n: int, word: str = "word") -> str:
    """Return n space-separated copies of word."""
    return " ".join([word] * n)


# ---------------------------------------------------------------------------
# Frontmatter stripping
# ---------------------------------------------------------------------------

class TestFrontmatterStripping:
    def test_frontmatter_excluded_from_chunks(self) -> None:
        content = "---\ntitle: Test\ntags: [a, b]\n---\n\n" + _words(60)
        chunks = chunk_note("test.md", content)
        assert chunks
        assert "title:" not in chunks[0].text
        assert "tags:" not in chunks[0].text

    def test_no_frontmatter_works(self) -> None:
        content = _words(60)
        chunks = chunk_note("test.md", content)
        assert len(chunks) == 1

    def test_unclosed_frontmatter_treated_as_content(self) -> None:
        # No closing --- so no frontmatter is stripped
        content = "---\ntitle: Test\n\n" + _words(60)
        chunks = chunk_note("test.md", content)
        assert chunks  # something was parsed


# ---------------------------------------------------------------------------
# Basic paragraph splitting
# ---------------------------------------------------------------------------

class TestParagraphSplitting:
    def test_single_paragraph_becomes_one_chunk(self) -> None:
        content = _words(60)
        chunks = chunk_note("test.md", content)
        assert len(chunks) == 1
        assert isinstance(chunks[0], Chunk)

    def test_two_paragraphs_accumulate_when_small(self) -> None:
        # Two short-ish paragraphs should be merged into one chunk
        p1 = _words(30)
        p2 = _words(30)
        content = p1 + "\n\n" + p2
        chunks = chunk_note("test.md", content)
        # 60 words * 1.3 ≈ 78 tokens; fits in one chunk
        assert len(chunks) == 1
        assert p1.split()[0] in chunks[0].text
        assert p2.split()[0] in chunks[0].text

    def test_empty_note_returns_empty_list(self) -> None:
        assert chunk_note("test.md", "") == []

    def test_frontmatter_only_returns_empty_list(self) -> None:
        content = "---\ntitle: Empty\n---\n"
        assert chunk_note("test.md", content) == []

    def test_chunk_index_is_sequential(self) -> None:
        # Three paragraphs large enough to produce 3 chunks individually
        paras = [_words(60, w) for w in ("alpha", "beta", "gamma")]
        # Make them not accumulate by making each large enough
        # 60 words * 1.3 ≈ 78 tokens per para; combined 234 < 400 → they merge
        # Use larger paragraphs to force splits
        paras = [_words(120, w) for w in ("alpha", "beta", "gamma")]
        content = "\n\n".join(paras)
        chunks = chunk_note("test.md", content)
        indices = [c.chunk_index for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_note_relpath_set_correctly(self) -> None:
        content = _words(60)
        chunks = chunk_note("folder/note.md", content)
        assert all(c.note_relpath == "folder/note.md" for c in chunks)


# ---------------------------------------------------------------------------
# Section header tracking
# ---------------------------------------------------------------------------

class TestSectionHeaders:
    def test_chunk_under_heading_has_header(self) -> None:
        content = "## My Section\n\n" + _words(60)
        chunks = chunk_note("test.md", content)
        assert chunks
        assert chunks[0].section_header == "My Section"

    def test_chunk_before_heading_has_no_header(self) -> None:
        content = _words(60) + "\n\n## Section\n\n" + _words(60)
        chunks = chunk_note("test.md", content)
        assert chunks[0].section_header is None

    def test_header_updates_per_section(self) -> None:
        # Use large paragraphs to prevent merging
        p1 = _words(200, "alpha")
        p2 = _words(200, "beta")
        content = f"## First\n\n{p1}\n\n## Second\n\n{p2}"
        chunks = chunk_note("test.md", content)
        assert len(chunks) >= 2
        assert chunks[0].section_header == "First"
        assert chunks[-1].section_header == "Second"

    def test_h1_heading_does_not_become_section_header(self) -> None:
        # H1 is the note title; only ##+ headings become section headers
        content = "# Title\n\n" + _words(60) + "\n\n## Section\n\n" + _words(60)
        chunks = chunk_note("test.md", content)
        first_chunk_headers = {c.section_header for c in chunks if c.section_header is None}
        assert any(c.section_header is None for c in chunks)  # pre-section content
        assert any(c.section_header == "Section" for c in chunks)

    def test_deeper_headings_tracked(self) -> None:
        content = "### Deep Section\n\n" + _words(60)
        chunks = chunk_note("test.md", content)
        assert chunks[0].section_header == "Deep Section"


# ---------------------------------------------------------------------------
# Minimum length filtering
# ---------------------------------------------------------------------------

class TestMinimumLength:
    def test_very_short_paragraph_discarded(self) -> None:
        # A single short line is below MIN_TOKENS
        content = "Just a few words."
        chunks = chunk_note("test.md", content)
        assert chunks == []

    def test_paragraph_just_above_min_kept(self) -> None:
        # ~40 words * 1.3 ≈ 52 tokens > MIN_TOKENS(50)
        content = _words(40)
        chunks = chunk_note("test.md", content)
        assert len(chunks) == 1

    def test_heading_only_note_returns_empty(self) -> None:
        content = "## Just a Heading"
        assert chunk_note("test.md", content) == []


# ---------------------------------------------------------------------------
# Long chunk splitting
# ---------------------------------------------------------------------------

class TestLongChunkSplitting:
    def test_long_paragraph_produces_multiple_chunks(self) -> None:
        # ~400+ words ensures we exceed MAX_TOKENS
        # Use sentence-ending punctuation so the splitter has boundaries
        sentences = ["This is sentence number {:03d} in a very long paragraph.".format(i)
                     for i in range(80)]
        content = " ".join(sentences)
        chunks = chunk_note("test.md", content)
        assert len(chunks) > 1
        assert all(c.token_count <= 520 for c in chunks)  # some slack for splitting

    def test_split_chunks_have_sequential_indices(self) -> None:
        sentences = ["Sentence {:03d} ends here.".format(i) for i in range(80)]
        content = " ".join(sentences)
        chunks = chunk_note("test.md", content)
        indices = [c.chunk_index for c in chunks]
        assert indices == list(range(len(chunks)))

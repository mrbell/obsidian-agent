from __future__ import annotations

from obsidian_agent.readwise.client import ReadwiseDocument, ReadwiseHighlight
from obsidian_agent.readwise.formatter import build_filename, format_document, slugify_title


def _document() -> ReadwiseDocument:
    return ReadwiseDocument(
        id=123,
        title="An Interesting Article",
        author="Ada Lovelace",
        category="articles",
        source_url="https://example.com/post",
        readwise_url="https://readwise.io/bookreview/123",
        saved_at="2026-03-11T12:00:00Z",
        updated_at="2026-03-11T12:05:00Z",
        highlights=[
            ReadwiseHighlight(
                id=1,
                text="First highlight",
                note="My note",
                location=None,
                location_type=None,
                highlighted_at="2026-03-11T12:00:00Z",
                updated_at="2026-03-11T12:01:00Z",
            ),
            ReadwiseHighlight(
                id=2,
                text="Second highlight",
                note=None,
                location=None,
                location_type=None,
                highlighted_at="2026-03-11T12:02:00Z",
                updated_at="2026-03-11T12:03:00Z",
            ),
        ],
    )


def test_slugify_title_normalizes_title() -> None:
    assert slugify_title("C++ & Rust") == "c-rust"


def test_build_filename_without_collision_suffix() -> None:
    assert build_filename(_document()) == "an-interesting-article.md"


def test_build_filename_with_collision_suffix() -> None:
    assert build_filename(_document(), with_id_suffix=True) == "an-interesting-article-123.md"


def test_format_document_includes_frontmatter_and_highlights() -> None:
    content = format_document(_document())
    assert "readwise_id: 123" in content
    assert "source_url: https://example.com/post" in content
    assert "tags: [readwise]" in content
    assert "# An Interesting Article" in content
    assert "**Source**: [example.com](https://example.com/post) · [Readwise](https://readwise.io/bookreview/123)" in content
    assert "> First highlight" in content
    assert "My note" in content
    assert "> Second highlight" in content

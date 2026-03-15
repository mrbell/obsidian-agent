from __future__ import annotations

from obsidian_agent.readwise.client import ReadwiseClient


def test_parse_document_accepts_user_book_id() -> None:
    client = ReadwiseClient(token="token")

    document = client._parse_document(  # type: ignore[attr-defined]
        {
            "user_book_id": 123,
            "title": "Article",
            "category": "articles",
            "source_url": "https://example.com/post",
            "highlights": [
                {
                    "id": 456,
                    "text": "Highlight",
                    "updated_at": "2026-03-13T13:00:59.951Z",
                }
            ],
        }
    )

    assert document.id == 123
    assert document.highlights[0].id == 456

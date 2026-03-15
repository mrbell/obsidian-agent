from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass


EXPORT_URL = "https://readwise.io/api/v2/export/"
DEFAULT_PAGE_DELAY_SECONDS = 0.2
IN_SCOPE_CATEGORIES = {"articles", "tweets"}


class ReadwiseClientError(Exception):
    """Raised when the Readwise API request fails or returns invalid data."""


@dataclass(frozen=True)
class ReadwiseHighlight:
    id: int
    text: str
    note: str | None
    location: int | None
    location_type: str | None
    highlighted_at: str | None
    updated_at: str | None


@dataclass(frozen=True)
class ReadwiseDocument:
    id: int
    title: str
    author: str | None
    category: str | None
    source_url: str | None
    readwise_url: str | None
    saved_at: str | None
    updated_at: str | None
    highlights: list[ReadwiseHighlight]


class ReadwiseClient:
    def __init__(
        self,
        token: str | None = None,
        *,
        page_delay_seconds: float = DEFAULT_PAGE_DELAY_SECONDS,
    ) -> None:
        self.token = token or os.environ.get("READWISE_API_TOKEN")
        if not self.token:
            raise ReadwiseClientError("READWISE_API_TOKEN is not set")
        self.page_delay_seconds = page_delay_seconds

    def fetch_documents(self, updated_after: str | None = None) -> list[ReadwiseDocument]:
        params: dict[str, str] = {}
        if updated_after:
            params["updatedAfter"] = updated_after

        documents: list[ReadwiseDocument] = []
        next_cursor: str | None = None

        while True:
            page_params = dict(params)
            if next_cursor:
                page_params["pageCursor"] = next_cursor
            payload = self._get_json(EXPORT_URL, page_params)
            results = payload.get("results", [])
            if not isinstance(results, list):
                raise ReadwiseClientError("Readwise export response missing list 'results'")

            documents.extend(
                self._parse_document(item)
                for item in results
                if isinstance(item, dict)
            )

            next_cursor = payload.get("nextPageCursor") or payload.get("next_page_cursor")
            if not next_cursor:
                break
            time.sleep(self.page_delay_seconds)

        return [
            doc
            for doc in documents
            if (doc.category or "").lower() in IN_SCOPE_CATEGORIES
        ]

    def _get_json(self, url: str, params: dict[str, str]) -> dict:
        full_url = url
        if params:
            full_url = f"{url}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(
            full_url,
            headers={
                "Authorization": f"Token {self.token}",
                "User-Agent": "obsidian-agent/readwise",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)
        except urllib.error.URLError as exc:
            raise ReadwiseClientError(f"Readwise request failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ReadwiseClientError(f"Readwise response was not valid JSON: {exc}") from exc

        if not isinstance(payload, dict):
            raise ReadwiseClientError("Readwise response must be a JSON object")
        return payload

    def _parse_document(self, raw: dict) -> ReadwiseDocument:
        raw_id = raw.get("id", raw.get("user_book_id"))
        if not isinstance(raw_id, int):
            raise ReadwiseClientError(f"Readwise document missing integer id: {raw!r}")

        highlights_raw = raw.get("highlights", [])
        highlights = [
            self._parse_highlight(item)
            for item in highlights_raw
            if isinstance(item, dict)
        ]

        category = raw.get("category")
        source_url = _first_str(raw, "source_url", "url", "source")
        readwise_url = _first_str(raw, "readwise_url")
        if not readwise_url:
            readwise_url = f"https://readwise.io/bookreview/{raw_id}"

        return ReadwiseDocument(
            id=raw_id,
            title=_first_str(raw, "title", "readable_title") or f"Untitled {raw_id}",
            author=_first_str(raw, "author"),
            category=category if isinstance(category, str) else None,
            source_url=source_url,
            readwise_url=readwise_url,
            saved_at=_first_str(raw, "saved_at", "created_at"),
            updated_at=_extract_document_updated_at(raw, highlights),
            highlights=highlights,
        )

    def _parse_highlight(self, raw: dict) -> ReadwiseHighlight:
        raw_id = raw.get("id")
        text = raw.get("text")
        if not isinstance(raw_id, int) or not isinstance(text, str):
            raise ReadwiseClientError(f"Readwise highlight missing required fields: {raw!r}")

        note = raw.get("note")
        location = raw.get("location")
        location_type = raw.get("location_type")
        highlighted_at = _first_str(raw, "highlighted_at")
        updated_at = _first_str(raw, "updated", "updated_at", "highlighted_at")
        return ReadwiseHighlight(
            id=raw_id,
            text=text,
            note=note if isinstance(note, str) and note.strip() else None,
            location=location if isinstance(location, int) else None,
            location_type=location_type if isinstance(location_type, str) else None,
            highlighted_at=highlighted_at,
            updated_at=updated_at,
        )


def _first_str(raw: dict, *keys: str) -> str | None:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _extract_document_updated_at(
    raw: dict,
    highlights: list[ReadwiseHighlight],
) -> str | None:
    candidates: list[str] = []
    for key in ("updated", "updated_at", "last_highlight_at", "saved_at", "created_at"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            candidates.append(value.strip())
    for highlight in highlights:
        if highlight.updated_at:
            candidates.append(highlight.updated_at)
    return max(candidates) if candidates else None

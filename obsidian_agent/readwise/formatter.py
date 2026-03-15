from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urlparse

from obsidian_agent.readwise.client import ReadwiseDocument


def slugify_title(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "readwise-item"


def build_filename(document: ReadwiseDocument, *, with_id_suffix: bool = False) -> str:
    slug = slugify_title(document.title)
    if with_id_suffix:
        slug = f"{slug}-{document.id}"
    return f"{slug}.md"


def format_document(document: ReadwiseDocument) -> str:
    source_url = document.source_url or ""
    readwise_url = document.readwise_url or f"https://readwise.io/bookreview/{document.id}"
    domain = _display_domain(source_url)
    date_saved = _display_date(document.saved_at)
    author = document.author or "Unknown"

    lines = [
        "---",
        f"readwise_id: {document.id}",
        f"source_url: {source_url}" if source_url else "source_url: null",
        f"readwise_url: {readwise_url}",
        f"author: {author}" if document.author else "author: null",
        f"date_saved: {date_saved}",
        "tags: [readwise]",
        "---",
        "",
        f"# {document.title}",
        "",
    ]

    source_bits: list[str] = []
    if source_url:
        source_bits.append(f"[{domain}]({source_url})")
    source_bits.append(f"[Readwise]({readwise_url})")
    lines.append(f"**Source**: {' · '.join(source_bits)}")
    lines.append(f"**Author**: {author}")
    lines.append(f"**Saved**: {date_saved}")
    lines.extend(["", "---", "", "## Highlights", ""])

    for index, highlight in enumerate(document.highlights):
        lines.append(f"> {highlight.text.strip()}")
        if highlight.note:
            lines.extend(["", highlight.note.strip()])
        if index != len(document.highlights) - 1:
            lines.append("")
            lines.append("")

    lines.append("")
    return "\n".join(lines)


def _display_domain(url: str) -> str:
    if not url:
        return "Source"
    domain = urlparse(url).netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain or "Source"


def _display_date(value: str | None) -> str:
    if not value:
        return "Unknown"
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return value[:10]


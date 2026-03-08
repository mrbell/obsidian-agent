from __future__ import annotations

from pathlib import Path
from typing import Iterator


def iter_markdown_files(vault_path: Path) -> Iterator[Path]:
    """Yield all .md files under vault_path, skipping hidden directories."""
    for path in vault_path.rglob("*.md"):
        rel = path.relative_to(vault_path)
        if any(part.startswith(".") for part in rel.parts[:-1]):
            continue
        yield path


def read_note(path: Path) -> str:
    """Read and return the text content of a note file."""
    return path.read_text(encoding="utf-8")

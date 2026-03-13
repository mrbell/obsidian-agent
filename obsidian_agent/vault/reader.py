from __future__ import annotations

from pathlib import Path
from typing import Iterator


def iter_markdown_files(
    vault_path: Path,
    exclude_paths: list[str] | None = None,
) -> Iterator[Path]:
    """Yield all .md files under vault_path, skipping hidden directories
    and any top-level folders listed in exclude_paths."""
    excluded = set(exclude_paths) if exclude_paths else set()
    for path in vault_path.rglob("*.md"):
        rel = path.relative_to(vault_path)
        if any(part.startswith(".") for part in rel.parts[:-1]):
            continue
        if rel.parts[0] in excluded:
            continue
        yield path


def read_note(path: Path) -> str:
    """Read and return the text content of a note file."""
    return path.read_text(encoding="utf-8")

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from obsidian_agent.index import queries
from obsidian_agent.index.store import IndexStore


def _vault_path_for(vault_path: Path, note_relpath: str) -> Path:
    return vault_path / note_relpath


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def search_notes(
    vault_path: Path,
    store: IndexStore,
    query: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Case-insensitive substring search across note content."""
    if not query:
        return []

    query_lower = query.lower()
    results: list[dict[str, Any]] = []

    note_relpaths = [
        r[0]
        for r in store.conn.execute("SELECT note_relpath FROM notes ORDER BY note_relpath").fetchall()
    ]

    for relpath in note_relpaths:
        abs_path = vault_path / relpath
        try:
            content = abs_path.read_text(encoding="utf-8")
        except OSError:
            continue

        idx = content.lower().find(query_lower)
        if idx == -1:
            continue

        # Extract a short excerpt around the match
        start = max(0, idx - 80)
        end = min(len(content), idx + len(query) + 80)
        excerpt = content[start:end].strip()
        if start > 0:
            excerpt = "…" + excerpt
        if end < len(content):
            excerpt = excerpt + "…"

        results.append({"path": relpath, "excerpt": excerpt})
        if len(results) >= limit:
            break

    return results


def get_note(vault_path: Path, path: str) -> str:
    """Return full content of a note by relative path."""
    abs_path = vault_path / path
    # Resolve and check it's still inside the vault (safety)
    try:
        resolved = abs_path.resolve()
        vault_resolved = vault_path.resolve()
        if not resolved.is_relative_to(vault_resolved):
            raise ValueError(f"Path escapes vault: {path!r}")
        return resolved.read_text(encoding="utf-8")
    except OSError as exc:
        raise FileNotFoundError(f"Note not found: {path!r}") from exc


def list_notes(
    store: IndexStore,
    folder: str | None = None,
    include_daily: bool = True,
) -> list[dict[str, Any]]:
    """List notes, optionally filtered by folder."""
    return queries.list_notes(store, folder=folder, include_daily=include_daily)


def get_daily_notes(
    vault_path: Path,
    store: IndexStore,
    start_date: str,
    end_date: str,
) -> list[dict[str, Any]]:
    """Return daily notes in [start_date, end_date] with their content."""
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    relpaths = queries.get_daily_notes_in_range(store, start, end)

    results = []
    for relpath in relpaths:
        try:
            content = (vault_path / relpath).read_text(encoding="utf-8")
        except OSError:
            content = ""
        results.append({"path": relpath, "content": content})
    return results


def query_tasks(
    store: IndexStore,
    status: str = "open",
    due_before: str | None = None,
) -> list[dict[str, Any]]:
    """Query tasks filtered by status and optional due date cutoff."""
    due = date.fromisoformat(due_before) if due_before else None
    return queries.query_tasks(store, status=status, due_before=due)


def get_note_links(store: IndexStore, path: str) -> dict[str, list[str]]:
    """Get outgoing and incoming links for a note."""
    return queries.get_note_links(store, path)


def find_notes_by_tag(store: IndexStore, tag: str) -> list[str]:
    """Find all notes with a given tag."""
    return queries.find_notes_by_tag(store, tag)


def get_vault_stats(store: IndexStore) -> dict[str, Any]:
    """Return note count, task count, and last indexed timestamp."""
    return {
        "note_count": queries.get_note_count(store),
        "task_count": queries.get_task_count(store),
        "last_indexed_at": queries.get_last_indexed_at(store),
    }

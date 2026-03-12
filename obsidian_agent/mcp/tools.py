from __future__ import annotations

import json
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from typing import Any

from obsidian_agent.index import queries
from obsidian_agent.index import semantic_queries as sq
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


# ---------------------------------------------------------------------------
# Semantic tools (Milestone 6-5)
# ---------------------------------------------------------------------------

def search_similar(
    store: IndexStore,
    embedder: Any,
    query: str,
    n: int = 10,
) -> list[dict[str, Any]]:
    """Embed query and return the N most semantically similar vault chunks."""
    if not query.strip():
        return []
    chunk_count = store.conn.execute("SELECT count(*) FROM chunk_embeddings").fetchone()[0]
    if chunk_count == 0:
        return []
    try:
        vector = embedder.embed([query])[0]
        results = sq.search_similar(store.conn, vector, n=n)
    except Exception:
        return []
    return [
        {
            "path": r.note_relpath,
            "chunk_index": r.chunk_index,
            "section_header": r.section_header,
            "text": r.text,
            "score": r.score,
        }
        for r in results
    ]


def get_note_summary(store: IndexStore, note_relpath: str) -> str | None:
    """Return the LLM-generated summary for a note, or None if not available."""
    row = store.conn.execute(
        "SELECT summary FROM note_intelligence WHERE note_relpath = ?",
        [note_relpath],
    ).fetchone()
    return row[0] if row else None


def find_related_notes_semantic(
    store: IndexStore,
    note_relpath: str,
    n: int = 5,
) -> list[dict[str, Any]]:
    """Return notes most conceptually related to note_relpath, with summaries."""
    related = sq.find_related_notes(store.conn, note_relpath, n=n)
    results = []
    for relpath, score in related:
        summary_row = store.conn.execute(
            "SELECT summary FROM note_intelligence WHERE note_relpath = ?",
            [relpath],
        ).fetchone()
        results.append({
            "path": relpath,
            "overlap_score": score,
            "summary": summary_row[0] if summary_row else None,
        })
    return results


def list_concepts_mcp(store: IndexStore, n: int = 30) -> list[dict[str, Any]]:
    """Return the most prominent concepts across the vault."""
    concepts = sq.list_concepts(store.conn, n=n)
    return [
        {"name": c.name, "note_count": c.note_count, "avg_salience": c.avg_salience}
        for c in concepts
    ]


def search_by_concept_mcp(
    store: IndexStore,
    concept: str,
    n: int = 10,
) -> list[dict[str, Any]]:
    """Find notes/chunks that discuss a concept (case-insensitive substring match)."""
    concept_lower = concept.strip().lower()
    if not concept_lower:
        return []
    matching = store.conn.execute(
        "SELECT name FROM concepts WHERE name LIKE ?",
        [f"%{concept_lower}%"],
    ).fetchall()
    seen: set[tuple[str, int]] = set()
    results: list[dict[str, Any]] = []
    for (name,) in matching:
        for chunk in sq.search_by_concept(store.conn, name):
            key = (chunk.note_relpath, chunk.chunk_index)
            if key not in seen:
                seen.add(key)
                results.append({
                    "path": chunk.note_relpath,
                    "chunk_index": chunk.chunk_index,
                    "section_header": chunk.section_header,
                    "text": chunk.text,
                    "salience": chunk.score,
                })
    results.sort(key=lambda x: x["salience"], reverse=True)
    return results[:n]


def get_entity_context_mcp(
    store: IndexStore,
    name: str,
    n: int = 10,
) -> list[dict[str, Any]]:
    """Find vault chunks mentioning a named entity (case-insensitive substring)."""
    rows = store.conn.execute(
        """
        SELECT c.note_relpath, c.chunk_index, c.section_header, c.text, ce.context_snippet
        FROM chunk_entities ce
        JOIN chunks c   ON c.id  = ce.chunk_id
        JOIN entities e ON e.id  = ce.entity_id
        WHERE e.name ILIKE ?
        LIMIT ?
        """,
        [f"%{name}%", n],
    ).fetchall()
    return [
        {
            "path": row[0],
            "chunk_index": row[1],
            "section_header": row[2],
            "text": row[3],
            "context": row[4],
        }
        for row in rows
    ]


def get_recent_concepts_mcp(
    store: IndexStore,
    days: int = 14,
    n: int = 20,
) -> list[dict[str, Any]]:
    """Return top concepts in notes modified within the last N days."""
    concepts = sq.get_recent_concepts(store.conn, since_days=days, n=n)
    return [
        {"name": c.name, "note_count": c.note_count, "avg_salience": c.avg_salience}
        for c in concepts
    ]


def get_stale_concepts_mcp(
    store: IndexStore,
    inactive_before: str,
    n: int = 20,
) -> list[dict[str, Any]]:
    """Return concepts not seen in any note modified since inactive_before.

    inactive_before: ISO date string (e.g. '2025-09-01').
    Each entry has: name, last_seen_date, note_count, avg_salience.
    """
    concepts = sq.get_stale_concepts(store.conn, inactive_before=inactive_before, n=n)
    return [
        {
            "name": c.name,
            "last_seen_date": c.last_seen_date,
            "note_count": c.note_count,
            "avg_salience": c.avg_salience,
        }
        for c in concepts
    ]


# ---------------------------------------------------------------------------
# Feed tool (8-2)
# ---------------------------------------------------------------------------

def _parse_rss(root: ET.Element, max_items: int) -> list[dict[str, Any]]:
    items = []
    for item in root.findall("channel/item")[:max_items]:
        items.append({
            "title": (item.findtext("title") or "").strip(),
            "link": (item.findtext("link") or "").strip(),
            "published": (item.findtext("pubDate") or "").strip(),
            "summary": (item.findtext("description") or "").strip(),
        })
    return items


def _parse_atom(root: ET.Element, max_items: int) -> list[dict[str, Any]]:
    ns = "http://www.w3.org/2005/Atom"
    items = []
    for entry in root.findall(f"{{{ns}}}entry")[:max_items]:
        link_el = entry.find(f"{{{ns}}}link")
        link = link_el.get("href", "") if link_el is not None else ""
        items.append({
            "title": (entry.findtext(f"{{{ns}}}title") or "").strip(),
            "link": link,
            "published": (
                entry.findtext(f"{{{ns}}}published")
                or entry.findtext(f"{{{ns}}}updated")
                or ""
            ).strip(),
            "summary": (
                entry.findtext(f"{{{ns}}}summary")
                or entry.findtext(f"{{{ns}}}content")
                or ""
            ).strip(),
        })
    return items


def fetch_feed(url: str, max_items: int = 50) -> list[dict[str, Any]]:
    """Fetch and parse an RSS 2.0 or Atom 1.0 feed. Returns up to max_items entries."""
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = resp.read()
    except urllib.error.URLError as exc:
        raise ValueError(f"Failed to fetch feed {url!r}: {exc}") from exc

    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError(f"Failed to parse feed from {url!r}: not valid XML: {exc}") from exc

    tag = root.tag
    if tag == "rss" or tag.endswith("}rss"):
        return _parse_rss(root, max_items)
    if tag in ("{http://www.w3.org/2005/Atom}feed", "feed"):
        return _parse_atom(root, max_items)
    raise ValueError(f"Unrecognised feed format at {url!r}: root element is <{tag}>")


def get_implicit_items_mcp(
    store: IndexStore,
    item_type: str | None = None,
    since: str | None = None,
    n: int = 20,
) -> list[dict[str, Any]]:
    """Return informal ideas, questions, intentions, and tasks from vault prose.

    item_type: 'idea' | 'question' | 'intention' | 'task' | None (all)
    since: ISO date string — only items from notes modified on or after this date
    """
    if since is not None:
        import time
        since_date = date.fromisoformat(since)
        since_ns = int(time.mktime(since_date.timetuple()) * 1e9)
        conditions = ["ii.note_relpath = n.note_relpath", "n.mtime_ns >= ?"]
        params: list[Any] = [since_ns]
        if item_type:
            conditions.append("ii.type = ?")
            params.append(item_type)
        rows = store.conn.execute(
            f"""
            SELECT ii.note_relpath, ii.type, ii.text
            FROM implicit_items ii
            JOIN notes n ON n.note_relpath = ii.note_relpath
            WHERE {' AND '.join(conditions)}
            ORDER BY n.mtime_ns DESC
            LIMIT ?
            """,
            [*params, n],
        ).fetchall()
    else:
        items = sq.get_implicit_items(store.conn, item_type=item_type)
        rows = [(i.note_relpath, i.type, i.text) for i in items[:n]]
    return [{"path": row[0], "type": row[1], "text": row[2]} for row in rows]

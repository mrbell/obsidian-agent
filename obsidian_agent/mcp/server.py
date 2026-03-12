from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from obsidian_agent.index.store import IndexStore
from obsidian_agent.mcp import tools as _tools


def create_server(
    vault_path: Path,
    db_path: Path,
    semantic_model: str = "all-MiniLM-L6-v2",
) -> FastMCP:
    """Create and return a configured MCP server instance.

    The server holds an open IndexStore for the lifetime of the process.
    All exposed tools are read-only.

    The LocalEmbedder for semantic search is loaded lazily on the first
    search_similar call (model download ~80MB on first use).
    """
    mcp = FastMCP("obsidian-vault")
    store = IndexStore(db_path)

    # Lazy embedder: initialized once on first semantic search call
    _embedder_holder: list[Any] = [None]

    def _get_embedder() -> Any:
        if _embedder_holder[0] is None:
            from obsidian_agent.embeddings.local import LocalEmbedder
            _embedder_holder[0] = LocalEmbedder(semantic_model)
        return _embedder_holder[0]

    # -------------------------------------------------------------------------
    # Tools
    # -------------------------------------------------------------------------

    @mcp.tool()
    def search_notes(query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search note content for a query string. Returns matching paths and excerpts."""
        return _tools.search_notes(vault_path, store, query, limit=limit)

    @mcp.tool()
    def get_note(path: str) -> str:
        """Get the full content of a note by its relative path (e.g. 'folder/Note.md')."""
        return _tools.get_note(vault_path, path)

    @mcp.tool()
    def list_notes(
        folder: str | None = None,
        include_daily: bool = True,
    ) -> list[dict[str, Any]]:
        """List notes in the vault. Optionally filter by folder prefix and exclude daily notes."""
        return _tools.list_notes(store, folder=folder, include_daily=include_daily)

    @mcp.tool()
    def get_daily_notes(start_date: str, end_date: str) -> list[dict[str, Any]]:
        """Get daily notes (YYYY-MM-DD filename) in a date range, with full content.

        Dates must be ISO format strings: 'YYYY-MM-DD'.
        """
        return _tools.get_daily_notes(vault_path, store, start_date, end_date)

    @mcp.tool()
    def query_tasks(
        status: str = "open",
        due_before: str | None = None,
    ) -> list[dict[str, Any]]:
        """Query tasks from the index.

        status: 'open' | 'done' | 'cancelled' | 'in_progress'
        due_before: ISO date string — only tasks due on or before this date
        """
        return _tools.query_tasks(store, status=status, due_before=due_before)

    @mcp.tool()
    def get_note_links(path: str) -> dict[str, list[str]]:
        """Get outgoing and incoming wikilinks/markdown links for a note."""
        return _tools.get_note_links(store, path)

    @mcp.tool()
    def find_notes_by_tag(tag: str) -> list[str]:
        """Find all notes that have a given tag (inline or frontmatter)."""
        return _tools.find_notes_by_tag(store, tag)

    @mcp.tool()
    def get_vault_stats() -> dict[str, Any]:
        """Get summary statistics: note count, task count, last indexed timestamp."""
        return _tools.get_vault_stats(store)

    # -------------------------------------------------------------------------
    # Semantic tools (Milestone 6-5)
    # -------------------------------------------------------------------------

    @mcp.tool()
    def search_similar(query: str, n: int = 10) -> list[dict[str, Any]]:
        """Semantic search: embed query and return the N most similar vault chunks.

        Requires the semantic index to be built (obsidian-agent index-semantic).
        Returns [] with no error if the semantic index is absent.
        """
        return _tools.search_similar(store, _get_embedder(), query, n=n)

    @mcp.tool()
    def get_note_summary(note_relpath: str) -> str | None:
        """Return the LLM-generated 2-4 sentence summary for a note.

        Returns None if the note has no summary yet (run index-semantic first).
        """
        return _tools.get_note_summary(store, note_relpath)

    @mcp.tool()
    def find_related_notes(note_relpath: str, n: int = 5) -> list[dict[str, Any]]:
        """Find the N notes most conceptually related to note_relpath.

        Similarity is based on shared concepts weighted by salience.
        Returns each related note's path, overlap score, and summary (if available).
        """
        return _tools.find_related_notes_semantic(store, note_relpath, n=n)

    @mcp.tool()
    def list_concepts(n: int = 30) -> list[dict[str, Any]]:
        """Return the most prominent concepts in the vault, ranked by note count.

        Each entry has: name, note_count, avg_salience.
        """
        return _tools.list_concepts_mcp(store, n=n)

    @mcp.tool()
    def search_by_concept(concept: str, n: int = 10) -> list[dict[str, Any]]:
        """Find notes and chunks discussing a concept (case-insensitive substring match).

        Returns chunks sorted by salience: path, text, section_header, salience.
        """
        return _tools.search_by_concept_mcp(store, concept, n=n)

    @mcp.tool()
    def get_entity_context(name: str, n: int = 10) -> list[dict[str, Any]]:
        """Find vault chunks mentioning a named entity (case-insensitive substring match).

        Useful for: people, projects, tools, book titles, locations.
        Returns: path, text, section_header, context snippet.
        """
        return _tools.get_entity_context_mcp(store, name, n=n)

    @mcp.tool()
    def get_recent_concepts(days: int = 14, n: int = 20) -> list[dict[str, Any]]:
        """Return top concepts in notes modified in the last N days.

        Useful for understanding what the user has been thinking about recently.
        Each entry has: name, note_count, avg_salience.
        """
        return _tools.get_recent_concepts_mcp(store, days=days, n=n)

    @mcp.tool()
    def get_stale_concepts(inactive_before: str, n: int = 20) -> list[dict[str, Any]]:
        """Return concepts not seen in any note modified since inactive_before.

        inactive_before: ISO date string (e.g. '2025-09-01').
        Useful for finding 'orphaned threads' — ideas the user was active on that have
        since gone quiet. Each entry has: name, last_seen_date, note_count, avg_salience.
        """
        return _tools.get_stale_concepts_mcp(store, inactive_before=inactive_before, n=n)

    @mcp.tool()
    def fetch_feed(url: str) -> list[dict[str, Any]]:
        """Fetch and parse an RSS 2.0 or Atom 1.0 feed URL.

        Returns up to 50 entries, each with: title, link, published, summary.
        Raises an error if the URL is unreachable or not a recognised feed format.
        Use the 'published' field to filter by recency.
        """
        return _tools.fetch_feed(url)

    @mcp.tool()
    def get_implicit_items(
        type: str | None = None,
        since: str | None = None,
        n: int = 20,
    ) -> list[dict[str, Any]]:
        """Return informal ideas, questions, intentions, and tasks from vault prose.

        type: 'idea' | 'question' | 'intention' | 'task' | None (all types)
        since: ISO date string — only items from notes modified on or after this date
        Each entry has: path, type, text.
        """
        return _tools.get_implicit_items_mcp(store, item_type=type, since=since, n=n)

    return mcp


def run_server(
    vault_path: Path,
    db_path: Path,
    semantic_model: str = "all-MiniLM-L6-v2",
) -> None:
    """Create and run the MCP server on stdio (blocking until process is killed)."""
    server = create_server(vault_path, db_path, semantic_model=semantic_model)
    server.run(transport="stdio")

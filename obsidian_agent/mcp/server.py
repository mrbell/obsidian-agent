from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from obsidian_agent.index.store import IndexStore
from obsidian_agent.mcp import tools as _tools


def create_server(vault_path: Path, db_path: Path) -> FastMCP:
    """Create and return a configured MCP server instance.

    The server holds an open IndexStore for the lifetime of the process.
    All exposed tools are read-only.
    """
    mcp = FastMCP("obsidian-vault")
    store = IndexStore(db_path)

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

    return mcp


def run_server(vault_path: Path, db_path: Path) -> None:
    """Create and run the MCP server on stdio (blocking until process is killed)."""
    server = create_server(vault_path, db_path)
    server.run(transport="stdio")

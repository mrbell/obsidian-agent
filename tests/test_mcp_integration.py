"""MCP protocol integration tests.

Tests exercise the server through the MCP protocol using an in-process
memory transport (no subprocess needed). This verifies tool dispatch,
serialization, and the list_tools response end-to-end.
"""
from __future__ import annotations

import json
from pathlib import Path

import anyio
import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from obsidian_agent.index.build_index import build_index
from obsidian_agent.index.store import IndexStore
from obsidian_agent.mcp.server import create_server


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

EXPECTED_TOOLS = {
    # Structural tools (Milestone 4)
    "search_notes",
    "get_note",
    "list_notes",
    "get_daily_notes",
    "query_tasks",
    "get_note_links",
    "find_notes_by_tag",
    "get_vault_stats",
    # Semantic tools (Milestone 6-5)
    "search_similar",
    "get_note_summary",
    "find_related_notes",
    "list_concepts",
    "search_by_concept",
    "get_entity_context",
    "get_recent_concepts",
    "get_implicit_items",
    # Semantic tools (Milestone 7)
    "get_stale_concepts",
    "get_unlinked_related_notes",
    # Feed tool (Milestone 8-2)
    "fetch_feed",
}


@pytest.fixture()
def vault(tmp_path: Path) -> Path:
    v = tmp_path / "vault"
    v.mkdir()
    return v


@pytest.fixture()
def server(vault: Path, tmp_path: Path):
    """Return a configured FastMCP server with a populated vault."""
    (vault / "Projects").mkdir()
    (vault / "Projects" / "Note.md").write_text(
        "# Test Note\n\n#testing\n\n[[OtherNote]]\n\n- [ ] Open task 📅 2026-03-10\n- [x] Done task\n",
        encoding="utf-8",
    )
    (vault / "2026-03-08.md").write_text(
        "# 2026-03-08\n\nDaily note.\n",
        encoding="utf-8",
    )

    db_path = tmp_path / "index.duckdb"
    with IndexStore(db_path) as store:
        build_index(vault, store)

    return create_server(vault, db_path)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
#
# FastMCP serialization rules:
#   - dict return value  → single TextContent with JSON string
#   - list return value  → one TextContent per element
#       - list-of-dict items are JSON-encoded per element
#       - list-of-str items are raw strings per element
#   - empty list         → result.content == []
#

def _items(result) -> list[str]:
    """Return raw text strings from all TextContent items."""
    return [c.text for c in result.content if hasattr(c, "text")]


def _json_obj(result) -> dict:
    """Parse a single-dict tool result."""
    return json.loads(_items(result)[0])


def _json_list(result) -> list:
    """Parse a list tool result — each TextContent item is one element."""
    items = _items(result)
    out = []
    for item in items:
        try:
            out.append(json.loads(item))
        except json.JSONDecodeError:
            out.append(item)
    return out


# ---------------------------------------------------------------------------
# list_tools — confirms read-only tool set
# ---------------------------------------------------------------------------

def test_list_tools_returns_expected_tools(server):
    async def run():
        async with create_connected_server_and_client_session(server) as client:
            result = await client.list_tools()
            names = {t.name for t in result.tools}
            assert names == EXPECTED_TOOLS

    anyio.run(run)


def test_list_tools_contains_no_write_tools(server):
    async def run():
        async with create_connected_server_and_client_session(server) as client:
            result = await client.list_tools()
            names = {t.name for t in result.tools}
            for name in names:
                assert not any(
                    word in name for word in ("write", "create", "delete", "update", "insert")
                )

    anyio.run(run)


# ---------------------------------------------------------------------------
# get_vault_stats
# ---------------------------------------------------------------------------

def test_get_vault_stats(server):
    async def run():
        async with create_connected_server_and_client_session(server) as client:
            result = await client.call_tool("get_vault_stats", {})
            assert not result.isError
            data = _json_obj(result)
            assert data["note_count"] == 2
            assert data["task_count"] > 0
            assert data["last_indexed_at"] is not None

    anyio.run(run)


# ---------------------------------------------------------------------------
# list_notes
# ---------------------------------------------------------------------------

def test_list_notes_returns_all(server):
    async def run():
        async with create_connected_server_and_client_session(server) as client:
            result = await client.call_tool("list_notes", {})
            assert not result.isError
            notes = _json_list(result)
            paths = [n["path"] for n in notes]
            assert "Projects/Note.md" in paths

    anyio.run(run)


def test_list_notes_folder_filter(server):
    async def run():
        async with create_connected_server_and_client_session(server) as client:
            result = await client.call_tool("list_notes", {"folder": "Projects"})
            assert not result.isError
            notes = _json_list(result)
            assert all(n["path"].startswith("Projects/") for n in notes)

    anyio.run(run)


# ---------------------------------------------------------------------------
# get_note
# ---------------------------------------------------------------------------

def test_get_note_returns_content(server):
    async def run():
        async with create_connected_server_and_client_session(server) as client:
            result = await client.call_tool("get_note", {"path": "Projects/Note.md"})
            assert not result.isError
            assert "Test Note" in _items(result)[0]

    anyio.run(run)


def test_get_note_missing_returns_error(server):
    async def run():
        async with create_connected_server_and_client_session(server) as client:
            result = await client.call_tool("get_note", {"path": "DoesNotExist.md"})
            assert result.isError

    anyio.run(run)


# ---------------------------------------------------------------------------
# query_tasks
# ---------------------------------------------------------------------------

def test_query_tasks_open(server):
    async def run():
        async with create_connected_server_and_client_session(server) as client:
            result = await client.call_tool("query_tasks", {"status": "open"})
            assert not result.isError
            tasks = _json_list(result)
            texts = [t["text"] for t in tasks]
            assert any("Open task" in t for t in texts)

    anyio.run(run)


def test_query_tasks_empty_result_is_not_error(server):
    async def run():
        async with create_connected_server_and_client_session(server) as client:
            result = await client.call_tool("query_tasks", {"status": "cancelled"})
            assert not result.isError
            assert result.content == []

    anyio.run(run)


# ---------------------------------------------------------------------------
# find_notes_by_tag
# ---------------------------------------------------------------------------

def test_find_notes_by_tag(server):
    async def run():
        async with create_connected_server_and_client_session(server) as client:
            result = await client.call_tool("find_notes_by_tag", {"tag": "testing"})
            assert not result.isError
            notes = _items(result)  # list of str paths
            assert "Projects/Note.md" in notes

    anyio.run(run)


def test_find_notes_by_tag_unknown_returns_empty(server):
    async def run():
        async with create_connected_server_and_client_session(server) as client:
            result = await client.call_tool("find_notes_by_tag", {"tag": "nosuchtagxyz"})
            assert not result.isError
            assert result.content == []

    anyio.run(run)


# ---------------------------------------------------------------------------
# get_note_links
# ---------------------------------------------------------------------------

def test_get_note_links(server):
    async def run():
        async with create_connected_server_and_client_session(server) as client:
            result = await client.call_tool("get_note_links", {"path": "Projects/Note.md"})
            assert not result.isError
            links = _json_obj(result)
            assert "OtherNote" in links["outgoing"]

    anyio.run(run)


# ---------------------------------------------------------------------------
# search_notes
# ---------------------------------------------------------------------------

def test_search_notes_finds_match(server):
    async def run():
        async with create_connected_server_and_client_session(server) as client:
            result = await client.call_tool("search_notes", {"query": "Daily note"})
            assert not result.isError
            results = _json_list(result)
            paths = [r["path"] for r in results]
            assert "2026-03-08.md" in paths

    anyio.run(run)


def test_search_notes_no_match_returns_empty(server):
    async def run():
        async with create_connected_server_and_client_session(server) as client:
            result = await client.call_tool("search_notes", {"query": "zzznomatchzzz"})
            assert not result.isError
            assert result.content == []

    anyio.run(run)


# ---------------------------------------------------------------------------
# get_daily_notes
# ---------------------------------------------------------------------------

def test_get_daily_notes_in_range(server):
    async def run():
        async with create_connected_server_and_client_session(server) as client:
            result = await client.call_tool(
                "get_daily_notes", {"start_date": "2026-03-08", "end_date": "2026-03-08"}
            )
            assert not result.isError
            notes = _json_list(result)
            assert len(notes) == 1
            assert notes[0]["path"] == "2026-03-08.md"
            assert "Daily note" in notes[0]["content"]

    anyio.run(run)


def test_get_daily_notes_empty_range(server):
    async def run():
        async with create_connected_server_and_client_session(server) as client:
            result = await client.call_tool(
                "get_daily_notes", {"start_date": "2020-01-01", "end_date": "2020-01-31"}
            )
            assert not result.isError
            assert result.content == []

    anyio.run(run)

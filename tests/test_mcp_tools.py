from __future__ import annotations

from pathlib import Path

import pytest

from obsidian_agent.index.build_index import build_index
from obsidian_agent.index.store import IndexStore
from obsidian_agent.mcp import tools


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def vault(tmp_path: Path) -> Path:
    v = tmp_path / "vault"
    v.mkdir()
    return v


@pytest.fixture()
def populated(vault: Path, tmp_path: Path):
    """Build a fixture vault with known content and return (vault, store)."""
    (vault / "Projects").mkdir()
    (vault / "Journal").mkdir()

    (vault / "Projects" / "Alpha.md").write_text(
        "# Project Alpha\n\n#work #active\n\n"
        "Links to [[Beta]] and [external](https://example.com).\n\n"
        "- [ ] Write proposal 📅 2026-03-10\n"
        "- [x] Research done\n",
        encoding="utf-8",
    )
    (vault / "Projects" / "Beta.md").write_text(
        "# Project Beta\n\n#work\n\nSee also [[Alpha]].\n\n"
        "- [ ] Draft spec 📅 2026-03-05\n",
        encoding="utf-8",
    )
    (vault / "Ideas.md").write_text(
        "# Ideas\n\n#personal\n\nRandom ideas about python and automation.\n",
        encoding="utf-8",
    )
    (vault / "Journal" / "2026-03-07.md").write_text(
        "# 2026-03-07\n\nDaily note content.\n\n- [ ] Follow up on Alpha\n",
        encoding="utf-8",
    )
    (vault / "Journal" / "2026-03-08.md").write_text(
        "# 2026-03-08\n\nAnother daily note.\n",
        encoding="utf-8",
    )

    db_path = tmp_path / "index.duckdb"
    store = IndexStore(db_path)
    build_index(vault, store)
    return vault, store


# ---------------------------------------------------------------------------
# get_note
# ---------------------------------------------------------------------------

class TestGetNote:
    def test_returns_content(self, populated):
        vault, store = populated
        content = tools.get_note(vault, "Projects/Alpha.md")
        assert "Project Alpha" in content

    def test_raises_for_missing_note(self, populated):
        vault, store = populated
        with pytest.raises(FileNotFoundError):
            tools.get_note(vault, "Nonexistent.md")

    def test_rejects_path_traversal(self, populated):
        vault, store = populated
        with pytest.raises((ValueError, FileNotFoundError)):
            tools.get_note(vault, "../../etc/passwd")


# ---------------------------------------------------------------------------
# list_notes
# ---------------------------------------------------------------------------

class TestListNotes:
    def test_returns_all_notes(self, populated):
        vault, store = populated
        result = tools.list_notes(store)
        paths = [r["path"] for r in result]
        assert "Projects/Alpha.md" in paths
        assert "Ideas.md" in paths

    def test_filters_by_folder(self, populated):
        vault, store = populated
        result = tools.list_notes(store, folder="Projects")
        paths = [r["path"] for r in result]
        assert all(p.startswith("Projects/") for p in paths)
        assert "Ideas.md" not in paths

    def test_excludes_daily_notes_when_requested(self, populated):
        vault, store = populated
        result = tools.list_notes(store, include_daily=False)
        paths = [r["path"] for r in result]
        assert not any("2026-" in p for p in paths)

    def test_empty_folder_returns_empty(self, populated):
        vault, store = populated
        result = tools.list_notes(store, folder="NoSuchFolder")
        assert result == []


# ---------------------------------------------------------------------------
# get_daily_notes
# ---------------------------------------------------------------------------

class TestGetDailyNotes:
    def test_returns_notes_in_range(self, populated):
        vault, store = populated
        result = tools.get_daily_notes(vault, store, "2026-03-07", "2026-03-08")
        paths = [r["path"] for r in result]
        assert "Journal/2026-03-07.md" in paths
        assert "Journal/2026-03-08.md" in paths

    def test_excludes_out_of_range(self, populated):
        vault, store = populated
        result = tools.get_daily_notes(vault, store, "2026-03-08", "2026-03-08")
        paths = [r["path"] for r in result]
        assert "Journal/2026-03-07.md" not in paths
        assert "Journal/2026-03-08.md" in paths

    def test_includes_content(self, populated):
        vault, store = populated
        result = tools.get_daily_notes(vault, store, "2026-03-07", "2026-03-07")
        assert len(result) == 1
        assert "Daily note content" in result[0]["content"]

    def test_empty_range_returns_empty(self, populated):
        vault, store = populated
        result = tools.get_daily_notes(vault, store, "2020-01-01", "2020-01-31")
        assert result == []


# ---------------------------------------------------------------------------
# query_tasks
# ---------------------------------------------------------------------------

class TestQueryTasks:
    def test_returns_open_tasks_by_default(self, populated):
        vault, store = populated
        result = tools.query_tasks(store)
        statuses = {r["status"] if "status" in r else "open" for r in result}
        # All returned tasks should be open (we didn't pass status filter here,
        # but query_tasks defaults to status="open")
        texts = [r["text"] for r in result]
        assert any("proposal" in t for t in texts)

    def test_excludes_done_tasks_by_default(self, populated):
        vault, store = populated
        result = tools.query_tasks(store)
        texts = [r["text"] for r in result]
        assert not any("Research done" in t for t in texts)

    def test_due_before_filter(self, populated):
        vault, store = populated
        result = tools.query_tasks(store, due_before="2026-03-06")
        texts = [r["text"] for r in result]
        assert any("Draft spec" in t for t in texts)
        assert not any("proposal" in t for t in texts)

    def test_returns_done_tasks_when_requested(self, populated):
        vault, store = populated
        result = tools.query_tasks(store, status="done")
        texts = [r["text"] for r in result]
        assert any("Research done" in t for t in texts)


# ---------------------------------------------------------------------------
# find_notes_by_tag
# ---------------------------------------------------------------------------

class TestFindNotesByTag:
    def test_finds_tagged_notes(self, populated):
        vault, store = populated
        result = tools.find_notes_by_tag(store, "work")
        assert "Projects/Alpha.md" in result
        assert "Projects/Beta.md" in result

    def test_excludes_untagged(self, populated):
        vault, store = populated
        result = tools.find_notes_by_tag(store, "work")
        assert "Ideas.md" not in result

    def test_unknown_tag_returns_empty(self, populated):
        vault, store = populated
        result = tools.find_notes_by_tag(store, "nosuchtagxyz")
        assert result == []


# ---------------------------------------------------------------------------
# get_note_links
# ---------------------------------------------------------------------------

class TestGetNoteLinks:
    def test_outgoing_links(self, populated):
        vault, store = populated
        result = tools.get_note_links(store, "Projects/Alpha.md")
        assert "Beta" in result["outgoing"]

    def test_incoming_links(self, populated):
        vault, store = populated
        result = tools.get_note_links(store, "Projects/Beta.md")
        # Alpha links to Beta, Beta links to Alpha
        assert "Projects/Alpha.md" in result["incoming"]

    def test_no_links_returns_empty_lists(self, populated):
        vault, store = populated
        result = tools.get_note_links(store, "Ideas.md")
        assert result["outgoing"] == []
        assert result["incoming"] == []


# ---------------------------------------------------------------------------
# search_notes
# ---------------------------------------------------------------------------

class TestSearchNotes:
    def test_finds_matching_note(self, populated):
        vault, store = populated
        result = tools.search_notes(vault, store, "automation")
        paths = [r["path"] for r in result]
        assert "Ideas.md" in paths

    def test_excerpt_contains_query_term(self, populated):
        vault, store = populated
        result = tools.search_notes(vault, store, "automation")
        assert any("automation" in r["excerpt"].lower() for r in result)

    def test_case_insensitive(self, populated):
        vault, store = populated
        result = tools.search_notes(vault, store, "AUTOMATION")
        paths = [r["path"] for r in result]
        assert "Ideas.md" in paths

    def test_no_match_returns_empty(self, populated):
        vault, store = populated
        result = tools.search_notes(vault, store, "zzznomatchzzz")
        assert result == []

    def test_limit_respected(self, populated):
        vault, store = populated
        result = tools.search_notes(vault, store, "note", limit=2)
        assert len(result) <= 2


# ---------------------------------------------------------------------------
# get_vault_stats
# ---------------------------------------------------------------------------

class TestGetVaultStats:
    def test_returns_note_count(self, populated):
        vault, store = populated
        stats = tools.get_vault_stats(store)
        assert stats["note_count"] == 5

    def test_returns_task_count(self, populated):
        vault, store = populated
        stats = tools.get_vault_stats(store)
        assert stats["task_count"] > 0

    def test_returns_last_indexed_at(self, populated):
        vault, store = populated
        stats = tools.get_vault_stats(store)
        assert stats["last_indexed_at"] is not None

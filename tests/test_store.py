from pathlib import Path

import pytest

from obsidian_agent.index.store import IndexStore

_ALL_TABLES = {
    "notes",
    "frontmatter",
    "headings",
    "tasks",
    "links",
    "tags",
    "meta",
    "note_summaries",
    "topic_clusters",
    # Semantic index tables (Milestone 6)
    "chunks",
    "chunk_embeddings",
    "note_intelligence",
    "concepts",
    "chunk_concepts",
    "entities",
    "chunk_entities",
    "implicit_items",
}


def _table_names(store: IndexStore) -> set[str]:
    rows = store.conn.execute("SHOW TABLES").fetchall()
    return {row[0] for row in rows}


class TestIndexStoreInit:
    def test_opens_without_error(self, tmp_path: Path) -> None:
        store = IndexStore(tmp_path / "index.duckdb")
        store.close()

    def test_all_tables_created(self, tmp_path: Path) -> None:
        with IndexStore(tmp_path / "index.duckdb") as store:
            assert _table_names(store) == _ALL_TABLES

    def test_init_is_idempotent(self, tmp_path: Path) -> None:
        db = tmp_path / "index.duckdb"
        with IndexStore(db):
            pass
        # Second open against same file must not raise
        with IndexStore(db) as store:
            assert _table_names(store) == _ALL_TABLES

    def test_data_survives_reopen(self, tmp_path: Path) -> None:
        db = tmp_path / "index.duckdb"
        with IndexStore(db) as store:
            store.conn.execute(
                "INSERT INTO notes VALUES (?, ?, ?, ?, ?, ?, ?)",
                ["notes/test.md", "Test", False, 0, 0, "abc", 10],
            )
        with IndexStore(db) as store:
            row = store.conn.execute(
                "SELECT title FROM notes WHERE note_relpath = ?",
                ["notes/test.md"],
            ).fetchone()
            assert row is not None
            assert row[0] == "Test"


class TestIndexStoreContextManager:
    def test_context_manager_closes_connection(self, tmp_path: Path) -> None:
        with IndexStore(tmp_path / "index.duckdb") as store:
            conn = store.conn
        # Connection should be closed; further queries should raise
        with pytest.raises(Exception):
            conn.execute("SELECT 1")

    def test_returns_self_from_enter(self, tmp_path: Path) -> None:
        store = IndexStore(tmp_path / "index.duckdb")
        with store as ctx:
            assert ctx is store

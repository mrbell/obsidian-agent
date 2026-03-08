from pathlib import Path

import pytest

from obsidian_agent.index.build_index import IndexStats, build_index
from obsidian_agent.index.store import IndexStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def vault(tmp_path: Path) -> Path:
    d = tmp_path / "vault"
    d.mkdir()
    return d


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "index.duckdb"


def _count(store: IndexStore, table: str, relpath: str) -> int:
    return store.conn.execute(
        f"SELECT count(*) FROM {table} WHERE note_relpath = ?", [relpath]
    ).fetchone()[0]


def _note_row(store: IndexStore, relpath: str):
    return store.conn.execute(
        "SELECT * FROM notes WHERE note_relpath = ?", [relpath]
    ).fetchone()


# ---------------------------------------------------------------------------
# New note
# ---------------------------------------------------------------------------

class TestNewNote:
    def test_new_note_added_to_notes(self, vault: Path, db_path: Path) -> None:
        (vault / "note.md").write_text("# Hello\n\nWorld.")
        with IndexStore(db_path) as store:
            stats = build_index(vault, store)
        assert stats.added == 1
        assert stats.scanned == 1

    def test_new_note_title_indexed(self, vault: Path, db_path: Path) -> None:
        (vault / "note.md").write_text("# My Title\n\nContent.")
        with IndexStore(db_path) as store:
            build_index(vault, store)
            row = _note_row(store, "note.md")
        assert row is not None
        assert row[1] == "My Title"  # title column

    def test_new_note_derived_rows_inserted(self, vault: Path, db_path: Path) -> None:
        content = "# Task Note\n\n- [ ] Do something 📅 2026-03-10\n\n#work"
        (vault / "note.md").write_text(content)
        with IndexStore(db_path) as store:
            build_index(vault, store)
            assert _count(store, "tasks", "note.md") == 1
            assert _count(store, "tags", "note.md") == 1
            assert _count(store, "headings", "note.md") == 1

    def test_multiple_notes(self, vault: Path, db_path: Path) -> None:
        (vault / "a.md").write_text("# A")
        (vault / "b.md").write_text("# B")
        with IndexStore(db_path) as store:
            stats = build_index(vault, store)
        assert stats.added == 2
        assert stats.scanned == 2


# ---------------------------------------------------------------------------
# Unchanged note
# ---------------------------------------------------------------------------

class TestUnchangedNote:
    def test_unchanged_note_skipped(self, vault: Path, db_path: Path) -> None:
        (vault / "note.md").write_text("# Note\n\nContent.")
        with IndexStore(db_path) as store:
            build_index(vault, store)
        with IndexStore(db_path) as store:
            stats = build_index(vault, store)
        assert stats.unchanged == 1
        assert stats.added == 0
        assert stats.updated == 0


# ---------------------------------------------------------------------------
# Modified note
# ---------------------------------------------------------------------------

class TestModifiedNote:
    def test_modified_note_updates_derived_rows(self, vault: Path, db_path: Path) -> None:
        path = vault / "note.md"
        path.write_text("# Note\n\n- [ ] Old task\n")
        with IndexStore(db_path) as store:
            build_index(vault, store)

        # Overwrite with new content (different task)
        path.write_text("# Note\n\n- [ ] New task\n")
        with IndexStore(db_path) as store:
            stats = build_index(vault, store)
            assert stats.updated == 1
            task_text = store.conn.execute(
                "SELECT text FROM tasks WHERE note_relpath = ?", ["note.md"]
            ).fetchone()[0]
        assert task_text == "New task"

    def test_modified_note_old_derived_rows_removed(self, vault: Path, db_path: Path) -> None:
        path = vault / "note.md"
        path.write_text("# Note\n\n#oldtag\n")
        with IndexStore(db_path) as store:
            build_index(vault, store)

        path.write_text("# Note\n\n#newtag\n")
        with IndexStore(db_path) as store:
            build_index(vault, store)
            tags = store.conn.execute(
                "SELECT tag FROM tags WHERE note_relpath = ?", ["note.md"]
            ).fetchall()
        tag_names = {row[0] for row in tags}
        assert "newtag" in tag_names
        assert "oldtag" not in tag_names


# ---------------------------------------------------------------------------
# Metadata-only change (mtime bumped, content unchanged)
# ---------------------------------------------------------------------------

class TestMetadataOnlyChange:
    def test_metadata_updated_no_reparse(self, vault: Path, db_path: Path) -> None:
        path = vault / "note.md"
        content = "# Note\n\n- [ ] A task\n"
        path.write_text(content)

        with IndexStore(db_path) as store:
            build_index(vault, store)
            old_mtime = _note_row(store, "note.md")[3]  # mtime_ns column

        # Write identical content — updates mtime, same sha256
        path.write_text(content)

        with IndexStore(db_path) as store:
            stats = build_index(vault, store)
            new_mtime = _note_row(store, "note.md")[3]
            task_count = _count(store, "tasks", "note.md")

        assert stats.updated == 1
        assert stats.unchanged == 0
        assert new_mtime != old_mtime
        # Derived row still present
        assert task_count == 1


# ---------------------------------------------------------------------------
# Deleted note
# ---------------------------------------------------------------------------

class TestDeletedNote:
    def test_deleted_note_removed_from_notes(self, vault: Path, db_path: Path) -> None:
        path = vault / "note.md"
        path.write_text("# Note\n\nContent.")
        with IndexStore(db_path) as store:
            build_index(vault, store)

        path.unlink()
        with IndexStore(db_path) as store:
            stats = build_index(vault, store)
            assert _note_row(store, "note.md") is None
        assert stats.deleted == 1

    def test_deleted_note_derived_rows_removed(self, vault: Path, db_path: Path) -> None:
        path = vault / "note.md"
        path.write_text("# Note\n\n- [ ] Task\n\n#tag\n")
        with IndexStore(db_path) as store:
            build_index(vault, store)

        path.unlink()
        with IndexStore(db_path) as store:
            build_index(vault, store)
            assert _count(store, "tasks", "note.md") == 0
            assert _count(store, "tags", "note.md") == 0
            assert _count(store, "headings", "note.md") == 0


# ---------------------------------------------------------------------------
# Renamed note
# ---------------------------------------------------------------------------

class TestRenamedNote:
    def test_renamed_note_relpath_updated(self, vault: Path, db_path: Path) -> None:
        old = vault / "old-name.md"
        old.write_text("# My Note\n\n- [ ] A task\n")
        with IndexStore(db_path) as store:
            build_index(vault, store)

        content = old.read_text()
        old.unlink()
        (vault / "new-name.md").write_text(content)

        with IndexStore(db_path) as store:
            stats = build_index(vault, store)
            old_row = _note_row(store, "old-name.md")
            new_row = _note_row(store, "new-name.md")

        assert stats.renamed == 1
        assert stats.added == 0
        assert stats.deleted == 0
        assert old_row is None
        assert new_row is not None

    def test_renamed_note_derived_data_preserved(self, vault: Path, db_path: Path) -> None:
        old = vault / "old-name.md"
        old.write_text("# My Note\n\n- [ ] Important task\n")
        with IndexStore(db_path) as store:
            build_index(vault, store)

        content = old.read_text()
        old.unlink()
        (vault / "new-name.md").write_text(content)

        with IndexStore(db_path) as store:
            build_index(vault, store)
            # Derived data moved to new relpath
            assert _count(store, "tasks", "new-name.md") == 1
            assert _count(store, "tasks", "old-name.md") == 0

    def test_rename_stats_not_counted_as_add_or_delete(
        self, vault: Path, db_path: Path
    ) -> None:
        old = vault / "a.md"
        old.write_text("# Note A\n")
        with IndexStore(db_path) as store:
            build_index(vault, store)

        content = old.read_text()
        old.unlink()
        (vault / "b.md").write_text(content)

        with IndexStore(db_path) as store:
            stats = build_index(vault, store)

        assert stats.renamed == 1
        assert stats.added == 0
        assert stats.deleted == 0

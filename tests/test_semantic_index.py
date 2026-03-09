"""Tests for the semantic index embedding phase."""
from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from obsidian_agent.embeddings.base import Embedder
from obsidian_agent.index.build_index import build_index
from obsidian_agent.index.semantic import run_embedding_phase
from obsidian_agent.index.store import IndexStore


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def _words(n: int, seed: str = "word") -> str:
    return " ".join([f"{seed}{i}" for i in range(n)])


class FakeEmbedder(Embedder):
    """Deterministic fake embedder: returns zero vectors of correct dimension."""

    def __init__(self, dim: int = 384) -> None:
        self._dim = dim
        self.call_count = 0
        self.last_texts: list[str] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.call_count += 1
        self.last_texts = texts
        return [[0.0] * self._dim for _ in texts]

    @property
    def dimension(self) -> int:
        return self._dim


def _make_note(vault: Path, relpath: str, content: str) -> Path:
    path = vault / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _chunk_count(store: IndexStore, note_relpath: str | None = None) -> int:
    if note_relpath:
        return store.conn.execute(
            "SELECT count(*) FROM chunks WHERE note_relpath = ?", [note_relpath]
        ).fetchone()[0]
    return store.conn.execute("SELECT count(*) FROM chunks").fetchone()[0]


def _embedding_count(store: IndexStore, note_relpath: str | None = None) -> int:
    if note_relpath:
        return store.conn.execute(
            "SELECT count(*) FROM chunk_embeddings ce "
            "JOIN chunks c ON ce.chunk_id = c.id "
            "WHERE c.note_relpath = ?",
            [note_relpath],
        ).fetchone()[0]
    return store.conn.execute("SELECT count(*) FROM chunk_embeddings").fetchone()[0]


@pytest.fixture()
def vault(tmp_path: Path) -> Path:
    v = tmp_path / "vault"
    v.mkdir()
    return v


@pytest.fixture()
def store(tmp_path: Path) -> IndexStore:
    s = IndexStore(tmp_path / "index.duckdb")
    yield s
    s.close()


@pytest.fixture()
def embedder() -> FakeEmbedder:
    return FakeEmbedder()


# ---------------------------------------------------------------------------
# Basic embedding
# ---------------------------------------------------------------------------

class TestNewNotesEmbedded:
    def test_new_note_gets_chunks(self, vault: Path, store: IndexStore, embedder: FakeEmbedder) -> None:
        _make_note(vault, "note.md", _words(80))
        build_index(vault, store)
        run_embedding_phase(vault, store, embedder)
        assert _chunk_count(store, "note.md") >= 1

    def test_new_note_gets_embeddings(self, vault: Path, store: IndexStore, embedder: FakeEmbedder) -> None:
        _make_note(vault, "note.md", _words(80))
        build_index(vault, store)
        run_embedding_phase(vault, store, embedder)
        assert _embedding_count(store, "note.md") >= 1

    def test_chunk_and_embedding_counts_match(self, vault: Path, store: IndexStore, embedder: FakeEmbedder) -> None:
        _make_note(vault, "note.md", _words(80))
        build_index(vault, store)
        run_embedding_phase(vault, store, embedder)
        assert _chunk_count(store) == _embedding_count(store)

    def test_stats_reports_notes_processed(self, vault: Path, store: IndexStore, embedder: FakeEmbedder) -> None:
        _make_note(vault, "a.md", _words(80))
        _make_note(vault, "b.md", _words(80))
        build_index(vault, store)
        stats = run_embedding_phase(vault, store, embedder)
        assert stats.notes_processed == 2
        assert stats.notes_skipped == 0

    def test_stats_reports_chunks_embedded(self, vault: Path, store: IndexStore, embedder: FakeEmbedder) -> None:
        _make_note(vault, "note.md", _words(80))
        build_index(vault, store)
        stats = run_embedding_phase(vault, store, embedder)
        assert stats.chunks_embedded == stats.chunks_generated
        assert stats.chunks_embedded >= 1

    def test_embedded_sha256_stored(self, vault: Path, store: IndexStore, embedder: FakeEmbedder) -> None:
        content = _words(80)
        _make_note(vault, "note.md", content)
        build_index(vault, store)
        run_embedding_phase(vault, store, embedder)
        row = store.conn.execute(
            "SELECT embedded_sha256 FROM chunks WHERE note_relpath = ? AND chunk_index = 0",
            ["note.md"],
        ).fetchone()
        assert row is not None
        assert row[0] == _sha256(content)


# ---------------------------------------------------------------------------
# Incremental: unchanged notes are skipped
# ---------------------------------------------------------------------------

class TestIncrementalSkipping:
    def test_second_run_skips_unchanged_notes(self, vault: Path, store: IndexStore, embedder: FakeEmbedder) -> None:
        _make_note(vault, "note.md", _words(80))
        build_index(vault, store)
        run_embedding_phase(vault, store, embedder)
        call_count_after_first = embedder.call_count

        # Second run: nothing changed
        build_index(vault, store)
        stats = run_embedding_phase(vault, store, embedder)

        assert stats.notes_processed == 0
        assert stats.notes_skipped == 1
        assert embedder.call_count == call_count_after_first  # no new embed calls

    def test_chunks_unchanged_on_second_run(self, vault: Path, store: IndexStore, embedder: FakeEmbedder) -> None:
        _make_note(vault, "note.md", _words(80))
        build_index(vault, store)
        run_embedding_phase(vault, store, embedder)
        count_after_first = _chunk_count(store)

        build_index(vault, store)
        run_embedding_phase(vault, store, embedder)

        assert _chunk_count(store) == count_after_first


# ---------------------------------------------------------------------------
# Changed notes are re-embedded
# ---------------------------------------------------------------------------

class TestChangedNotesReembedded:
    def test_changed_note_is_reprocessed(self, vault: Path, store: IndexStore, embedder: FakeEmbedder) -> None:
        note = _make_note(vault, "note.md", _words(80))
        build_index(vault, store)
        run_embedding_phase(vault, store, embedder)
        call_count_after_first = embedder.call_count

        # Modify the note
        note.write_text(_words(80, "changed"), encoding="utf-8")
        build_index(vault, store)
        stats = run_embedding_phase(vault, store, embedder)

        assert stats.notes_processed == 1
        assert embedder.call_count > call_count_after_first

    def test_changed_note_embedded_sha256_updated(self, vault: Path, store: IndexStore, embedder: FakeEmbedder) -> None:
        note = _make_note(vault, "note.md", _words(80))
        build_index(vault, store)
        run_embedding_phase(vault, store, embedder)

        new_content = _words(80, "updated")
        note.write_text(new_content, encoding="utf-8")
        build_index(vault, store)
        run_embedding_phase(vault, store, embedder)

        row = store.conn.execute(
            "SELECT embedded_sha256 FROM chunks WHERE note_relpath = ? AND chunk_index = 0",
            ["note.md"],
        ).fetchone()
        assert row[0] == _sha256(new_content)

    def test_note_intelligence_cleared_on_reembed(self, vault: Path, store: IndexStore, embedder: FakeEmbedder) -> None:
        note = _make_note(vault, "note.md", _words(80))
        build_index(vault, store)
        run_embedding_phase(vault, store, embedder)

        # Manually insert a stale note_intelligence row
        store.conn.execute(
            "INSERT INTO note_intelligence (note_relpath, summary, extracted_at, model_version) "
            "VALUES (?, ?, NOW(), 'test')",
            ["note.md", "old summary"],
        )
        assert store.conn.execute(
            "SELECT count(*) FROM note_intelligence WHERE note_relpath = 'note.md'"
        ).fetchone()[0] == 1

        # Change note and re-embed
        note.write_text(_words(80, "new"), encoding="utf-8")
        build_index(vault, store)
        run_embedding_phase(vault, store, embedder)

        assert store.conn.execute(
            "SELECT count(*) FROM note_intelligence WHERE note_relpath = 'note.md'"
        ).fetchone()[0] == 0


# ---------------------------------------------------------------------------
# Deleted note chunks removed
# ---------------------------------------------------------------------------

class TestDeletedNoteCleanup:
    def test_deleted_note_chunks_removed_by_build_index(
        self, vault: Path, store: IndexStore, embedder: FakeEmbedder
    ) -> None:
        note = _make_note(vault, "note.md", _words(80))
        build_index(vault, store)
        run_embedding_phase(vault, store, embedder)
        assert _chunk_count(store, "note.md") >= 1

        # Delete note from vault
        note.unlink()
        build_index(vault, store)

        # build_index should have cleared semantic data for deleted note
        assert _chunk_count(store, "note.md") == 0
        assert _embedding_count(store, "note.md") == 0

    def test_deleted_note_not_reembedded(
        self, vault: Path, store: IndexStore, embedder: FakeEmbedder
    ) -> None:
        note = _make_note(vault, "note.md", _words(80))
        build_index(vault, store)
        run_embedding_phase(vault, store, embedder)

        note.unlink()
        build_index(vault, store)
        stats = run_embedding_phase(vault, store, embedder)

        assert stats.notes_processed == 0


# ---------------------------------------------------------------------------
# Short notes below MIN_TOKENS
# ---------------------------------------------------------------------------

class TestShortNotes:
    def test_short_note_produces_no_chunks(self, vault: Path, store: IndexStore, embedder: FakeEmbedder) -> None:
        _make_note(vault, "short.md", "Just a few words.")
        build_index(vault, store)
        stats = run_embedding_phase(vault, store, embedder)
        assert stats.chunks_generated == 0
        assert _chunk_count(store, "short.md") == 0
        # Note is still counted as processed (no chunks to embed)
        assert stats.notes_processed == 1

"""Tests for the intelligence phase (concept/entity extraction)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from dataclasses import dataclass

import pytest

from obsidian_agent.index.build_index import build_index
from obsidian_agent.index.semantic import (
    _build_extraction_prompt,
    _extract_json,
    run_embedding_phase,
    run_intelligence_phase,
)
from obsidian_agent.index.store import IndexStore

from tests.test_semantic_index import FakeEmbedder, _make_note, _words


# ---------------------------------------------------------------------------
# Fake worker
# ---------------------------------------------------------------------------

@dataclass
class FakeWorkerResult:
    returncode: int
    output: str
    stderr: str = ""


class FakeWorker:
    """Returns a configurable response. Tracks calls for assertions."""

    def __init__(self, response: dict | None = None, returncode: int = 0, raw: str = "") -> None:
        self._response = response
        self._returncode = returncode
        self._raw = raw
        self.calls: list[str] = []

    def run(self, prompt: str, *, web_search: bool, with_mcp: bool) -> FakeWorkerResult:
        self.calls.append(prompt)
        if self._returncode != 0:
            return FakeWorkerResult(returncode=self._returncode, output="", stderr="error")
        if self._raw:
            return FakeWorkerResult(returncode=0, output=self._raw)
        return FakeWorkerResult(
            returncode=0,
            output=json.dumps(self._response) if self._response else "",
        )


_SAMPLE_RESPONSE = {
    "summary": "This note discusses machine learning and neural networks.",
    "concepts": [
        {"name": "machine learning", "salience": 0.9},
        {"name": "neural networks", "salience": 0.7},
    ],
    "entities": [
        {"name": "PyTorch", "type": "tool"},
        {"name": "Yann LeCun", "type": "person"},
    ],
    "implicit_items": [
        {"type": "idea", "text": "Explore attention mechanisms further", "chunk_index": 0},
        {"type": "question", "text": "Why does dropout work so well?", "chunk_index": 0},
    ],
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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


def _setup_embedded_note(vault: Path, store: IndexStore, embedder: FakeEmbedder, filename: str = "note.md") -> None:
    """Create a note, build the structural index, and run the embedding phase."""
    _make_note(vault, filename, _words(80))
    build_index(vault, store)
    run_embedding_phase(vault, store, embedder)


# ---------------------------------------------------------------------------
# JSON extraction helper
# ---------------------------------------------------------------------------

class TestExtractJson:
    def test_plain_json(self) -> None:
        text = '{"summary": "test", "concepts": []}'
        result = _extract_json(text)
        assert result == {"summary": "test", "concepts": []}

    def test_json_with_preamble(self) -> None:
        text = 'Here is the analysis:\n\n{"summary": "hello", "concepts": []}\n\nDone.'
        result = _extract_json(text)
        assert result is not None
        assert result["summary"] == "hello"

    def test_returns_none_for_no_json(self) -> None:
        assert _extract_json("no json here") is None

    def test_returns_none_for_invalid_json(self) -> None:
        assert _extract_json("{ invalid json }") is None


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------

class TestBuildExtractionPrompt:
    def test_includes_note_path(self) -> None:
        prompt = _build_extraction_prompt("folder/note.md", ["chunk 1", "chunk 2"])
        assert "folder/note.md" in prompt

    def test_includes_chunk_texts(self) -> None:
        prompt = _build_extraction_prompt("note.md", ["alpha content", "beta content"])
        assert "alpha content" in prompt
        assert "beta content" in prompt

    def test_includes_json_schema(self) -> None:
        prompt = _build_extraction_prompt("note.md", ["text"])
        assert "summary" in prompt
        assert "concepts" in prompt
        assert "entities" in prompt
        assert "implicit_items" in prompt


# ---------------------------------------------------------------------------
# Concepts stored correctly
# ---------------------------------------------------------------------------

class TestConceptsStored:
    def test_concepts_inserted(self, vault: Path, store: IndexStore, embedder: FakeEmbedder) -> None:
        _setup_embedded_note(vault, store, embedder)
        worker = FakeWorker(response=_SAMPLE_RESPONSE)
        run_intelligence_phase(store, worker)
        count = store.conn.execute("SELECT count(*) FROM concepts").fetchone()[0]
        assert count == 2

    def test_concept_names_stored(self, vault: Path, store: IndexStore, embedder: FakeEmbedder) -> None:
        _setup_embedded_note(vault, store, embedder)
        worker = FakeWorker(response=_SAMPLE_RESPONSE)
        run_intelligence_phase(store, worker)
        names = {row[0] for row in store.conn.execute("SELECT name FROM concepts").fetchall()}
        assert "machine learning" in names
        assert "neural networks" in names

    def test_chunk_concepts_inserted(self, vault: Path, store: IndexStore, embedder: FakeEmbedder) -> None:
        _setup_embedded_note(vault, store, embedder)
        worker = FakeWorker(response=_SAMPLE_RESPONSE)
        run_intelligence_phase(store, worker)
        count = store.conn.execute("SELECT count(*) FROM chunk_concepts").fetchone()[0]
        assert count == 2


# ---------------------------------------------------------------------------
# Entities stored correctly
# ---------------------------------------------------------------------------

class TestEntitiesStored:
    def test_entities_inserted(self, vault: Path, store: IndexStore, embedder: FakeEmbedder) -> None:
        _setup_embedded_note(vault, store, embedder)
        worker = FakeWorker(response=_SAMPLE_RESPONSE)
        run_intelligence_phase(store, worker)
        count = store.conn.execute("SELECT count(*) FROM entities").fetchone()[0]
        assert count == 2

    def test_entity_types_stored(self, vault: Path, store: IndexStore, embedder: FakeEmbedder) -> None:
        _setup_embedded_note(vault, store, embedder)
        worker = FakeWorker(response=_SAMPLE_RESPONSE)
        run_intelligence_phase(store, worker)
        rows = {row for row in store.conn.execute("SELECT name, type FROM entities").fetchall()}
        assert ("PyTorch", "tool") in rows
        assert ("Yann LeCun", "person") in rows


# ---------------------------------------------------------------------------
# Implicit items stored
# ---------------------------------------------------------------------------

class TestImplicitItemsStored:
    def test_implicit_items_inserted(self, vault: Path, store: IndexStore, embedder: FakeEmbedder) -> None:
        _setup_embedded_note(vault, store, embedder)
        worker = FakeWorker(response=_SAMPLE_RESPONSE)
        run_intelligence_phase(store, worker)
        count = store.conn.execute("SELECT count(*) FROM implicit_items").fetchone()[0]
        assert count == 2

    def test_implicit_item_types(self, vault: Path, store: IndexStore, embedder: FakeEmbedder) -> None:
        _setup_embedded_note(vault, store, embedder)
        worker = FakeWorker(response=_SAMPLE_RESPONSE)
        run_intelligence_phase(store, worker)
        types = {row[0] for row in store.conn.execute("SELECT type FROM implicit_items").fetchall()}
        assert "idea" in types
        assert "question" in types


# ---------------------------------------------------------------------------
# Note intelligence stored
# ---------------------------------------------------------------------------

class TestNoteIntelligenceStored:
    def test_summary_stored(self, vault: Path, store: IndexStore, embedder: FakeEmbedder) -> None:
        _setup_embedded_note(vault, store, embedder)
        worker = FakeWorker(response=_SAMPLE_RESPONSE)
        run_intelligence_phase(store, worker)
        row = store.conn.execute(
            "SELECT summary FROM note_intelligence WHERE note_relpath = 'note.md'"
        ).fetchone()
        assert row is not None
        assert "machine learning" in row[0]

    def test_model_version_stored(self, vault: Path, store: IndexStore, embedder: FakeEmbedder) -> None:
        _setup_embedded_note(vault, store, embedder)
        worker = FakeWorker(response=_SAMPLE_RESPONSE)
        run_intelligence_phase(store, worker, model_version="test-model")
        row = store.conn.execute(
            "SELECT model_version FROM note_intelligence WHERE note_relpath = 'note.md'"
        ).fetchone()
        assert row[0] == "test-model"


# ---------------------------------------------------------------------------
# Idempotency: re-running replaces, not duplicates
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_rerun_does_not_duplicate_concepts(
        self, vault: Path, store: IndexStore, embedder: FakeEmbedder
    ) -> None:
        _setup_embedded_note(vault, store, embedder)
        worker = FakeWorker(response=_SAMPLE_RESPONSE)
        run_intelligence_phase(store, worker)

        # Delete note_intelligence to force a re-run
        store.conn.execute("DELETE FROM note_intelligence WHERE note_relpath = 'note.md'")
        run_intelligence_phase(store, worker)

        count = store.conn.execute("SELECT count(*) FROM concepts").fetchone()[0]
        assert count == 2  # not 4

    def test_rerun_replaces_implicit_items(
        self, vault: Path, store: IndexStore, embedder: FakeEmbedder
    ) -> None:
        _setup_embedded_note(vault, store, embedder)
        worker = FakeWorker(response=_SAMPLE_RESPONSE)
        run_intelligence_phase(store, worker)

        store.conn.execute("DELETE FROM note_intelligence WHERE note_relpath = 'note.md'")
        run_intelligence_phase(store, worker)

        count = store.conn.execute(
            "SELECT count(*) FROM implicit_items WHERE note_relpath = 'note.md'"
        ).fetchone()[0]
        assert count == 2  # not 4


# ---------------------------------------------------------------------------
# Worker errors are skipped gracefully
# ---------------------------------------------------------------------------

class TestWorkerErrors:
    def test_nonzero_exit_skips_note(
        self, vault: Path, store: IndexStore, embedder: FakeEmbedder
    ) -> None:
        _setup_embedded_note(vault, store, embedder)
        worker = FakeWorker(returncode=1)
        stats = run_intelligence_phase(store, worker)
        assert stats.notes_failed == 1
        assert stats.notes_processed == 0
        assert store.conn.execute("SELECT count(*) FROM note_intelligence").fetchone()[0] == 0

    def test_invalid_json_skips_note(
        self, vault: Path, store: IndexStore, embedder: FakeEmbedder
    ) -> None:
        _setup_embedded_note(vault, store, embedder)
        worker = FakeWorker(raw="Sorry, I cannot process this request.")
        stats = run_intelligence_phase(store, worker)
        assert stats.notes_failed == 1
        assert stats.notes_processed == 0

    def test_one_failure_does_not_block_others(
        self, vault: Path, store: IndexStore, embedder: FakeEmbedder
    ) -> None:
        _make_note(vault, "fail.md", _words(80))
        _make_note(vault, "pass.md", _words(80))
        build_index(vault, store)
        run_embedding_phase(vault, store, embedder)

        call_count = 0
        def _side_effect(prompt, *, web_search, with_mcp):
            nonlocal call_count
            call_count += 1
            if "fail.md" in prompt:
                return FakeWorkerResult(returncode=1, output="", stderr="boom")
            return FakeWorkerResult(returncode=0, output=json.dumps(_SAMPLE_RESPONSE))

        class _SelectiveWorker:
            def run(self, prompt, *, web_search, with_mcp):
                return _side_effect(prompt, web_search=web_search, with_mcp=with_mcp)

        stats = run_intelligence_phase(store, _SelectiveWorker())
        assert stats.notes_processed == 1
        assert stats.notes_failed == 1


# ---------------------------------------------------------------------------
# Incremental: notes already processed are skipped
# ---------------------------------------------------------------------------

class TestIncrementalSkipping:
    def test_second_run_skips_already_processed(
        self, vault: Path, store: IndexStore, embedder: FakeEmbedder
    ) -> None:
        _setup_embedded_note(vault, store, embedder)
        worker = FakeWorker(response=_SAMPLE_RESPONSE)
        run_intelligence_phase(store, worker)
        first_call_count = len(worker.calls)

        stats = run_intelligence_phase(store, worker)
        assert stats.notes_processed == 0
        assert stats.notes_skipped >= 1
        assert len(worker.calls) == first_call_count  # no new calls


# ---------------------------------------------------------------------------
# max_notes_per_run throttling
# ---------------------------------------------------------------------------

class TestMaxNotesPerRun:
    def test_max_notes_limits_processing(
        self, vault: Path, store: IndexStore, embedder: FakeEmbedder
    ) -> None:
        for i in range(5):
            _make_note(vault, f"note{i}.md", _words(80))
        build_index(vault, store)
        run_embedding_phase(vault, store, embedder)

        worker = FakeWorker(response=_SAMPLE_RESPONSE)
        stats = run_intelligence_phase(store, worker, max_notes_per_run=2)
        assert stats.notes_processed == 2
        assert len(worker.calls) == 2

"""Tests for index/semantic_queries.py — populates fixture data without LLM or embedder."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from obsidian_agent.index.semantic_queries import (
    ChunkResult,
    ConceptSummary,
    ImplicitItem,
    find_related_notes,
    find_unformalized_tasks,
    find_unlinked_related_notes,
    get_entity_context,
    get_implicit_items,
    get_older_notes_by_concepts,
    get_recent_concepts,
    list_concepts,
    search_by_concept,
)
from obsidian_agent.index.store import IndexStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def store(tmp_path: Path) -> IndexStore:
    s = IndexStore(tmp_path / "index.duckdb")
    yield s
    s.close()


def _insert_note(conn, relpath: str, mtime_ns: int = 0) -> None:
    conn.execute(
        "INSERT INTO notes (note_relpath, title, is_daily_note, mtime_ns, size_bytes, content_sha256, word_count) "
        "VALUES (?, ?, false, ?, 100, 'abc', 100)",
        [relpath, relpath, mtime_ns],
    )


def _insert_chunk(conn, note_relpath: str, chunk_index: int = 0, text: str = "chunk text") -> str:
    chunk_id = f"{note_relpath}:{chunk_index}"
    conn.execute(
        "INSERT INTO chunks (id, note_relpath, chunk_index, section_header, text, token_count) "
        "VALUES (?, ?, ?, NULL, ?, 100)",
        [chunk_id, note_relpath, chunk_index, text],
    )
    return chunk_id


def _insert_concept(conn, concept_id: int, name: str) -> None:
    conn.execute("INSERT INTO concepts (id, name) VALUES (?, ?)", [concept_id, name])


def _insert_entity(conn, entity_id: int, name: str, entity_type: str) -> None:
    conn.execute(
        "INSERT INTO entities (id, name, type) VALUES (?, ?, ?)",
        [entity_id, name, entity_type],
    )


def _link_chunk_concept(conn, chunk_id: str, concept_id: int, salience: float = 0.8) -> None:
    conn.execute(
        "INSERT INTO chunk_concepts (chunk_id, concept_id, salience) VALUES (?, ?, ?)",
        [chunk_id, concept_id, salience],
    )


def _link_chunk_entity(conn, chunk_id: str, entity_id: int) -> None:
    conn.execute(
        "INSERT INTO chunk_entities (chunk_id, entity_id, context_snippet) VALUES (?, ?, NULL)",
        [chunk_id, entity_id],
    )


def _insert_implicit_item(
    conn, note_relpath: str, chunk_id: str, item_type: str, text: str, item_id: int
) -> None:
    conn.execute(
        "INSERT INTO implicit_items (id, chunk_id, note_relpath, type, text, extracted_at) "
        "VALUES (?, ?, ?, ?, ?, NOW())",
        [item_id, chunk_id, note_relpath, item_type, text],
    )


@pytest.fixture()
def populated(store: IndexStore) -> IndexStore:
    """Insert a small semantic fixture: 3 notes, 3 concepts, 2 entities, 2 implicit items."""
    conn = store.conn
    now_ns = int(time.time() * 1e9)
    old_ns = int((time.time() - 30 * 86400) * 1e9)  # 30 days ago

    # Notes
    _insert_note(conn, "recent.md", mtime_ns=now_ns)
    _insert_note(conn, "old_a.md", mtime_ns=old_ns)
    _insert_note(conn, "old_b.md", mtime_ns=old_ns)

    # Chunks
    c_recent = _insert_chunk(conn, "recent.md", 0, "Machine learning trends in 2026.")
    c_old_a = _insert_chunk(conn, "old_a.md", 0, "Neural networks and deep learning.")
    c_old_b = _insert_chunk(conn, "old_b.md", 0, "Transformers and attention mechanisms.")

    # Concepts: machine-learning (1), neural-networks (2), transformers (3)
    _insert_concept(conn, 1, "machine learning")
    _insert_concept(conn, 2, "neural networks")
    _insert_concept(conn, 3, "transformers")

    # Concept associations
    _link_chunk_concept(conn, c_recent, 1, 0.9)   # recent ↔ machine-learning
    _link_chunk_concept(conn, c_old_a, 1, 0.7)    # old_a  ↔ machine-learning (shared!)
    _link_chunk_concept(conn, c_old_a, 2, 0.8)    # old_a  ↔ neural-networks
    _link_chunk_concept(conn, c_old_b, 3, 0.6)    # old_b  ↔ transformers

    # Entities
    _insert_entity(conn, 1, "PyTorch", "tool")
    _insert_entity(conn, 2, "Yann LeCun", "person")
    _link_chunk_entity(conn, c_old_a, 1)
    _link_chunk_entity(conn, c_old_a, 2)

    # Implicit items
    _insert_implicit_item(conn, "recent.md", c_recent, "idea", "Explore attention further", 1)
    _insert_implicit_item(conn, "old_a.md", c_old_a, "task", "Email team about results", 2)

    return store


# ---------------------------------------------------------------------------
# list_concepts
# ---------------------------------------------------------------------------

class TestListConcepts:
    def test_returns_concepts(self, populated: IndexStore) -> None:
        results = list_concepts(populated.conn)
        names = [c.name for c in results]
        assert "machine learning" in names

    def test_concept_note_count(self, populated: IndexStore) -> None:
        results = list_concepts(populated.conn)
        ml = next(c for c in results if c.name == "machine learning")
        assert ml.note_count == 2  # appears in recent.md and old_a.md

    def test_returns_typed_dataclass(self, populated: IndexStore) -> None:
        results = list_concepts(populated.conn)
        assert all(isinstance(c, ConceptSummary) for c in results)

    def test_empty_db_returns_empty(self, store: IndexStore) -> None:
        assert list_concepts(store.conn) == []

    def test_respects_n_limit(self, populated: IndexStore) -> None:
        results = list_concepts(populated.conn, n=1)
        assert len(results) == 1


# ---------------------------------------------------------------------------
# search_by_concept
# ---------------------------------------------------------------------------

class TestSearchByConcept:
    def test_finds_chunks_for_concept(self, populated: IndexStore) -> None:
        results = search_by_concept(populated.conn, "machine learning")
        assert len(results) == 2

    def test_returns_typed_chunk_result(self, populated: IndexStore) -> None:
        results = search_by_concept(populated.conn, "machine learning")
        assert all(isinstance(r, ChunkResult) for r in results)

    def test_unknown_concept_returns_empty(self, populated: IndexStore) -> None:
        assert search_by_concept(populated.conn, "quantum computing") == []

    def test_result_contains_text(self, populated: IndexStore) -> None:
        results = search_by_concept(populated.conn, "machine learning")
        texts = {r.text for r in results}
        assert any("Machine learning" in t or "Neural networks" in t for t in texts)


# ---------------------------------------------------------------------------
# find_related_notes
# ---------------------------------------------------------------------------

class TestFindRelatedNotes:
    def test_finds_related_by_shared_concept(self, populated: IndexStore) -> None:
        results = find_related_notes(populated.conn, "recent.md")
        related_paths = [r[0] for r in results]
        assert "old_a.md" in related_paths  # shares "machine learning"

    def test_does_not_include_self(self, populated: IndexStore) -> None:
        results = find_related_notes(populated.conn, "recent.md")
        assert all(r[0] != "recent.md" for r in results)

    def test_overlap_score_is_positive(self, populated: IndexStore) -> None:
        results = find_related_notes(populated.conn, "recent.md")
        assert all(r[1] > 0 for r in results)

    def test_no_shared_concepts_returns_empty(self, populated: IndexStore) -> None:
        # old_b.md only has "transformers"; recent.md doesn't
        results = find_related_notes(populated.conn, "old_b.md")
        # Should not include recent.md or old_a.md (no shared concepts with old_b)
        # (old_b only has transformers; neither recent nor old_a has transformers)
        assert all(r[0] not in {"recent.md", "old_a.md"} for r in results)


# ---------------------------------------------------------------------------
# get_recent_concepts
# ---------------------------------------------------------------------------

class TestGetRecentConcepts:
    def test_finds_concepts_in_recent_notes(self, populated: IndexStore) -> None:
        # recent.md has "machine learning" and was modified just now
        results = get_recent_concepts(populated.conn, since_days=1)
        names = [c.name for c in results]
        assert "machine learning" in names

    def test_excludes_old_note_concepts(self, populated: IndexStore) -> None:
        # "neural networks" only appears in old_a.md (30 days ago)
        results = get_recent_concepts(populated.conn, since_days=1)
        names = [c.name for c in results]
        assert "neural networks" not in names

    def test_empty_when_no_recent_notes(self, populated: IndexStore) -> None:
        # Use a window of 0 days — no notes match
        results = get_recent_concepts(populated.conn, since_days=0)
        assert results == []


# ---------------------------------------------------------------------------
# get_older_notes_by_concepts
# ---------------------------------------------------------------------------

class TestGetOlderNotesByConcepts:
    def test_finds_old_notes_with_matching_concept(self, populated: IndexStore) -> None:
        results = get_older_notes_by_concepts(
            populated.conn, ["machine learning"], newer_than_days=7
        )
        paths = [r[0] for r in results]
        assert "old_a.md" in paths  # old, has machine learning

    def test_excludes_recent_notes(self, populated: IndexStore) -> None:
        results = get_older_notes_by_concepts(
            populated.conn, ["machine learning"], newer_than_days=7
        )
        paths = [r[0] for r in results]
        assert "recent.md" not in paths

    def test_empty_concept_list_returns_empty(self, populated: IndexStore) -> None:
        assert get_older_notes_by_concepts(populated.conn, [], newer_than_days=7) == []


# ---------------------------------------------------------------------------
# get_entity_context
# ---------------------------------------------------------------------------

class TestGetEntityContext:
    def test_finds_chunks_for_entity(self, populated: IndexStore) -> None:
        results = get_entity_context(populated.conn, "PyTorch")
        assert len(results) == 1
        assert results[0].note_relpath == "old_a.md"

    def test_unknown_entity_returns_empty(self, populated: IndexStore) -> None:
        assert get_entity_context(populated.conn, "Unknown Person") == []

    def test_returns_chunk_result_type(self, populated: IndexStore) -> None:
        results = get_entity_context(populated.conn, "Yann LeCun")
        assert all(isinstance(r, ChunkResult) for r in results)


# ---------------------------------------------------------------------------
# get_implicit_items
# ---------------------------------------------------------------------------

class TestGetImplicitItems:
    def test_returns_all_items_unfiltered(self, populated: IndexStore) -> None:
        results = get_implicit_items(populated.conn)
        assert len(results) == 2

    def test_filter_by_type(self, populated: IndexStore) -> None:
        ideas = get_implicit_items(populated.conn, item_type="idea")
        assert all(i.type == "idea" for i in ideas)
        assert len(ideas) == 1

    def test_filter_by_note(self, populated: IndexStore) -> None:
        items = get_implicit_items(populated.conn, note_relpath="recent.md")
        assert all(i.note_relpath == "recent.md" for i in items)

    def test_returns_implicit_item_type(self, populated: IndexStore) -> None:
        results = get_implicit_items(populated.conn)
        assert all(isinstance(i, ImplicitItem) for i in results)

    def test_empty_db_returns_empty(self, store: IndexStore) -> None:
        assert get_implicit_items(store.conn) == []


# ---------------------------------------------------------------------------
# find_unformalized_tasks
# ---------------------------------------------------------------------------

class TestFindUnformalizedTasks:
    def test_returns_task_type_implicit_items(self, populated: IndexStore) -> None:
        results = find_unformalized_tasks(populated.conn)
        # "Email team about results" is a task-type implicit item with no formal task
        assert any(i.text == "Email team about results" for i in results)

    def test_returns_empty_when_no_implicit_tasks(self, store: IndexStore) -> None:
        assert find_unformalized_tasks(store.conn) == []


# ---------------------------------------------------------------------------
# find_unlinked_related_notes
# ---------------------------------------------------------------------------

class TestFindUnlinkedRelatedNotes:
    def test_finds_pairs_with_shared_concepts(self, populated: IndexStore) -> None:
        results = find_unlinked_related_notes(populated.conn, min_score=0.1)
        pairs = [(r[0], r[1]) for r in results]
        assert ("old_a.md", "recent.md") in pairs or ("recent.md", "old_a.md") in pairs

    def test_returns_float_score(self, populated: IndexStore) -> None:
        results = find_unlinked_related_notes(populated.conn, min_score=0.1)
        assert all(isinstance(r[2], float) for r in results)

    def test_empty_when_no_shared_concepts(self, store: IndexStore) -> None:
        assert find_unlinked_related_notes(store.conn) == []

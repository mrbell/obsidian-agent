"""Incremental semantic indexing — embedding and intelligence phases.

The embedding phase (run_embedding_phase) chunks changed notes, generates
vector embeddings, and stores results in DuckDB.

The intelligence phase (run_intelligence_phase) calls a Claude Code worker
for each note with missing/stale note_intelligence to extract concepts,
entities, implicit items, and a prose summary.

Both phases are orchestrated by run_semantic_index(), invoked via the
``obsidian-agent index-semantic`` CLI command.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from obsidian_agent.agent.base import AgentWorker
from obsidian_agent.embeddings.base import Embedder
from obsidian_agent.index.chunker import chunk_note
from obsidian_agent.index.store import IndexStore

_log = logging.getLogger(__name__)

# Default model version tag stored in note_intelligence.model_version
_DEFAULT_MODEL_VERSION = "claude/claude-sonnet-4-6"

# Regex to locate the outermost JSON object in worker output
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@dataclass
class EmbeddingStats:
    notes_processed: int = 0   # notes that were re-chunked and re-embedded
    notes_skipped: int = 0     # notes already up to date
    chunks_generated: int = 0  # total chunks produced
    chunks_embedded: int = 0   # embeddings stored in chunk_embeddings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_stale_notes(store: IndexStore) -> list[tuple[str, str]]:
    """Return (note_relpath, content_sha256) for notes needing re-embedding.

    A note is stale when:
    - It has no rows in ``chunks`` (new note), or
    - Any of its chunks has ``embedded_sha256 != notes.content_sha256``
      (content changed since last embedding run).

    We check staleness via the chunk at index 0 as a proxy for all chunks;
    the embedding phase always replaces all chunks together.
    """
    # Load all notes indexed by the structural indexer
    notes: dict[str, str] = {
        row[0]: row[1]
        for row in store.conn.execute(
            "SELECT note_relpath, content_sha256 FROM notes"
        ).fetchall()
    }

    # Find which notes have an up-to-date embedding (check chunk 0)
    up_to_date: set[str] = set()
    for row in store.conn.execute(
        "SELECT note_relpath, embedded_sha256 FROM chunks WHERE chunk_index = 0"
    ).fetchall():
        relpath, embedded_sha = row[0], row[1]
        if relpath in notes and embedded_sha == notes[relpath]:
            up_to_date.add(relpath)

    return [
        (relpath, sha256)
        for relpath, sha256 in notes.items()
        if relpath not in up_to_date
    ]


def _clear_note_semantic_data(store: IndexStore, note_relpath: str) -> None:
    """Delete all semantic index rows for a note."""
    conn = store.conn
    chunk_ids = [
        row[0]
        for row in conn.execute(
            "SELECT id FROM chunks WHERE note_relpath = ?", [note_relpath]
        ).fetchall()
    ]
    for cid in chunk_ids:
        conn.execute("DELETE FROM chunk_embeddings WHERE chunk_id = ?", [cid])
        conn.execute("DELETE FROM chunk_concepts WHERE chunk_id = ?", [cid])
        conn.execute("DELETE FROM chunk_entities WHERE chunk_id = ?", [cid])
    conn.execute("DELETE FROM implicit_items WHERE note_relpath = ?", [note_relpath])
    conn.execute("DELETE FROM chunks WHERE note_relpath = ?", [note_relpath])
    conn.execute("DELETE FROM note_intelligence WHERE note_relpath = ?", [note_relpath])


def _embed_note(
    vault_path: Path,
    note_relpath: str,
    content_sha256: str,
    store: IndexStore,
    embedder: Embedder,
) -> int:
    """Chunk, embed, and persist one note. Returns the number of chunks stored.

    Clears any existing semantic data for the note before inserting fresh rows.
    If the note file no longer exists on disk (concurrent deletion), returns 0.
    """
    abs_path = vault_path / note_relpath
    if not abs_path.exists():
        _log.warning("Note not found on disk, skipping embed: %s", note_relpath)
        return 0

    content = abs_path.read_text(encoding="utf-8")
    chunks = chunk_note(note_relpath, content)

    _clear_note_semantic_data(store, note_relpath)

    if not chunks:
        return 0

    texts = [c.text for c in chunks]
    vectors = embedder.embed(texts)
    now = datetime.now(timezone.utc)
    conn = store.conn

    for chunk, vector in zip(chunks, vectors):
        chunk_id = f"{note_relpath}:{chunk.chunk_index}"
        conn.execute(
            """INSERT INTO chunks
               (id, note_relpath, chunk_index, section_header, text,
                token_count, embedded_sha256, embedded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                chunk_id,
                note_relpath,
                chunk.chunk_index,
                chunk.section_header,
                chunk.text,
                chunk.token_count,
                content_sha256,
                now,
            ],
        )
        conn.execute(
            "INSERT INTO chunk_embeddings (chunk_id, embedding) VALUES (?, ?)",
            [chunk_id, vector],
        )

    return len(chunks)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_embedding_phase(
    vault_path: Path,
    store: IndexStore,
    embedder: Embedder,
) -> EmbeddingStats:
    """Incrementally embed changed notes.

    Runs inside a single transaction. Stale notes are re-chunked and
    re-embedded; up-to-date notes are skipped entirely.
    """
    stats = EmbeddingStats()
    stale = _find_stale_notes(store)
    total_notes = store.conn.execute("SELECT count(*) FROM notes").fetchone()[0]
    stats.notes_skipped = total_notes - len(stale)

    if not stale:
        _log.info("Embedding phase: all %d notes up to date", total_notes)
        return stats

    _log.info(
        "Embedding phase: %d stale note(s) to process out of %d total",
        len(stale), total_notes,
    )

    conn = store.conn
    conn.execute("BEGIN TRANSACTION")
    try:
        for note_relpath, content_sha256 in stale:
            n = _embed_note(vault_path, note_relpath, content_sha256, store, embedder)
            stats.notes_processed += 1
            stats.chunks_generated += n
            stats.chunks_embedded += n
            _log.debug("Embedded %s: %d chunk(s)", note_relpath, n)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    _log.info(
        "Embedding phase complete: processed=%d skipped=%d chunks=%d",
        stats.notes_processed, stats.notes_skipped, stats.chunks_embedded,
    )
    return stats


# ---------------------------------------------------------------------------
# Intelligence phase stats
# ---------------------------------------------------------------------------

@dataclass
class IntelligenceStats:
    notes_processed: int = 0   # notes successfully extracted
    notes_skipped: int = 0     # notes already have intelligence
    notes_failed: int = 0      # worker errors or parse failures


# ---------------------------------------------------------------------------
# Intelligence phase helpers
# ---------------------------------------------------------------------------

def _find_notes_needing_intelligence(store: IndexStore) -> list[str]:
    """Return note_relpaths that have chunks but no note_intelligence row."""
    rows = store.conn.execute(
        """
        SELECT n.note_relpath
        FROM notes n
        WHERE NOT EXISTS (
            SELECT 1 FROM note_intelligence ni WHERE ni.note_relpath = n.note_relpath
        )
        AND EXISTS (
            SELECT 1 FROM chunks c WHERE c.note_relpath = n.note_relpath
        )
        ORDER BY n.note_relpath
        """
    ).fetchall()
    return [row[0] for row in rows]


def _build_extraction_prompt(note_relpath: str, chunk_texts: list[str]) -> str:
    separator = "\n---\n"
    content_block = separator.join(chunk_texts)
    return (
        f"You are analyzing a note from a personal Obsidian knowledge base.\n"
        f"Note path: {note_relpath}\n\n"
        f"Content (by paragraph):\n"
        f"---\n{content_block}\n---\n\n"
        'Extract the following. Respond ONLY with valid JSON matching this schema — no preamble.\n\n'
        '{\n'
        '  "summary": "2-4 sentence summary of what this note is about.",\n'
        '  "concepts": [\n'
        '    {"name": "concept name (lowercase)", "salience": 0.0, "chunk_index": 0}\n'
        '  ],\n'
        '  "entities": [\n'
        '    {"name": "entity name", "type": "person|project|tool|book|place|other", "chunk_index": 0}\n'
        '  ],\n'
        '  "implicit_items": [\n'
        '    {"type": "idea|question|intention|task", "text": "the item text", "chunk_index": 0}\n'
        '  ]\n'
        '}\n\n'
        "Guidelines:\n"
        "- concepts: recurring topics, themes, and ideas discussed. 3-10 per note is typical.\n"
        "  salience: 1.0 = the note is primarily about this, 0.3 = mentioned in passing.\n"
        "  chunk_index: the 0-based index of the paragraph where this concept is most prominent.\n"
        "- entities: proper nouns — specific people, named projects, software tools, book titles,\n"
        "  locations. Not generic terms.\n"
        "  chunk_index: the 0-based index of the paragraph where this entity first appears.\n"
        "- implicit_items: only things not already captured as formal tasks (- [ ] ...) in the note.\n"
        "  Focus on items buried in prose. Do not invent items not present.\n"
        "- If a field would be an empty list, return []."
    )


def _extract_json(text: str) -> dict[str, Any] | None:
    """Extract the outermost JSON object from worker output text."""
    m = _JSON_OBJECT_RE.search(text)
    if not m:
        return None
    try:
        result = json.loads(m.group(0))
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass
    return None


def _get_or_create_concept(conn: Any, name: str) -> int:
    existing = conn.execute(
        "SELECT id FROM concepts WHERE name = ?", [name]
    ).fetchone()
    if existing:
        return existing[0]
    new_id = conn.execute(
        "SELECT COALESCE(MAX(id), 0) + 1 FROM concepts"
    ).fetchone()[0]
    conn.execute("INSERT INTO concepts (id, name) VALUES (?, ?)", [new_id, name])
    return new_id


def _get_or_create_entity(conn: Any, name: str, entity_type: str) -> int:
    existing = conn.execute(
        "SELECT id FROM entities WHERE name = ? AND type = ?", [name, entity_type]
    ).fetchone()
    if existing:
        return existing[0]
    new_id = conn.execute(
        "SELECT COALESCE(MAX(id), 0) + 1 FROM entities"
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO entities (id, name, type) VALUES (?, ?, ?)",
        [new_id, name, entity_type],
    )
    return new_id


def _store_extraction(
    store: IndexStore,
    note_relpath: str,
    chunk_ids: list[str],
    data: dict[str, Any],
    model_version: str,
) -> None:
    """Persist extraction results for one note inside the caller's transaction."""
    conn = store.conn
    now = datetime.now(timezone.utc)

    # --- note_intelligence ---
    conn.execute(
        """INSERT INTO note_intelligence (note_relpath, summary, extracted_at, model_version)
           VALUES (?, ?, ?, ?)
           ON CONFLICT (note_relpath) DO UPDATE SET
               summary = excluded.summary,
               extracted_at = excluded.extracted_at,
               model_version = excluded.model_version""",
        [note_relpath, data.get("summary", ""), now, model_version],
    )

    # Clear stale chunk-level data for idempotency (handles re-run without re-embed)
    for cid in chunk_ids:
        conn.execute("DELETE FROM chunk_concepts WHERE chunk_id = ?", [cid])
        conn.execute("DELETE FROM chunk_entities WHERE chunk_id = ?", [cid])
    conn.execute("DELETE FROM implicit_items WHERE note_relpath = ?", [note_relpath])

    # --- concepts ---
    n_chunks = len(chunk_ids)
    for concept in data.get("concepts", []):
        name = str(concept.get("name", "")).strip().lower()
        if not name:
            continue
        salience = float(concept.get("salience", 0.5))
        chunk_index = int(concept.get("chunk_index", 0))
        chunk_index = max(0, min(chunk_index, n_chunks - 1)) if n_chunks else 0
        chunk_id = chunk_ids[chunk_index] if chunk_ids else ""
        concept_id = _get_or_create_concept(conn, name)
        conn.execute(
            "INSERT INTO chunk_concepts (chunk_id, concept_id, salience) VALUES (?, ?, ?)"
            " ON CONFLICT (chunk_id, concept_id) DO UPDATE SET salience = excluded.salience",
            [chunk_id, concept_id, salience],
        )

    # --- entities ---
    for entity in data.get("entities", []):
        name = str(entity.get("name", "")).strip()
        entity_type = str(entity.get("type", "other")).strip()
        if not name:
            continue
        chunk_index = int(entity.get("chunk_index", 0))
        chunk_index = max(0, min(chunk_index, n_chunks - 1)) if n_chunks else 0
        chunk_id = chunk_ids[chunk_index] if chunk_ids else ""
        entity_id = _get_or_create_entity(conn, name, entity_type)
        conn.execute(
            "INSERT INTO chunk_entities (chunk_id, entity_id, context_snippet) VALUES (?, ?, ?)"
            " ON CONFLICT (chunk_id, entity_id) DO UPDATE SET context_snippet = excluded.context_snippet",
            [chunk_id, entity_id, None],
        )

    # --- implicit_items ---
    for item in data.get("implicit_items", []):
        item_type = str(item.get("type", "idea")).strip()
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        chunk_index = int(item.get("chunk_index", 0))
        # Clamp chunk_index to valid range
        chunk_index = max(0, min(chunk_index, n_chunks - 1)) if n_chunks else 0
        chunk_id = chunk_ids[chunk_index] if chunk_ids else ""
        new_id = conn.execute(
            "SELECT COALESCE(MAX(id), 0) + 1 FROM implicit_items"
        ).fetchone()[0]
        conn.execute(
            """INSERT INTO implicit_items
               (id, chunk_id, note_relpath, type, text, extracted_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [new_id, chunk_id, note_relpath, item_type, text, now],
        )


# ---------------------------------------------------------------------------
# Intelligence phase public API
# ---------------------------------------------------------------------------

def run_intelligence_phase(
    store: IndexStore,
    worker: AgentWorker,
    model_version: str = _DEFAULT_MODEL_VERSION,
    max_notes_per_run: int | None = None,
) -> IntelligenceStats:
    """Extract concepts, entities, and implicit items for notes lacking intelligence.

    Calls the Claude Code worker once per note with chunk content injected
    directly into the prompt (no MCP server needed). Stores results in a
    per-note transaction so a worker failure for one note does not affect others.
    """
    stats = IntelligenceStats()
    candidates = _find_notes_needing_intelligence(store)

    total_in_db = store.conn.execute("SELECT count(*) FROM notes").fetchone()[0]
    stats.notes_skipped = total_in_db - len(candidates)

    if max_notes_per_run is not None:
        candidates = candidates[:max_notes_per_run]

    if not candidates:
        _log.info("Intelligence phase: no notes need processing")
        return stats

    _log.info("Intelligence phase: %d note(s) to process", len(candidates))

    for i, note_relpath in enumerate(candidates):
        _log.info(
            "Intelligence phase: note %d/%d — %s",
            i + 1, len(candidates), note_relpath,
        )

        chunk_rows = store.conn.execute(
            "SELECT id, text FROM chunks WHERE note_relpath = ? ORDER BY chunk_index",
            [note_relpath],
        ).fetchall()

        if not chunk_rows:
            _log.debug("No chunks for %s; skipping", note_relpath)
            continue

        chunk_ids = [row[0] for row in chunk_rows]
        chunk_texts = [row[1] for row in chunk_rows]

        prompt = _build_extraction_prompt(note_relpath, chunk_texts)
        result = worker.run(prompt, web_search=False, with_mcp=False)

        if result.returncode != 0 or not result.output.strip():
            _log.warning(
                "Worker failed for %s: exit=%d stderr=%s",
                note_relpath, result.returncode, result.stderr[:200],
            )
            stats.notes_failed += 1
            continue

        data = _extract_json(result.output)
        if data is None:
            _log.warning(
                "Could not parse JSON from worker output for %s. output=%r",
                note_relpath, result.output[:200],
            )
            stats.notes_failed += 1
            continue

        conn = store.conn
        conn.execute("BEGIN TRANSACTION")
        try:
            _store_extraction(store, note_relpath, chunk_ids, data, model_version)
            conn.execute("COMMIT")
            stats.notes_processed += 1
        except Exception as exc:
            conn.execute("ROLLBACK")
            _log.error("Failed to store extraction for %s: %s", note_relpath, exc)
            stats.notes_failed += 1

    _log.info(
        "Intelligence phase complete: processed=%d skipped=%d failed=%d",
        stats.notes_processed, stats.notes_skipped, stats.notes_failed,
    )
    return stats


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def run_semantic_index(
    vault_path: Path,
    store: IndexStore,
    embedder: Embedder,
    worker: AgentWorker | None = None,
    model_version: str = _DEFAULT_MODEL_VERSION,
    max_notes_per_run: int | None = None,
) -> tuple[EmbeddingStats, IntelligenceStats | None]:
    """Run the full semantic index pipeline.

    1. Embedding phase: chunk and embed all stale notes.
    2. Intelligence phase: extract concepts/entities for notes with no
       note_intelligence. Only runs if a worker is provided.

    Returns (embedding_stats, intelligence_stats). intelligence_stats is None
    if no worker was supplied.
    """
    embedding_stats = run_embedding_phase(vault_path, store, embedder)

    if worker is None:
        _log.info("No agent worker configured; skipping intelligence phase.")
        return embedding_stats, None

    if model_version == _DEFAULT_MODEL_VERSION and worker.backend.model_version:
        model_version = worker.backend.model_version

    intelligence_stats = run_intelligence_phase(
        store, worker,
        model_version=model_version,
        max_notes_per_run=max_notes_per_run,
    )
    return embedding_stats, intelligence_stats

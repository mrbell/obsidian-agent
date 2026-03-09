"""Incremental semantic indexing — embedding phase.

Chunks changed notes, generates vector embeddings using a local model, and
stores results in DuckDB. Designed to run daily after the structural index.

The intelligence phase (concept/entity extraction via Claude Code) will be
added in 6-3 and called from run_semantic_index() after the embedding phase.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from obsidian_agent.embeddings.base import Embedder
from obsidian_agent.index.chunker import chunk_note
from obsidian_agent.index.store import IndexStore

_log = logging.getLogger(__name__)


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


def run_semantic_index(
    vault_path: Path,
    store: IndexStore,
    embedder: Embedder,
) -> EmbeddingStats:
    """Run the full semantic index pipeline.

    Currently runs only the embedding phase. The intelligence phase
    (concept/entity extraction) will be added in issue 6-3.
    """
    return run_embedding_phase(vault_path, store, embedder)

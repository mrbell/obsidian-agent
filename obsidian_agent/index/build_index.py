from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from obsidian_agent.index.store import IndexStore
from obsidian_agent.vault.parser import ParsedNote, parse_note
from obsidian_agent.vault.reader import iter_markdown_files, read_note


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@dataclass
class IndexStats:
    scanned: int = 0
    added: int = 0
    updated: int = 0
    renamed: int = 0
    deleted: int = 0
    unchanged: int = 0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_DERIVED_TABLES = (
    "frontmatter",
    "headings",
    "tasks",
    "links",
    "tags",
    "note_summaries",
)

_ALL_TABLES = (
    "notes",
    "frontmatter",
    "headings",
    "tasks",
    "links",
    "tags",
    "note_summaries",
    "topic_clusters",
)


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _delete_derived(store: IndexStore, note_relpath: str) -> None:
    for table in _DERIVED_TABLES:
        store.conn.execute(
            f"DELETE FROM {table} WHERE note_relpath = ?", [note_relpath]
        )


def _delete_all(store: IndexStore, note_relpath: str) -> None:
    for table in _ALL_TABLES:
        store.conn.execute(
            f"DELETE FROM {table} WHERE note_relpath = ?", [note_relpath]
        )


def _rename_in_db(store: IndexStore, old_path: str, new_path: str) -> None:
    for table in _ALL_TABLES:
        store.conn.execute(
            f"UPDATE {table} SET note_relpath = ? WHERE note_relpath = ?",
            [new_path, old_path],
        )


def _insert_derived(store: IndexStore, note_relpath: str, parsed: ParsedNote) -> None:
    conn = store.conn

    for key, value in parsed.frontmatter.items():
        conn.execute(
            "INSERT INTO frontmatter VALUES (?, ?, ?)",
            [note_relpath, key, json.dumps(value)],
        )

    for h in parsed.headings:
        conn.execute(
            "INSERT INTO headings VALUES (?, ?, ?, ?)",
            [note_relpath, h.line_no, h.level, h.text],
        )

    for t in parsed.tasks:
        conn.execute(
            "INSERT INTO tasks VALUES (?, ?, ?, ?, ?)",
            [note_relpath, t.line_no, t.status, t.text, t.due_date],
        )

    for link in parsed.links:
        conn.execute(
            "INSERT INTO links VALUES (?, ?, ?, ?)",
            [note_relpath, link.line_no, link.target, link.kind],
        )

    for tag in parsed.tags:
        conn.execute(
            "INSERT INTO tags VALUES (?, ?, ?)",
            [note_relpath, tag.name, tag.source],
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_index(vault_path: Path, store: IndexStore) -> IndexStats:
    """Incrementally update the DuckDB index from the vault on disk.

    All mutations run inside a single transaction. Returns stats describing
    what was found and changed.
    """
    conn = store.conn
    stats = IndexStats()

    # Snapshot existing records before starting
    existing: dict[str, tuple[int, int, str]] = {}
    for row in conn.execute(
        "SELECT note_relpath, mtime_ns, size_bytes, content_sha256 FROM notes"
    ).fetchall():
        existing[row[0]] = (row[1], row[2], row[3])

    # Deferred new notes: collected before rename detection so renames
    # can be identified and handled without double-inserting.
    # relpath -> (content, sha256, mtime_ns, size_bytes)
    new_notes: dict[str, tuple[str, str, int, int]] = {}
    seen_paths: set[str] = set()

    conn.execute("BEGIN TRANSACTION")
    try:
        # --- Step 1 & 2: walk files ---
        for abs_path in iter_markdown_files(vault_path):
            note_relpath = abs_path.relative_to(vault_path).as_posix()
            seen_paths.add(note_relpath)
            stat = abs_path.stat()
            mtime_ns = stat.st_mtime_ns
            size_bytes = stat.st_size

            if note_relpath in existing:
                old_mtime, old_size, old_sha = existing[note_relpath]

                if mtime_ns == old_mtime and size_bytes == old_size:
                    stats.unchanged += 1
                    continue

                content = read_note(abs_path)
                sha256 = _sha256(content)

                if sha256 == old_sha:
                    # Metadata-only update (e.g. mtime bumped, content identical)
                    conn.execute(
                        "UPDATE notes SET mtime_ns = ?, size_bytes = ? WHERE note_relpath = ?",
                        [mtime_ns, size_bytes, note_relpath],
                    )
                    stats.updated += 1
                    continue

                # Content changed: replace derived rows
                parsed = parse_note(content, abs_path.name)
                _delete_derived(store, note_relpath)
                _insert_derived(store, note_relpath, parsed)
                conn.execute(
                    """UPDATE notes
                       SET title = ?, is_daily_note = ?, mtime_ns = ?, size_bytes = ?,
                           content_sha256 = ?, word_count = ?
                       WHERE note_relpath = ?""",
                    [
                        parsed.title,
                        parsed.is_daily_note,
                        mtime_ns,
                        size_bytes,
                        sha256,
                        parsed.word_count,
                        note_relpath,
                    ],
                )
                stats.updated += 1

            else:
                # Defer new notes until after rename detection
                content = read_note(abs_path)
                sha256 = _sha256(content)
                new_notes[note_relpath] = (content, sha256, mtime_ns, size_bytes)

        # --- Step 3: find deleted paths ---
        deleted_paths = set(existing.keys()) - seen_paths

        # --- Step 4: rename detection ---
        # Build reverse map: sha256 -> new relpath (for newly-seen paths only)
        new_by_sha: dict[str, str] = {info[1]: rp for rp, info in new_notes.items()}
        renamed_new_paths: set[str] = set()

        for old_path in deleted_paths:
            old_sha = existing[old_path][2]
            if old_sha and old_sha in new_by_sha:
                new_path = new_by_sha[old_sha]
                _rename_in_db(store, old_path, new_path)
                renamed_new_paths.add(new_path)
                del new_by_sha[old_sha]
                stats.renamed += 1
            else:
                # --- Step 5: confirmed deletion ---
                _delete_all(store, old_path)
                stats.deleted += 1

        # --- Insert genuinely new notes (not renames) ---
        for note_relpath, (content, sha256, mtime_ns, size_bytes) in new_notes.items():
            if note_relpath in renamed_new_paths:
                continue
            abs_path = vault_path / note_relpath
            parsed = parse_note(content, abs_path.name)
            conn.execute(
                "INSERT INTO notes VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    note_relpath,
                    parsed.title,
                    parsed.is_daily_note,
                    mtime_ns,
                    size_bytes,
                    sha256,
                    parsed.word_count,
                ],
            )
            _insert_derived(store, note_relpath, parsed)
            stats.added += 1

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('last_indexed_at', ?)"
            " ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            [now],
        )

        conn.execute("COMMIT")

    except Exception:
        conn.execute("ROLLBACK")
        raise

    stats.scanned = len(seen_paths)
    return stats

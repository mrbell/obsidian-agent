from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from obsidian_agent.index.store import IndexStore


def get_note_count(store: IndexStore) -> int:
    return store.conn.execute("SELECT count(*) FROM notes").fetchone()[0]


def get_task_count(store: IndexStore) -> int:
    return store.conn.execute("SELECT count(*) FROM tasks").fetchone()[0]


def get_last_indexed_at(store: IndexStore) -> str | None:
    row = store.conn.execute(
        "SELECT value FROM meta WHERE key = 'last_indexed_at'"
    ).fetchone()
    return row[0] if row else None


def list_notes(
    store: IndexStore,
    folder: str | None = None,
    include_daily: bool = True,
) -> list[dict[str, Any]]:
    """Return notes optionally filtered by folder prefix and daily-note status."""
    parts: list[str] = []
    params: list[Any] = []

    if folder:
        parts.append("note_relpath LIKE ?")
        params.append(f"{folder.rstrip('/')}/%")

    if not include_daily:
        parts.append("is_daily_note = FALSE")

    where = ("WHERE " + " AND ".join(parts)) if parts else ""
    rows = store.conn.execute(
        f"SELECT note_relpath, title, mtime_ns FROM notes {where} ORDER BY note_relpath",
        params,
    ).fetchall()

    return [{"path": r[0], "title": r[1], "mtime_ns": r[2]} for r in rows]


def get_daily_notes_in_range(
    store: IndexStore,
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    """Return daily notes whose filename date falls within [start_date, end_date]."""
    rows = store.conn.execute(
        """SELECT note_relpath
           FROM notes
           WHERE is_daily_note = TRUE
             AND CAST(regexp_extract(note_relpath, '(\\d{4}-\\d{2}-\\d{2})', 1) AS DATE)
                 BETWEEN ? AND ?
           ORDER BY note_relpath""",
        [str(start_date), str(end_date)],
    ).fetchall()
    return [r[0] for r in rows]


def query_tasks(
    store: IndexStore,
    status: str = "open",
    due_before: date | None = None,
) -> list[dict[str, Any]]:
    parts = ["status = ?"]
    params: list[Any] = [status]

    if due_before is not None:
        parts.append("due_date IS NOT NULL AND due_date <= ?")
        params.append(str(due_before))

    where = "WHERE " + " AND ".join(parts)
    rows = store.conn.execute(
        f"SELECT text, note_relpath, due_date, line_no FROM tasks {where} ORDER BY due_date NULLS LAST, note_relpath",
        params,
    ).fetchall()

    return [
        {
            "text": r[0],
            "note_relpath": r[1],
            "due_date": str(r[2]) if r[2] else None,
            "line_no": r[3],
        }
        for r in rows
    ]


def get_note_links(
    store: IndexStore,
    note_relpath: str,
) -> dict[str, list[str]]:
    outgoing = [
        r[0]
        for r in store.conn.execute(
            "SELECT target FROM links WHERE note_relpath = ? ORDER BY line_no",
            [note_relpath],
        ).fetchall()
    ]
    incoming = [
        r[0]
        for r in store.conn.execute(
            "SELECT DISTINCT note_relpath FROM links WHERE target = ? ORDER BY note_relpath",
            [Path(note_relpath).stem],
        ).fetchall()
    ]
    return {"outgoing": outgoing, "incoming": incoming}


def find_notes_by_tag(store: IndexStore, tag: str) -> list[str]:
    rows = store.conn.execute(
        "SELECT DISTINCT note_relpath FROM tags WHERE tag = ? ORDER BY note_relpath",
        [tag],
    ).fetchall()
    return [r[0] for r in rows]

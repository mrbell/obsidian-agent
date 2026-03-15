#!/usr/bin/env python3
"""One-off script to backfill context_snippet for chunk_entities rows that have NULL.

Usage:
    uv run scripts/backfill_entity_snippets.py ~/.local/share/obsidian-agent/index.duckdb

This is safe to run multiple times — it only touches rows where context_snippet IS NULL.
After a full index rebuild the snippets will be populated automatically, so this script
is only needed for existing databases built before the runtime fix in issue 10-4.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from obsidian_agent.index.semantic import _derive_context_snippet
from obsidian_agent.index.store import IndexStore


def backfill(db_path: Path) -> int:
    store = IndexStore(db_path)
    rows = store.conn.execute(
        """
        SELECT ce.chunk_id, ce.entity_id, e.name, c.text
        FROM chunk_entities ce
        JOIN chunks c   ON c.id  = ce.chunk_id
        JOIN entities e ON e.id  = ce.entity_id
        WHERE ce.context_snippet IS NULL
        """
    ).fetchall()

    if not rows:
        print("No NULL context_snippet rows found — nothing to do.")
        return 0

    store.conn.execute("BEGIN TRANSACTION")
    try:
        for chunk_id, entity_id, entity_name, chunk_text in rows:
            snippet = _derive_context_snippet(entity_name, chunk_text)
            store.conn.execute(
                "UPDATE chunk_entities SET context_snippet = ? WHERE chunk_id = ? AND entity_id = ?",
                [snippet, chunk_id, entity_id],
            )
        store.conn.execute("COMMIT")
    except Exception:
        store.conn.execute("ROLLBACK")
        raise

    print(f"Backfilled {len(rows)} row(s).")
    return len(rows)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <path/to/index.duckdb>")
        sys.exit(1)
    backfill(Path(sys.argv[1]))

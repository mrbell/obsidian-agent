"""Query helpers over the semantic index (chunks, concepts, entities, implicit_items).

All functions accept a DuckDB connection (or IndexStore.conn) and return typed
dataclasses. No data is modified — these are read-only query helpers.
"""
from __future__ import annotations

import datetime
import time
from dataclasses import dataclass
from typing import Any


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ChunkResult:
    note_relpath: str
    chunk_index: int
    section_header: str | None
    text: str
    score: float   # cosine similarity, salience, or overlap depending on query


@dataclass(frozen=True)
class ConceptSummary:
    name: str
    note_count: int
    avg_salience: float


@dataclass(frozen=True)
class ImplicitItem:
    note_relpath: str
    type: str
    text: str


@dataclass(frozen=True)
class StaleConcept:
    name: str
    last_seen_date: str   # ISO date of most recent associated note modification
    note_count: int
    avg_salience: float


# ---------------------------------------------------------------------------
# View SQL — created on IndexStore init
# ---------------------------------------------------------------------------

SEMANTIC_VIEWS_SQL = """
CREATE OR REPLACE VIEW note_concepts_summary AS
SELECT
    c.note_relpath,
    con.name   AS concept,
    MAX(cc.salience) AS salience
FROM chunk_concepts cc
JOIN chunks c   ON c.id  = cc.chunk_id
JOIN concepts con ON con.id = cc.concept_id
GROUP BY c.note_relpath, con.name;

CREATE OR REPLACE VIEW note_entities_summary AS
SELECT DISTINCT
    c.note_relpath,
    e.name  AS entity,
    e.type  AS entity_type
FROM chunk_entities ce
JOIN chunks c   ON c.id  = ce.chunk_id
JOIN entities e ON e.id  = ce.entity_id;
"""


# ---------------------------------------------------------------------------
# Semantic similarity search (requires DuckDB VSS extension)
# ---------------------------------------------------------------------------

def search_similar(
    conn: Any,
    query_vector: list[float],
    n: int = 10,
) -> list[ChunkResult]:
    """Return the N chunks most similar to query_vector (cosine similarity).

    Requires the DuckDB VSS extension. Raises RuntimeError if VSS is not loaded.
    """
    dim = len(query_vector)
    try:
        rows = conn.execute(
            f"""
            SELECT
                c.note_relpath,
                c.chunk_index,
                c.section_header,
                c.text,
                array_cosine_similarity(ce.embedding, $1::FLOAT[{dim}]) AS score
            FROM chunk_embeddings ce
            JOIN chunks c ON c.id = ce.chunk_id
            ORDER BY score DESC
            LIMIT {int(n)}
            """,
            [query_vector],
        ).fetchall()
    except Exception as exc:
        raise RuntimeError(
            "search_similar requires the DuckDB VSS extension. "
            "Ensure IndexStore.vss_available is True before calling this function."
        ) from exc
    return [
        ChunkResult(
            note_relpath=row[0],
            chunk_index=row[1],
            section_header=row[2],
            text=row[3],
            score=float(row[4]),
        )
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Related notes (concept overlap)
# ---------------------------------------------------------------------------

def find_related_notes(
    conn: Any,
    note_relpath: str,
    n: int = 10,
) -> list[tuple[str, float]]:
    """Return notes most conceptually related to note_relpath.

    Similarity is measured as the sum of (salience_a × salience_b) over
    shared concepts. Returns (related_relpath, overlap_score) pairs.
    """
    rows = conn.execute(
        """
        SELECT
            c2.note_relpath                         AS related,
            SUM(cc1.salience * cc2.salience)        AS overlap_score
        FROM chunk_concepts cc1
        JOIN chunks c1 ON c1.id = cc1.chunk_id AND c1.note_relpath = ?
        JOIN chunk_concepts cc2 ON cc2.concept_id = cc1.concept_id
        JOIN chunks c2 ON c2.id = cc2.chunk_id AND c2.note_relpath != ?
        GROUP BY c2.note_relpath
        ORDER BY overlap_score DESC
        LIMIT ?
        """,
        [note_relpath, note_relpath, n],
    ).fetchall()
    return [(row[0], float(row[1])) for row in rows]


# ---------------------------------------------------------------------------
# Concept queries
# ---------------------------------------------------------------------------

def list_concepts(conn: Any, n: int = 50) -> list[ConceptSummary]:
    """Return the top N concepts by number of distinct notes they appear in."""
    rows = conn.execute(
        """
        SELECT con.name,
               COUNT(DISTINCT c.note_relpath) AS note_count,
               AVG(cc.salience)               AS avg_salience
        FROM chunk_concepts cc
        JOIN concepts con ON con.id = cc.concept_id
        JOIN chunks c     ON c.id  = cc.chunk_id
        GROUP BY con.name
        ORDER BY note_count DESC, avg_salience DESC
        LIMIT ?
        """,
        [n],
    ).fetchall()
    return [
        ConceptSummary(name=row[0], note_count=row[1], avg_salience=float(row[2]))
        for row in rows
    ]


def search_by_concept(conn: Any, concept_name: str) -> list[ChunkResult]:
    """Return all chunks discussing a given concept (exact name match)."""
    rows = conn.execute(
        """
        SELECT c.note_relpath, c.chunk_index, c.section_header, c.text, cc.salience
        FROM chunk_concepts cc
        JOIN chunks c     ON c.id  = cc.chunk_id
        JOIN concepts con ON con.id = cc.concept_id
        WHERE con.name = ?
        ORDER BY cc.salience DESC
        """,
        [concept_name],
    ).fetchall()
    return [
        ChunkResult(
            note_relpath=row[0],
            chunk_index=row[1],
            section_header=row[2],
            text=row[3],
            score=float(row[4]),
        )
        for row in rows
    ]


def get_recent_concepts(
    conn: Any,
    since_days: int,
    n: int = 20,
) -> list[ConceptSummary]:
    """Return top concepts in notes modified within the last since_days days."""
    since_ns = int((time.time() - since_days * 86400) * 1e9)
    rows = conn.execute(
        """
        SELECT con.name,
               COUNT(DISTINCT c.note_relpath) AS note_count,
               MAX(cc.salience)               AS peak_salience
        FROM chunk_concepts cc
        JOIN chunks c     ON c.id  = cc.chunk_id
        JOIN concepts con ON con.id = cc.concept_id
        JOIN notes n      ON n.note_relpath = c.note_relpath
        WHERE n.mtime_ns >= ?
        GROUP BY con.name
        ORDER BY note_count DESC, peak_salience DESC
        LIMIT ?
        """,
        [since_ns, n],
    ).fetchall()
    return [
        ConceptSummary(name=row[0], note_count=row[1], avg_salience=float(row[2]))
        for row in rows
    ]


def get_older_notes_by_concepts(
    conn: Any,
    concept_names: list[str],
    newer_than_days: int,
    n: int = 20,
) -> list[tuple[str, float]]:
    """Return notes discussing concept_names whose mtime is older than newer_than_days.

    Useful for resurfacing old ideas related to recent activity. Returns
    (note_relpath, overlap_score) sorted by overlap descending.
    """
    if not concept_names:
        return []
    cutoff_ns = int((time.time() - newer_than_days * 86400) * 1e9)
    placeholders = ", ".join("?" * len(concept_names))
    rows = conn.execute(
        f"""
        SELECT c.note_relpath,
               SUM(cc.salience) AS overlap_score
        FROM chunk_concepts cc
        JOIN chunks c     ON c.id  = cc.chunk_id
        JOIN concepts con ON con.id = cc.concept_id
        JOIN notes n      ON n.note_relpath = c.note_relpath
        WHERE con.name IN ({placeholders})
          AND n.mtime_ns < ?
        GROUP BY c.note_relpath
        ORDER BY overlap_score DESC
        LIMIT ?
        """,
        [*concept_names, cutoff_ns, n],
    ).fetchall()
    return [(row[0], float(row[1])) for row in rows]


# ---------------------------------------------------------------------------
# Entity queries
# ---------------------------------------------------------------------------

def get_entity_context(conn: Any, entity_name: str) -> list[ChunkResult]:
    """Return all chunks mentioning the named entity."""
    rows = conn.execute(
        """
        SELECT c.note_relpath, c.chunk_index, c.section_header, c.text, 1.0 AS score
        FROM chunk_entities ce
        JOIN chunks c   ON c.id  = ce.chunk_id
        JOIN entities e ON e.id  = ce.entity_id
        WHERE e.name = ?
        ORDER BY c.note_relpath, c.chunk_index
        """,
        [entity_name],
    ).fetchall()
    return [
        ChunkResult(
            note_relpath=row[0],
            chunk_index=row[1],
            section_header=row[2],
            text=row[3],
            score=float(row[4]),
        )
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Implicit item queries
# ---------------------------------------------------------------------------

def get_implicit_items(
    conn: Any,
    item_type: str | None = None,
    note_relpath: str | None = None,
) -> list[ImplicitItem]:
    """Return implicit items, optionally filtered by type and/or note.

    item_type: 'idea' | 'question' | 'intention' | 'task' | None (all)
    """
    conditions = []
    params: list[Any] = []
    if item_type is not None:
        conditions.append("type = ?")
        params.append(item_type)
    if note_relpath is not None:
        conditions.append("note_relpath = ?")
        params.append(note_relpath)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    rows = conn.execute(
        f"""
        SELECT note_relpath, type, text
        FROM implicit_items
        {where}
        ORDER BY extracted_at DESC
        """,
        params,
    ).fetchall()
    return [ImplicitItem(note_relpath=row[0], type=row[1], text=row[2]) for row in rows]


def find_unformalized_tasks(conn: Any) -> list[ImplicitItem]:
    """Return implicit task/intention items that have no corresponding formal task.

    A formal task is a row in ``tasks`` with status='open' whose text shares
    the first word with the implicit item.
    """
    rows = conn.execute(
        """
        SELECT ii.note_relpath, ii.type, ii.text
        FROM implicit_items ii
        LEFT JOIN tasks t ON (
            t.note_relpath = ii.note_relpath
            AND t.status = 'open'
            AND t.text ILIKE '%' || SPLIT_PART(ii.text, ' ', 1) || '%'
        )
        WHERE ii.type IN ('task', 'intention')
          AND t.line_no IS NULL
        ORDER BY ii.note_relpath
        """
    ).fetchall()
    return [ImplicitItem(note_relpath=row[0], type=row[1], text=row[2]) for row in rows]


# ---------------------------------------------------------------------------
# Cross-index: unlinked related notes
# ---------------------------------------------------------------------------

def get_stale_concepts(
    conn: Any,
    inactive_before: str,
    n: int = 20,
) -> list[StaleConcept]:
    """Return concepts whose most recent associated note hasn't been modified since inactive_before.

    inactive_before: ISO date string (e.g. '2025-12-01'). Concepts are stale when every
    note that mentions them has mtime_ns older than this date.

    Ordered by last_seen_date descending (most recently active stale concepts first).
    Useful for detecting 'orphaned threads' — ideas that were active at some point but
    have since gone quiet.
    """
    cutoff_ns = int(
        time.mktime(datetime.date.fromisoformat(inactive_before).timetuple()) * 1e9
    )
    rows = conn.execute(
        """
        SELECT con.name,
               MAX(n.mtime_ns)                   AS last_seen_ns,
               COUNT(DISTINCT c.note_relpath)     AS note_count,
               AVG(cc.salience)                   AS avg_salience
        FROM chunk_concepts cc
        JOIN chunks c     ON c.id  = cc.chunk_id
        JOIN concepts con ON con.id = cc.concept_id
        JOIN notes n      ON n.note_relpath = c.note_relpath
        GROUP BY con.name
        HAVING MAX(n.mtime_ns) < ?
        ORDER BY last_seen_ns DESC
        LIMIT ?
        """,
        [cutoff_ns, n],
    ).fetchall()
    results = []
    for row in rows:
        last_seen_dt = datetime.datetime.fromtimestamp(row[1] / 1e9)
        results.append(StaleConcept(
            name=row[0],
            last_seen_date=last_seen_dt.date().isoformat(),
            note_count=row[2],
            avg_salience=float(row[3]),
        ))
    return results


def find_unlinked_related_notes(
    conn: Any,
    min_score: float = 0.5,
    n: int = 20,
) -> list[tuple[str, str, float]]:
    """Return (note_a, note_b, overlap_score) pairs that share concepts but no wikilink.

    Computes concept overlap between all note pairs and filters to those where
    neither note contains a wikilink targeting the other.
    """
    rows = conn.execute(
        """
        WITH concept_overlap AS (
            SELECT
                c1.note_relpath AS note_a,
                c2.note_relpath AS note_b,
                SUM(cc1.salience * cc2.salience) AS overlap_score
            FROM chunk_concepts cc1
            JOIN chunks c1 ON c1.id = cc1.chunk_id
            JOIN chunk_concepts cc2 ON cc2.concept_id = cc1.concept_id
            JOIN chunks c2 ON c2.id = cc2.chunk_id
            WHERE c1.note_relpath < c2.note_relpath   -- canonical ordering avoids (A,B)+(B,A)
            GROUP BY c1.note_relpath, c2.note_relpath
            HAVING SUM(cc1.salience * cc2.salience) >= ?
        )
        SELECT co.note_a, co.note_b, co.overlap_score
        FROM concept_overlap co
        WHERE NOT EXISTS (
            SELECT 1 FROM links l
            WHERE l.kind = 'wikilink'
              AND (
                (l.note_relpath = co.note_a
                 AND l.target LIKE '%' || REPLACE(co.note_b, '.md', '') || '%')
                OR
                (l.note_relpath = co.note_b
                 AND l.target LIKE '%' || REPLACE(co.note_a, '.md', '') || '%')
              )
        )
        ORDER BY co.overlap_score DESC
        LIMIT ?
        """,
        [min_score, n],
    ).fetchall()
    return [(row[0], row[1], float(row[2])) for row in rows]

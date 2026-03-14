from __future__ import annotations

import logging
from pathlib import Path
from typing import Self

import duckdb

_SCHEMA_SQL = Path(__file__).parent / "schema.sql"
_log = logging.getLogger(__name__)


class IndexStore:
    """DuckDB-backed index store.

    Opens (or creates) a DuckDB database at db_path and initialises the
    schema. Use as a context manager or call close() explicitly.

    The DuckDB VSS extension is loaded on init for vector similarity search.
    ``vss_available`` is False if the extension could not be loaded (e.g. no
    network on first run); structural indexing still works in that case.

    Example::

        with IndexStore(db_path) as store:
            store.conn.execute("SELECT count(*) FROM notes").fetchone()
    """

    def __init__(self, db_path: Path, *, read_only: bool = False) -> None:
        self._db_path = db_path
        self.conn: duckdb.DuckDBPyConnection = duckdb.connect(
            str(db_path), read_only=read_only
        )
        if not read_only:
            self.conn.execute(_SCHEMA_SQL.read_text())
        self.vss_available: bool = self._load_vss(read_only=read_only)

    def _load_vss(self, *, read_only: bool = False) -> bool:
        try:
            if read_only:
                self.conn.execute("LOAD vss;")
            else:
                self.conn.execute("INSTALL vss; LOAD vss;")
            return True
        except duckdb.Error as exc:
            _log.warning("DuckDB VSS extension not available: %s", exc)
            return False

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

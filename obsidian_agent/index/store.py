from __future__ import annotations

from pathlib import Path
from typing import Self

import duckdb

_SCHEMA_SQL = Path(__file__).parent / "schema.sql"


class IndexStore:
    """DuckDB-backed index store.

    Opens (or creates) a DuckDB database at db_path and initialises the
    schema. Use as a context manager or call close() explicitly.

    Example::

        with IndexStore(db_path) as store:
            store.conn.execute("SELECT count(*) FROM notes").fetchone()
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self.conn: duckdb.DuckDBPyConnection = duckdb.connect(str(db_path))
        self.conn.execute(_SCHEMA_SQL.read_text())

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

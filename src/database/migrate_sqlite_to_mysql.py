"""Copy legacy Agent SQLite records into MySQL without deleting the source."""

import sqlite3
from pathlib import Path

from sqlalchemy import text

from database.database import get_engine
from database.init_db import create_tables

SQLITE_PATH = Path(__file__).with_name("agent.db")
TABLE_COLUMNS = {
    "knowledge_documents": ("id", "title", "source", "created_time"),
    "knowledge_chunks": ("id", "document_id", "content", "source", "created_time"),
    "memories": (
        "id",
        "content",
        "category",
        "importance",
        "embedding",
        "created_at",
    ),
}


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    return row is not None


def migrate() -> dict[str, int]:
    """Copy compatible rows and preserve their original primary keys."""
    if not SQLITE_PATH.exists():
        raise FileNotFoundError(f"Legacy SQLite database was not found: {SQLITE_PATH}")

    create_tables()
    copied: dict[str, int] = {}
    sqlite_connection = sqlite3.connect(SQLITE_PATH)
    sqlite_connection.row_factory = sqlite3.Row
    try:
        with get_engine().begin() as mysql_connection:
            for table, expected_columns in TABLE_COLUMNS.items():
                if not _table_exists(sqlite_connection, table):
                    copied[table] = 0
                    continue

                source_columns = {
                    row[1]
                    for row in sqlite_connection.execute(f"PRAGMA table_info({table})")
                }
                columns = [
                    column for column in expected_columns if column in source_columns
                ]
                if "id" not in columns:
                    raise RuntimeError(f"Legacy table {table} does not contain an id column")

                rows = [
                    dict(row)
                    for row in sqlite_connection.execute(
                        f"SELECT {', '.join(columns)} FROM {table} ORDER BY id"
                    )
                ]
                if not rows:
                    copied[table] = 0
                    continue

                column_sql = ", ".join(columns)
                value_sql = ", ".join(f":{column}" for column in columns)
                mysql_connection.execute(
                    text(
                        f"""
                        INSERT INTO {table} ({column_sql})
                        VALUES ({value_sql})
                        ON DUPLICATE KEY UPDATE id = id
                        """
                    ),
                    rows,
                )
                copied[table] = len(rows)
    finally:
        sqlite_connection.close()
    return copied


if __name__ == "__main__":
    for table, count in migrate().items():
        print(f"{table}: {count} rows copied")

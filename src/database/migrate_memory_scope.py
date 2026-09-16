"""Add user and session scope to existing MySQL memories without data loss."""

from sqlalchemy import inspect, text

from database.database import get_engine

LEGACY_USER_ID = "legacy"
LEGACY_SESSION_ID = "legacy"


def migrate() -> int:
    """Backfill existing memories into an isolated legacy scope."""
    with get_engine().begin() as connection:
        inspector = inspect(connection)
        columns = {
            column["name"] for column in inspector.get_columns("memories")
        }
        if "user_id" not in columns:
            connection.execute(
                text("ALTER TABLE memories ADD COLUMN user_id VARCHAR(128) NULL")
            )
        if "session_id" not in columns:
            connection.execute(
                text("ALTER TABLE memories ADD COLUMN session_id VARCHAR(128) NULL")
            )

        result = connection.execute(
            text(
                """
                UPDATE memories
                SET user_id = COALESCE(user_id, :legacy_user_id),
                    session_id = COALESCE(session_id, :legacy_session_id)
                WHERE user_id IS NULL OR session_id IS NULL
                """
            ),
            {
                "legacy_user_id": LEGACY_USER_ID,
                "legacy_session_id": LEGACY_SESSION_ID,
            },
        )
        connection.execute(
            text("ALTER TABLE memories MODIFY COLUMN user_id VARCHAR(128) NOT NULL")
        )
        connection.execute(
            text("ALTER TABLE memories MODIFY COLUMN session_id VARCHAR(128) NOT NULL")
        )

        index_names = {
            index["name"] for index in inspect(connection).get_indexes("memories")
        }
        if "idx_memories_user_session" not in index_names:
            connection.execute(
                text(
                    """
                    CREATE INDEX idx_memories_user_session
                    ON memories (user_id, session_id)
                    """
                )
            )
    return result.rowcount


if __name__ == "__main__":
    print(f"Scoped {migrate()} existing memories")

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from sqlalchemy import text
try:
    from database.database import get_engine
except (ImportError, ModuleNotFoundError):
    from database import get_engine


def create_tables() -> None:
    """Create the MySQL tables owned by the Agent application."""
    statements = (
        """
        CREATE TABLE IF NOT EXISTS memories (
            id BIGINT NOT NULL AUTO_INCREMENT,
            user_id VARCHAR(128) NOT NULL,
            session_id VARCHAR(128) NOT NULL,
            content TEXT NOT NULL,
            category VARCHAR(50) NOT NULL,
            importance INT NOT NULL DEFAULT 0,
            embedding JSON NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            INDEX idx_memories_user_session (user_id, session_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS knowledge_documents (
            id BIGINT NOT NULL AUTO_INCREMENT,
            title VARCHAR(255) NOT NULL,
            source VARCHAR(1024) NULL,
            created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            INDEX idx_knowledge_documents_source (source(255))
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS chat_history (
            id BIGINT NOT NULL AUTO_INCREMENT,
            user_id VARCHAR(128) NOT NULL,
            session_id VARCHAR(128) NOT NULL,
            role VARCHAR(32) NOT NULL,
            content MEDIUMTEXT NOT NULL,
            metadata JSON NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            INDEX idx_chat_history_user_session (user_id, session_id, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
    )
    with get_engine().begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


if __name__ == "__main__":
    create_tables()
    print("MySQL tables are ready")

from sqlalchemy import text

from database.database import get_engine


def create_tables() -> None:
    """Create the MySQL tables owned by the Agent application."""
    statements = (
        """
        CREATE TABLE IF NOT EXISTS memories (
            id BIGINT NOT NULL AUTO_INCREMENT,
            content TEXT NOT NULL,
            category VARCHAR(50) NOT NULL,
            importance INT NOT NULL DEFAULT 0,
            embedding JSON NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id)
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
        CREATE TABLE IF NOT EXISTS knowledge_chunks (
            id BIGINT NOT NULL AUTO_INCREMENT,
            document_id BIGINT NOT NULL,
            content MEDIUMTEXT NOT NULL,
            source VARCHAR(1024) NULL,
            created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            INDEX idx_knowledge_chunks_document_id (document_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
    )
    with get_engine().begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


if __name__ == "__main__":
    create_tables()
    print("MySQL tables are ready")

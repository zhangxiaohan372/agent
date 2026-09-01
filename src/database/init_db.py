from database.database import DATABASE_PATH, get_connection


def create_tables():
    connection = get_connection()
    cursor = connection.cursor()
    # 创建记忆表
    memory_sql = """
    CREATE TABLE IF NOT EXISTS memories(
         id INTEGER PRIMARY KEY AUTOINCREMENT,
         content TEXT NOT NULL,
         category TEXT NOT NULL,
         importance INTEGER NOT NULL DEFAULT 0,
         embedding TEXT,
         created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """
    # 创建知识库表
    documents_sql = """
    CREATE TABLE IF NOT EXISTS knowledge_documents(
         id INTEGER PRIMARY KEY AUTOINCREMENT,
         title TEXT NOT NULL,
         source TEXT,
         created_time DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """
    # 知识分块表
    knowledge_sql = """
    CREATE TABLE IF NOT EXISTS knowledge_chunks(
         id INTEGER PRIMARY KEY AUTOINCREMENT,
         document_id INTEGER NOT NULL,
         content TEXT NOT NULL,
         embedding TEXT,
         source TEXT,
         created_time DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """
    cursor.execute(memory_sql)
    cursor.execute(documents_sql)
    cursor.execute(knowledge_sql)
    # ! 创建索引加快寻找knowledge的速度
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_document_id
        ON knowledge_chunks(document_id)
        """
    )
    connection.commit()
    cursor.close()
    connection.close()


if __name__ == "__main__":
    if DATABASE_PATH.exists():
        DATABASE_PATH.unlink()

    create_tables()
    print("数据表创建成功")

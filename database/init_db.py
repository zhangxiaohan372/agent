try:
    from database.database import DATABASE_PATH, get_connection
except ImportError:
    from database import DATABASE_PATH, get_connection


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
    knowledge_sql = """
    CREATE TABLE IF NOT EXISTS knowledge_chunks(
         id INTEGER PRIMARY KEY AUTOINCREMENT,
         content TEXT NOT NULL,
         embedding TEXT,
         source TEXT,
         created_time DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """
    cursor.execute(memory_sql)
    cursor.execute(knowledge_sql)
    connection.commit()
    cursor.close()
    connection.close()


if __name__ == "__main__":
    if DATABASE_PATH.exists():
        DATABASE_PATH.unlink()

    create_tables()
    print("数据表创建成功")

import sqlite3
from pathlib import Path


# 当前项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent

# 数据库目录
DATABASE_DIR = BASE_DIR / "database"

# 数据库文件
DATABASE_PATH = DATABASE_DIR / "agent.db"


def get_connection():
    """
    获取 SQLite 数据库连接
    """
    DATABASE_DIR.mkdir(exist_ok=True)

    return sqlite3.connect(DATABASE_PATH)


if __name__ == "__main__":
    connection = get_connection()
    connection.close()

    print(f"数据库创建成功：{DATABASE_PATH}")

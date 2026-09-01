import sqlite3
from pathlib import Path

DATABASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = DATABASE_DIR / "agent.db"


def get_connection():
    DATABASE_DIR.mkdir(exist_ok=True)
    return sqlite3.connect(DATABASE_PATH)


if __name__ == "__main__":
    connection = get_connection()
    connection.close()
    print(f"数据库创建成功：{DATABASE_PATH}")

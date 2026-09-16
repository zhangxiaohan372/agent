import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, URL

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def _required_setting(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required MySQL setting: {name}")
    return value


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """返回共享的、线程安全的 MySQL 连接池。"""
    url = URL.create(
        "mysql+pymysql",
        username=_required_setting("MYSQL_USER"),
        password=_required_setting("MYSQL_PASSWORD"),
        host=_required_setting("MYSQL_HOST"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        database=_required_setting("MYSQL_DATABASE"),
        query={"charset": "utf8mb4"},
    )
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_size=5,
        max_overflow=10,
    )


def dispose_engine() -> None:
    """在程序关闭或者测试时，关闭连接池里的数据库连接"""
    get_engine().dispose()
    get_engine.cache_clear()


if __name__ == "__main__":
    with get_engine().connect() as connection:
        connection.exec_driver_sql("SELECT 1")
    print("MySQL connection succeeded")

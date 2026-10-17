import os
import logging
import redis
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)


class FallbackMemoryStore:
    """当本地或远程 Redis 服务未就绪时的内存兜底存储。
    
    保证在没有运行 redis-server 的情况下，代码也能平稳降级运行而不报错。
    """

    def __init__(self):
        self._store = {}

    def get(self, name: str):
        return self._store.get(name)

    def set(self, name: str, value: str, ex: int = None, **kwargs):
        self._store[name] = value
        return True

    def delete(self, *names):
        for name in names:
            self._store.pop(name, None)
        return True

    def ttl(self, name: str) -> int:
        return -1

    def exists(self, name: str) -> bool:
        return name in self._store


def create_redis_client():
    """创建并测试 Redis 连接，若失败则安全降级到内存模式。"""
    try:
        client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD,
            decode_responses=True,
            socket_connect_timeout=1.0,
            socket_timeout=2.0,
        )
        client.ping()
        print(f"[Redis] 已连接到 Redis 服务: {REDIS_HOST}:{REDIS_PORT}")
        return client
    except Exception as e:
        print(f"[Redis] 无法连接到 Redis 服务 ({e})，系统已安全降级为内存会话模式。")
        return FallbackMemoryStore()


redis_client = create_redis_client()

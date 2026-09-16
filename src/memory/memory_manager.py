import json
import math
from contextlib import closing

from database.database import get_connection
from .embedding_manager import EmbeddingManager


class MemoryManager:
    def __init__(self):
        self.embedding_manager = EmbeddingManager()

    def save(self, memory, category, importance, embedding=None):
        embedding_str = json.dumps(embedding) if embedding is not None else None
        with closing(get_connection()) as connection:
            connection.execute(
                "INSERT INTO memories (content, category, importance, embedding) VALUES (?, ?, ?, ?)",
                (memory, category, importance, embedding_str),
            )
            connection.commit()

    def search(self, query, top_k=5):
        #给设置搜索词进行向量转换，获取向量值
        query_embedding = self.embedding_manager.embed(query)
        with closing(get_connection()) as connection:
            rows = connection.execute(
                """
                SELECT id,content,category,importance,embedding
                FROM memories
                WHERE embedding IS NOT NULL
                """
            ).fetchall()
        # 获取所有memory的数据
        scored = []
        for row in rows:
            memory_embedding = json.loads(row[4])

            score = self._cosine_similarity(query_embedding, memory_embedding)
            scored.append((score,row))

        # 对余弦值进行相似对匹配
        scored.sort(
            key=lambda item:item[0],
            reverse=True
        )
        return [
            row
            for _, row in scored[:top_k]
        ]

    def get_all(self):
        with closing(get_connection()) as connection:
            return connection.execute("SELECT * FROM memories").fetchall()

    def close(self):
        """Retained for callers; database connections are scoped per operation."""
        pass

    @staticmethod
    def _cosine_similarity(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

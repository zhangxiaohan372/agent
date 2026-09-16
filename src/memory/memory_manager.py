import json
import math

from sqlalchemy import text

from database.database import get_engine
from .embedding_manager import EmbeddingManager


class MemoryManager:
    def __init__(self):
        self.embedding_manager = EmbeddingManager()

    def save(self, memory, category, importance, embedding, user_id, session_id):
        embedding_str = json.dumps(embedding) if embedding is not None else None
        with get_engine().begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO memories
                        (content, category, importance, embedding, user_id, session_id)
                    VALUES
                        (:content, :category, :importance, :embedding, :user_id, :session_id)
                    """
                ),
                {
                    "content": memory,
                    "category": category,
                    "importance": importance,
                    "embedding": embedding_str,
                    "user_id": user_id,
                    "session_id": session_id,
                },
            )

    def search(self, query, user_id, session_id, top_k=5):
        #给设置搜索词进行向量转换，获取向量值
        query_embedding = self.embedding_manager.embed(query)
        with get_engine().connect() as connection:
            rows = connection.execute(
                text(
                    """
                SELECT id,content,category,importance,embedding
                FROM memories
                WHERE user_id = :user_id
                  AND session_id = :session_id
                  AND embedding IS NOT NULL
                """
                ),
                {"user_id": user_id, "session_id": session_id},
            ).fetchall()
        # 获取所有memory的数据
        scored = []
        for row in rows:
            stored_embedding = row[4]
            memory_embedding = (
                json.loads(stored_embedding)
                if isinstance(stored_embedding, str)
                else stored_embedding
            )

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

    def get_all(self, user_id, session_id):
        with get_engine().connect() as connection:
            return connection.execute(
                text(
                    """
                    SELECT * FROM memories
                    WHERE user_id = :user_id AND session_id = :session_id
                    """
                ),
                {"user_id": user_id, "session_id": session_id},
            ).fetchall()

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

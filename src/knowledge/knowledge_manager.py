# 用户提出问题 → 转 embedding → 去知识库找最相关 chunk → 返回结果
from memory.embedding_manager import EmbeddingManager
import json
import math
from database.init_db import create_tables
from database.database import get_connection
from .init_knowledge import InitKnowledge

class KnowledgeManager:
    def __init__(self,source_path=None):
        self.embedding_manager = EmbeddingManager()
        self.init_knowledge = InitKnowledge()
        self.source_path = source_path

    #余弦相似度数学公式
    def cosine_similarity(self,a, b):

        dot = sum(
            x * y for x, y in zip(a, b)
        )

        norm_a = math.sqrt(
            sum(x*x for x in a)
        )

        norm_b = math.sqrt(
            sum(x*x for x in b)
        )

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot / (norm_a * norm_b)

    #增加search方法
    def search(self, query, top_k=3, document_id=None):
        # 1. 用户问题转向量
        query_embedding = self.embedding_manager.embed(query)

        # 2. 查询数据库
        create_tables()
        connection = get_connection()
        cursor = connection.cursor()
        sql = """
            SELECT document_id, content, source, embedding
            FROM knowledge_chunks
            WHERE embedding IS NOT NULL
        """
        params = []
        if document_id is not None:
            sql += " AND document_id = ?"
            params.append(document_id)
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        scored = []

        for row in rows:
            chunk_embedding = json.loads(row[3])

            score = self.cosine_similarity(query_embedding,chunk_embedding)

            scored.append({
                "document_id": row[0],
                "content": row[1],
                "source": row[2],
                "score": score,
            })

        scored.sort(
            key=lambda x: x['score'],
            reverse = True
        )

        cursor.close()
        connection.close()

        return scored[:top_k]

    def ingest_text(self, text, source="user_input", title=None):
        return self.init_knowledge.ingest_text(text, source=source, title=title)

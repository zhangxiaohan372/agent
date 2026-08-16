from .chunker import Chunker
from .document_loader import DocumentLoader
from memory.embedding_manager import EmbeddingManager
import json
import math
from database.init_db import create_tables
from database.database import get_connection

class KnowledgeManager:
    def __init__(self,source_path):
        self.source_path = source_path
        self.loader = DocumentLoader()
        self.chunker = Chunker()
        self.embedding_manager = EmbeddingManager()

    def load_and_chunk(self):

        text = self.loader.load(self.source_path)
        chunks = self.chunker.split(text)
        return chunks

    def embed_chunks(self,chunks):
        embeddings = []

        for chunk in chunks:
            embedding = self.embedding_manager.embed(chunk)
            embeddings.append(embedding)

        return embeddings

    def save_chunks(self,chunks,embeddings):
        create_tables()
        connection = get_connection()
        cursor = connection.cursor()
        for chunk,embedding in zip(chunks,embeddings):
            cursor.execute(
                """
                INSERT INTO knowledge_chunks (content,embedding,source)
                VALUES (?,?,?)
                """,
                (
                    chunk,
                    json.dumps(embedding),
                    self.source_path,
                )
            )
        connection.commit()
        cursor.close()
        connection.close()
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
    def search(self,query,top_k=3):
        # 1. 用户问题转向量
        query_embedding = self.embedding_manager.embed(query)

        # 2. 查询数据库
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT content, source, embedding
            FROM knowledge_chunks
            WHERE embedding IS NOT NULL
            """
        )
        rows = cursor.fetchall()
        scored = []

        for row in rows:
            chunk_embedding = json.loads(row[2])

            score = self.cosine_similarity(query_embedding,chunk_embedding)

            scored.append({
                "content": row[0],
                "source": row[1],
                "score": score,
            })

        scored.sort(
            key=lambda x: x['score'],
            reverse = True
        )

        cursor.close()
        connection.close()

        return scored[:top_k]
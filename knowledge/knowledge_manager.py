from .chunker import Chunker
from .document_loader import DocumentLoader
from memory.embedding_manager import EmbeddingManager
import json
import math
from pathlib import Path
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

    def create_document(self, title, source=None):
        create_tables()
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO knowledge_documents (title, source)
            VALUES (?, ?)
            """,
            (title, source),
        )
        document_id = cursor.lastrowid
        connection.commit()
        cursor.close()
        connection.close()
        return document_id

    def save_chunks(self, chunks, embeddings, source=None, document_id=None):
        # ! source 由调用方指定；未指定时使用知识库默认来源文件
        source = self.source_path if source is None else source
        if document_id is None:
            document_id = self.create_document(
                title=Path(str(source)).name or str(source),
                source=source,
            )
        create_tables()
        connection = get_connection()
        cursor = connection.cursor()
        for chunk,embedding in zip(chunks,embeddings):
            cursor.execute(
                """
                INSERT INTO knowledge_chunks
                    (document_id, content, embedding, source)
                VALUES (?,?,?,?)
                """,
                (
                    document_id,
                    chunk,
                    json.dumps(embedding),
                    source,
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

    # ! 增加知识进入（用户输入知识库） 
    def ingest_text(self, text, source, title=None):
        chunks = self.chunker.split(text)
        embeddings = self.embed_chunks(chunks)
        source = self.source_path if source is None else source
        title = title or Path(str(source)).name or str(source)
        document_id = self.create_document(title=title, source=source)
        self.save_chunks(
            chunks,
            embeddings,
            source=source,
            document_id=document_id,
        )
        return document_id

    def ingest_file(self, file_path):
        text = self.loader.load(file_path)
        return self.ingest_text(text, file_path, title=Path(file_path).name)

# ! 拆分知识库入库和知识库引用
#    文件夹/文件 
#         ↓
# DocumentLoader
#         ↓
# Chunker
#         ↓
# Embedding模型
#         ↓
# knowledge_chunks表
from .document_loader import DocumentLoader
from .chunker import Chunker
from memory.embedding_manager import EmbeddingManager
from pathlib import Path
from database.init_db import create_tables
from database.database import get_connection
import json

class InitKnowledge:
    def __init__(self):
        self.document_loader = DocumentLoader()
        self.chunker = Chunker()
        self.embedding_manager = EmbeddingManager()

    # 创建知识库的id储存表更方便找到相应资料
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

    def embed_chunks(self, chunks):
        return [self.embedding_manager.embed(chunk) for chunk in chunks]

    # 保存文章切片
    def save_chunks(self, chunks, embeddings, source=None, document_id=None):
        source = source or "unknown"
        if document_id is None:
            document_id = self.create_document(
                title=Path(str(source)).name or str(source),
                source=source,
            )
        create_tables()
        connection = get_connection()
        cursor = connection.cursor()
        for chunk, embedding in zip(chunks, embeddings):
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
                ),
            )
        connection.commit()
        cursor.close()
        connection.close()

    # ! 增加知识进入（用户输入知识库）
    def ingest_text(self, text, source, title=None):
        chunks = self.chunker.split(text)
        embeddings = self.embed_chunks(chunks)
        source = source or "user_input"
        title = title or Path(str(source)).name or str(source)
        document_id = self.create_document(title=title, source=source)
        self.save_chunks(
            chunks,
            embeddings,
            source=source,
            document_id=document_id,
        )
        return document_id

    def find_document_id(self, source):
        create_tables()
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "SELECT id FROM knowledge_documents WHERE source = ?",
            (source,),
        )
        row = cursor.fetchone()
        cursor.close()
        connection.close()
        return row[0] if row else None

    def ingest_file(self, file_path):
        file_path = str(file_path)
        existing_id = self.find_document_id(file_path)
        if existing_id is not None:
            return existing_id
        text = self.document_loader.load(file_path)
        return self.ingest_text(text, file_path, title=Path(file_path).name)

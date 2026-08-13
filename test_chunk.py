from dotenv import load_dotenv

load_dotenv()

from document_loader import DocumentLoader
from chunker import Chunker
from memory.embedding_manager import EmbeddingManager
import json
import math
from database.init_db import create_tables
from database.database import get_connection


SOURCE_PATH = "knowledge/rag-test-document.md"


# 余弦相似度数学公式
def cosine_similarity(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def save_knowledge_chunks(chunks, embedding_manager):
    create_tables()

    conn = get_connection()
    cursor = conn.cursor()

    # 防止重复运行是重复插入同一段文档
    cursor.execute("DELETE FROM knowledge_chunks WHERE source = ?", (SOURCE_PATH,))

    for chunk in chunks:
        embedding = embedding_manager.embed(chunk)
        embedding_text = json.dumps(embedding)

        cursor.execute(
            """
            INSERT INTO knowledge_chunks (content, embedding, source)
            VALUES (?, ?, ?)
            """,
            (chunk, embedding_text, SOURCE_PATH),
        )
    conn.commit()
    cursor.close()
    conn.close()


def search_knowledge(query, embedding_manager, top_k=3):
    query_embedding = embedding_manager.embed(query)

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
        score = cosine_similarity(query_embedding, chunk_embedding)
        scored.append((score, row))
    scored.sort(key=lambda x: x[0], reverse=True)
    cursor.close()
    connection.close()

    return scored[:top_k]


loader = DocumentLoader()

text = loader.load(SOURCE_PATH)

chunker = Chunker(chunk_size=500)

chunks = chunker.split(text)
print(f"共分成 {len(chunks)} 段")

embedding_manager = EmbeddingManager()

save_knowledge_chunks(chunks, embedding_manager)

query = "黑卡会员需要多少星值？有什么权益?"

results = search_knowledge(query, embedding_manager)

print("问题:")
print(query)
print()
print("检索结果:")
for score, row in results:
    print("相似度:", score)
    print("来源:", row[1])
    print("文本:")
    print(row[0])

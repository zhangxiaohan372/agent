# 用户提出问题 → 转 embedding → 去知识库找最相关 chunk → 返回结果
from pathlib import Path
from memory.embedding_manager import EmbeddingManager
from .init_knowledge import InitKnowledge
from database.vector_db import get_or_create_collection

class KnowledgeManager:
    def __init__(self, source_path=None):
        self.embedding_manager = EmbeddingManager()
        self.init_knowledge = InitKnowledge()
        self.collection = get_or_create_collection("knowledge_chunks")
        self.source_path = source_path
        
        # 自动入库检查：如果提供了知识库文件且 Chroma 为空，自动入库
        if self.source_path and Path(self.source_path).exists():
            if self.collection.count() == 0:
                print(f"[知识库] 检测到 Chroma 集合为空，正在自动入库: {self.source_path}")
                self.init_knowledge.ingest_file(self.source_path)
                print(f"[知识库] 入库完成，当前切片数: {self.collection.count()}")

    # search方法
    def search(self, query, top_k=3, document_id=None):
        # 1. 用户问题转向量
        query_embedding = self.embedding_manager.embed(query)

        # 2. 如果指定了 document_id，则只在该文档的 chunk 中搜索，否则在所有 chunk 中搜索
        
        where_clause = None
        if document_id is not None:
            where_clause = {"document_id": document_id}
            
        # 3. 让 Chroma 在底层通过 HNSW 索引极速检索
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where_clause,
            include=["documents", "metadatas", "distances"]
        )
        
        # 4. 将 Chroma 的返回格式整理成你之前习惯的 dict
        scored = []
        if (
            results
            and results["documents"]
            and results["metadatas"]
            and results["distances"]
        ):
            docs = results["documents"][0]
            metas = results["metadatas"][0]
            distances = results["distances"][0]
            for doc, meta, dist in zip(docs, metas, distances):
                # 如果索引用的 cosine，Chroma 返回的 distance 是 余弦距离 (1 - 余弦相似度)
                # 余弦距离（Cosine Distance）=1−余弦相似度（Cosine Similarity）
                similarity_score = 1 - dist 
                scored.append({
                    "document_id": meta.get("document_id"),
                    "content": doc,
                    "source": meta.get("source"),
                    "score": similarity_score,
                })
        return scored

    def ingest_text(self, text, source="user_input", title=None):
        return self.init_knowledge.ingest_text(text, source=source, title=title)

import chromadb
from pathlib import Path

CHROMA_DATA_DIR = Path(__file__).parent.parent.parent / "data" / "chroma"

def get_chroma_client():
    """获取本地持久化的 ChromaDB 客户端
    """
    CHROMA_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path = str(CHROMA_DATA_DIR))

def get_or_create_collection(name:str):
    
    """获取或创建集合
    metadata={"hnsw:space": "cosine"} 指定底层索引使用余弦距离
    （默认是 l2 欧氏距离，RAG 通常用 cosine）"""
    
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=name,
        metadata = {"hnsw:space": "cosine"}
    )
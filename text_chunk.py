from dotenv import load_dotenv

load_dotenv()

from document_loader import DocumentLoader
from chunker import Chunker
from memory.embedding_manager import EmbeddingManager


loader = DocumentLoader()


text = loader.load("knowledge/vue3.md")


chunker = Chunker(chunk_size=500)


chunks = chunker.split(text)


embedding_manager = EmbeddingManager()


for chunk in chunks:
    vector = embedding_manager.embed(chunk)

    print("文本:")
    print(chunk)

    print("向量长度:")
    print(len(vector))

    break

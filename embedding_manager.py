import os

from dashscope import TextEmbedding

# 先设定一下一次回答只只有一句话，只需要设定一个向量
class EmbeddingManager:
    def __init__(self):
        pass

    def embed(self, text):
        response = TextEmbedding.call(
            model="text-embedding-v3",
            input=text,
            api_key=os.getenv("DASHSCOPE_API_KEY"),
        )

        if response.status_code != 200:
            raise Exception(response)

        embedding = response.output["embeddings"][0]["embedding"]

        return embedding

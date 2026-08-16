#添加overlap
class Chunker:
    def __init__(self,chunk_size=500,over_lap=100):
        self.chunk_size = chunk_size
        self.over_lap = over_lap
    def split(self,text):

        chunks = []
        start = 0

        while start < len(text):
            end = start + self.chunk_size
            if end > len(text):
                end = len(text)
                chunk = text[start:]
                chunks.append(chunk)
                break
            chunk = text[start:end]

            chunks.append(chunk)

            start = end - self.over_lap

        return chunks
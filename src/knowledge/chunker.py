import re


class Chunker:
    """Split text on semantic boundaries before falling back to fixed windows."""

    def __init__(self, chunk_size=500, overlap=80):
        if chunk_size <= 0:
            raise ValueError("chunk_size must be greater than zero")
        if not 0 <= overlap < chunk_size:
            raise ValueError("overlap must be between zero and chunk_size")

        self.chunk_size = chunk_size
        self.overlap = overlap

    def split(self, text):
        text = self._normalize(text)
        if not text:
            return []

        chunks = []
        current = ""
        for unit in self._split_units(text):
            if len(unit) > self.chunk_size:
                if current:
                    chunks.append(current.strip())
                    current = ""
                chunks.extend(self._hard_split(unit))
                continue

            if not current:
                current = unit
                continue

            if len(current) + len(unit) + 1 <= self.chunk_size:
                current += "\n" + unit
                continue

            chunks.append(current.strip())
            remaining_space = self.chunk_size - len(unit) - 1
            overlap_text = self._get_overlap(current, remaining_space)
            current = f"{overlap_text}\n{unit}".strip() if overlap_text else unit

        if current:
            chunks.append(current.strip())
        return chunks

    @staticmethod
    def _normalize(text):
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def _split_units(text):
        units = []
        for paragraph in re.split(r"\n\s*\n+", text):
            paragraph = re.sub(r"\s*\n\s*", " ", paragraph).strip()
            if not paragraph:
                continue
            units.extend(
                sentence.strip()
                for sentence in re.findall(r"[^。！？；]+[。！？；]?", paragraph)
                if sentence.strip()
            )
        return units

    def _hard_split(self, text):
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            chunks.append(text[start:end].strip())
            if end == len(text):
                break
            start = end - self.overlap
        return chunks

    # 接收“要被提取重叠的旧文本（text）”以及“新块中还能塞多少字的预算（remaining_space）”。
    def _get_overlap(self, text, remaining_space):
        if remaining_space <= 0 or self.overlap == 0:
            return ""
        overlap_length = min(self.overlap, remaining_space)
        return text[-overlap_length:].strip()

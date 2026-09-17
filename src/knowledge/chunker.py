#添加overlap
import re
class Chunker:
    def __init__(self,chunk_size=500,over_lap=100):
        self.chunk_size = chunk_size
        self.over_lap = over_lap
    def split(self,text):
        text = self._normalize(text)
        if not text:
            return []
        
        units = self._split_units(text)
        chunks = []
        current = ""
        
        for unit in units:
            # 判断当前句子的字符长度（len(unit)）是否大于系统预设的每个块的最大限制（self.chunk_size）。
            if len(unit) > self.chunk_size:
                if current:
                    chunks.append(current.strip())
                    current = ""
                
                chunks.extend(self._hard_split(unit))
        
    def _normalize(self,text):
        #作用：这行代码把所有的 Windows 换行符（\r\n）和旧 Mac 换行符（\r）全部替换成标准的 Linux 换行符（\n），避免后续处理时出现兼容性问题。
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        #利用刚学到的 re 模块，把文本中连续的多个空格或 Tab（制表符 \t）压缩成单个半角空格。
        text = re.sub(r"[ \t]+", " ", text)
        #它会把这些多余的空行“压扁”，最多只保留两个换行符（即 一个空行 \n\n），让文章段落看起来紧凑，不会有大片空白。
        text = re.sub(r"\n{3,}", "\n\n", text)
        #去掉整个字符串最开头和最结尾多余的空格、换行符或 Tab。
        return text.strip()
    
    def _split_units(self, text):
        units = []

        # 先按空行分段
        paragraphs = re.split(r"\n\s*\n+", text)

        for paragraph in paragraphs:
            paragraph = re.sub(r"\s*\n\s*", " ", paragraph).strip()
            if not paragraph:
                continue

            # 再按中文句末标点切分，保留标点
            #这是 Python 正则表达式的一个方法，作用是查找字符串中所有符合规则的匹配项，
            sentences = re.findall(r"[^。！？；]+[。！？；]?", paragraph)
            units.extend(sentence.strip() for sentence in sentences if sentence.strip())

        return units
    
    # 强行拆分 
    def _hard_split(self, text):
        chunks = []
        start = 0
        # 在此文本长度之内都会循环，直到将整个文本拆分完毕为止。
        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            chunks.append(text[start:end].strip())

            if end == len(text):
                break

            start = end - self.over_lap

        return chunks
    def _get_overlap(self,text,max_length):
        if max_length <= 0 or self.over_lap == 0:
            return ""
        
        length = min(self.over_lap,max_length)
        return text[-length:].strip()
# 负责读取文件，把文件变成字符串。
class DocumentLoader:
    def load(self,path):

        with open(
            path,
            'r',
            encoding='utf-8'
        )as file:
            return file.read()
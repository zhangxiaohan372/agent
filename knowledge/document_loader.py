class DocumentLoader:

    def load(self,path):
        path = str(path)
        suffix = path.split('.')[-1]

        if suffix in ['md','txt','doc','docx']:
            return self._load_text(path)
        else:
            raise ValueError(f"Unsupported file type: {suffix}")

    def _load_text(self,path):
        with open(path,'r',encoding='utf-8') as file:
            return file.read()
# 文本输出测试
from document_loader import DocumentLoader

loader = DocumentLoader()

text = loader.load(
    "knowledge/vue3.md"
)

print(text)
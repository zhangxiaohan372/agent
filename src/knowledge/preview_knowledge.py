"""Preview local Markdown chunking without embedding or database writes."""

from pathlib import Path

from knowledge.chunker import Chunker
from knowledge.document_loader import DocumentLoader


def preview(paths: list[Path]) -> None:
    loader = DocumentLoader()
    chunker = Chunker()
    for path in paths:
        chunks = chunker.split(loader.load(path))
        lengths = [len(chunk) for chunk in chunks]
        short_count = sum(length < 50 for length in lengths)
        print(
            f"{path.name}: chunks={len(chunks)}, min={min(lengths, default=0)}, "
            f"max={max(lengths, default=0)}, under_50={short_count}"
        )


if __name__ == "__main__":
    knowledge_dir = Path(__file__).resolve().parents[2] / "knowledge_document"
    files = sorted(knowledge_dir.glob("0[1-4]_*.md"))
    preview(files)

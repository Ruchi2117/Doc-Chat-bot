import hashlib
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

import chromadb
import docx2txt
from PyPDF2 import PdfReader
from settings import resolve_path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class TextChunk:
    id: str
    content: str
    metadata: dict


class DocumentProcessor:
    """Render-friendly vector indexing with Chroma's ONNX MiniLM embeddings."""

    def __init__(
        self,
        data_dir: Optional[Union[str, Path]] = None,
        vectorstore_path: Optional[Union[str, Path]] = None,
        embedding_model: Optional[str] = None,
        device: Optional[str] = None,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ):
        self.data_dir = Path(data_dir) if data_dir else resolve_path("DOCUMENTS_DIR", "documents")
        self.vectorstore_path = Path(vectorstore_path) if vectorstore_path else resolve_path("VECTORSTORE_PATH", "vectorstore")
        self.collection_name = os.getenv("CHROMA_COLLECTION", "doc_chatbot")
        self.chunk_size = int(os.getenv("CHUNK_SIZE", str(chunk_size)))
        self.chunk_overlap = int(os.getenv("CHUNK_OVERLAP", str(chunk_overlap)))

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.vectorstore_path.mkdir(parents=True, exist_ok=True)

    def _collection(self):
        client = chromadb.PersistentClient(path=str(self.vectorstore_path))
        return client.get_or_create_collection(name=self.collection_name)

    def process_document(self, file_path: Path) -> list[TextChunk]:
        """Load a document and split it into chunks ready for Chroma."""
        if not file_path or not file_path.exists():
            return []

        suffix = file_path.suffix.lower()
        if suffix not in {".txt", ".md", ".pdf", ".docx"}:
            logger.info("Skipping unsupported file type: %s", file_path)
            return []

        logger.info("Processing document: %s", file_path)
        text = self._extract_text(file_path)
        if not text.strip():
            return []

        chunks = []
        for index, content in enumerate(self._chunk_text(text)):
            chunk_id = hashlib.sha1(
                f"{file_path.name}:{index}:{content}".encode("utf-8")
            ).hexdigest()
            chunks.append(
                TextChunk(
                    id=chunk_id,
                    content=content,
                    metadata={
                        "source": file_path.name,
                        "path": str(file_path),
                        "chunk": index,
                    },
                )
            )

        logger.info("Added %s chunks from %s", len(chunks), file_path.name)
        return chunks

    def process_documents(self) -> list[TextChunk]:
        documents = []
        for file_path in self.data_dir.glob("**/*"):
            if file_path.is_file():
                documents.extend(self.process_document(file_path))
        return documents

    def update_vectorstore(self, documents: list[TextChunk]):
        if not documents:
            logger.warning("No documents to index")
            return

        collection = self._collection()
        collection.upsert(
            ids=[doc.id for doc in documents],
            documents=[doc.content for doc in documents],
            metadatas=[doc.metadata for doc in documents],
        )
        logger.info("Indexed %s chunks in Chroma at %s", len(documents), self.vectorstore_path)

    def create_vectorstore_from_documents(self, documents: list[TextChunk]):
        self.update_vectorstore(documents)

    def _extract_text(self, file_path: Path) -> str:
        suffix = file_path.suffix.lower()

        if suffix in {".txt", ".md"}:
            return file_path.read_text(encoding="utf-8", errors="ignore")

        if suffix == ".pdf":
            reader = PdfReader(str(file_path))
            return "\n\n".join(page.extract_text() or "" for page in reader.pages)

        if suffix == ".docx":
            return docx2txt.process(str(file_path)) or ""

        return ""

    def _chunk_text(self, text: str) -> list[str]:
        normalized = "\n".join(line.strip() for line in text.splitlines())
        normalized = "\n".join(line for line in normalized.splitlines() if line)

        if len(normalized) <= self.chunk_size:
            return [normalized]

        chunks = []
        start = 0
        text_length = len(normalized)

        while start < text_length:
            end = min(start + self.chunk_size, text_length)
            if end < text_length:
                paragraph_break = normalized.rfind("\n", start, end)
                sentence_break = normalized.rfind(". ", start, end)
                split_at = max(paragraph_break, sentence_break)
                if split_at > start + self.chunk_size // 2:
                    end = split_at + 1

            chunk = normalized[start:end].strip()
            if chunk:
                chunks.append(chunk)

            if end >= text_length:
                break

            next_start = end - self.chunk_overlap
            start = max(next_start, end) if next_start <= start else next_start

        return chunks


def main():
    processor = DocumentProcessor()
    if not list(processor.data_dir.glob("**/*")):
        logger.warning("No documents found in %s", processor.data_dir)
        return

    documents = processor.process_documents()
    processor.create_vectorstore_from_documents(documents)


if __name__ == "__main__":
    main()

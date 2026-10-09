"""Document ingestion, text extraction, and chunking utilities."""

from __future__ import annotations

__all__ = [
    "Chunk",
    "extract_text",
    "chunk_text",
]

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Chunk:
    """A segment of extracted document text for auditing."""
    text: str
    index: int = 0
    page_number: Optional[int] = None
    metadata: dict[str, Any] = field(default_factory=dict)


def extract_text(file_content: bytes, mime_type: str) -> str:
    """Extract plain text from uploaded document bytes."""
    if not file_content:
        return ""
    
    try:
        if mime_type == "application/pdf":
            import pypdf
            import io
            reader = pypdf.PdfReader(io.BytesIO(file_content))
            return "\n".join([page.extract_text() or "" for page in reader.pages])
        elif mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            import docx
            import io
            doc = docx.Document(io.BytesIO(file_content))
            return "\n".join([para.text for para in doc.paragraphs])
    except Exception:
        pass

    try:
        return file_content.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def chunk_text(text: str, chunk_size: int = 4000, overlap: int = 200) -> list[Chunk]:
    """Split text into manageable chunks with overlap."""
    if not text:
        return []
    
    chunks = []
    start = 0
    length = len(text)
    index = 0

    while start < length:
        end = min(start + chunk_size, length)
        chunk_str = text[start:end]
        chunks.append(Chunk(text=chunk_str, index=index))
        if end == length:
            break
        start = end - overlap
        index += 1

    return chunks

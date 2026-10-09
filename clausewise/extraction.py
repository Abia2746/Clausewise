"""Document ingestion and text extraction pipeline for PDF, DOCX, and TXT files."""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Optional

from .errors import ExtractionFailed, UnsupportedDocument

@dataclass(frozen=True)
class ExtractedDocument:
    filename: str
    text: str
    char_count: int
    word_count: int
    page_count: int
    is_scanned: bool = False

def extract_text_from_pdf(content: bytes) -> tuple[str, int]:
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(content))
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        text = "\n\n".join(pages).strip()
        return text, len(reader.pages)
    except Exception as exc:
        raise ExtractionFailed(f"Could not read PDF document: {exc}") from exc

def extract_text_from_docx(content: bytes) -> tuple[str, int]:
    try:
        import docx
        doc = docx.Document(io.BytesIO(content))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        for table in doc.tables:
            for row in table.rows:
                row_txt = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                if row_txt:
                    paragraphs.append(row_txt)
        text = "\n".join(paragraphs).strip()
        return text, 1
    except Exception as exc:
        raise ExtractionFailed(f"Could not read Word document: {exc}") from exc

def extract_text(filename: str, content: bytes, mime_type: str = "") -> ExtractedDocument:
    if not content:
        raise UnsupportedDocument("File content is empty.")

    page_count = 1
    if mime_type == "application/pdf" or filename.lower().endswith(".pdf"):
        text, page_count = extract_text_from_pdf(content)
    elif mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document" or filename.lower().endswith(".docx"):
        text, page_count = extract_text_from_docx(content)
    else:
        try:
            text = content.decode("utf-8", errors="replace").strip()
        except Exception as exc:
            raise ExtractionFailed("Could not decode plain text file.") from exc

    if not text:
        raise ExtractionFailed("No readable text could be extracted from the document.")

    words = len(text.split())
    is_scanned = words < 20 and page_count > 0

    return ExtractedDocument(
        filename=filename,
        text=text,
        char_count=len(text),
        word_count=words,
        page_count=page_count,
        is_scanned=is_scanned,
    )

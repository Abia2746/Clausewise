"""Document ingestion and text extraction utilities."""

from __future__ import annotations

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
    # Fallback decoder for text or basic formats
    try:
        return file_content.decode("utf-8", errors="ignore")
    except Exception:
        return ""

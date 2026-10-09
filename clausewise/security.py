"""Security primitives: hashing, tokens, encryption, upload validation, rate limits.

Design notes
------------
* Passwords use `hashlib.scrypt` from the standard library — memory-hard, no
  native build step, no dependency that can break a bank's build pipeline.
* Session tokens and API keys are stored as SHA-256 hashes, so a database
  dump does not hand an attacker live credentials.
* Contract text at rest is encrypted with Fernet when DATA_ENCRYPTION_KEY is set.
* Upload validation is by magic bytes, not by file extension.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import get_settings
from .errors import DocumentTooLarge, RateLimited, UnsupportedDocument

# --------------------------------------------------------------------- hashing
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32


def hash_password(password: str, *, salt: Optional[str] = None) -> tuple[str, str]:
    """Return (hash_hex, salt_hex)."""
    salt_bytes = bytes.fromhex(salt) if salt else os.urandom(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt_bytes, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_SCRYPT_DKLEN
    )
    return digest.hex(), salt_bytes.hex()


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    if not password_hash or not salt:
        return False
    candidate, _ = hash_password(password, salt=salt)
    return hmac.compare_digest(candidate, password_hash)


def password_problems(password: str) -> list[str]:
    """Return policy violations. Enterprise buyers ask what the policy is."""
    problems: list[str] = []
    if len(password) < 12:
        problems.append("Password must be at least 12 characters.")
    if not re.search(r"[A-Z]", password):
        problems.append("Add at least one uppercase letter.")
    if not re.search(r"[a-z]", password):
        problems.append("Add at least one lowercase letter.")
    if not re.search(r"\d", password):
        problems.append("Add at least one digit.")
    return problems


# ---------------------------------------------------------------------- tokens
def new_token(prefix: str = "") -> str:
    return f"{prefix}{secrets.token_urlsafe(32)}"


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def slugify(value: str, max_length: int = 60) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return (slug or "tenant")[:max_length]


# ------------------------------------------------------------------ encryption
def _fernet():
    key = get_settings().data_encryption_key
    if not key:
        return None
    try:
        from cryptography.fernet import Fernet
    except Exception:  # pragma: no cover - cryptography is in requirements
        return None
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception:
        return None


def encrypt_text(plaintext: str) -> Optional[str]:
    """Encrypt for storage. Returns None when no key is configured."""
    f = _fernet()
    if f is None:
        return None
    return f.encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_text(ciphertext: str) -> Optional[str]:
    f = _fernet()
    if f is None:
        return None
    try:
        return f.decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except Exception:
        return None


# ------------------------------------------------------------ upload validation
_MAGIC = {
    b"%PDF-": "application/pdf",
    b"PK\x03\x04": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

# Files whose real-world metaphor is not a contract. Rejected on sight.
_BLOCKED_EXTENSIONS = {".exe", ".dll", ".so", ".bat", ".sh", ".js", ".html", ".zip", ".rar", ".7z"}


@dataclass(frozen=True)
class ValidatedUpload:
    filename: str
    safe_filename: str
    mime_type: str
    size_bytes: int
    content: bytes


def sanitize_filename(filename: str) -> str:
    name = Path(filename or "contract").name
    name = re.sub(r"[^\w\s.\-()]", "_", name).strip()
    name = re.sub(r"\s+", " ", name)
    return (name or "contract")[:200]


def validate_upload(filename: str, content: bytes, *, declared_mime: str = "") -> ValidatedUpload:
    settings = get_settings()

    ext = Path(filename or "").suffix.lower()
    if ext in _BLOCKED_EXTENSIONS:
        raise UnsupportedDocument(f"The file type {ext} is not accepted. Upload a PDF, DOCX or plain text.")

    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise DocumentTooLarge(
            f"That file is {len(content) / 1_048_576:.1f} MB. The limit is {settings.max_upload_mb} MB per document."
        )
    if not content:
        raise UnsupportedDocument("That file appears to be empty.")

    mime = ""
    for magic, detected in _MAGIC.items():
        if content.startswith(magic):
            mime = detected
            break

    if not mime:
        if ext in {".txt", ".md", ".text"}:
            mime = "text/plain"
        else:
            raise UnsupportedDocument(
                "We could not read that file. Upload a .pdf, .docx or paste the contract text directly."
            )

    # NOTE: `declared_mime` is accepted for logging and diagnostics only. It is
    # deliberately NOT used to decide the type: browsers report DOCX uploads as
    # application/zip, application/octet-stream or an empty string depending on
    # platform, so the magic bytes above are the only trustworthy signal.

    return ValidatedUpload(
        filename=filename or "contract",
        safe_filename=sanitize_filename(filename),
        mime_type=mime,
        size_bytes=len(content),
        content=content,
    )


# ---------------------------------------------------------------- rate limiting
class RateLimiter:
    """In-process sliding window.

    Correct for a single Streamlit container or a single API worker. For a
    horizontally scaled deployment, swap the backing store for Redis — the
    interface is deliberately the same three methods.
    """

    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, *, cost: int = 1) -> None:
        now = time.monotonic()
        window = self._hits[key]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) + cost > self.per_minute:
            retry_after = int(60 - (now - window[0])) if window else 60
            raise RateLimited(
                f"Rate limit reached ({self.per_minute} requests/minute). Retry in about {max(retry_after, 1)}s.",
                retry_after=max(retry_after, 1),
            )
        window.extend([now] * cost)

    def remaining(self, key: str) -> int:
        now = time.monotonic()
        window = self._hits[key]
        while window and now - window[0] > 60:
            window.popleft()
        return max(self.per_minute - len(window), 0)

    def reset(self, key: Optional[str] = None) -> None:
        if key is None:
            self._hits.clear()
        else:
            self._hits.pop(key, None)


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")

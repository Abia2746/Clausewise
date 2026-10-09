"""Application-specific exceptions for Clausewise."""

from __future__ import annotations


class ClauseWiseError(Exception):
    """Base exception for all Clausewise errors."""
    pass


class AuthError(ClauseWiseError):
    """Raised when authentication or token validation fails."""
    pass


class PermissionDenied(ClauseWiseError):
    """Raised when an operation is not permitted for the user/tenant."""
    pass


class ProviderError(ClauseWiseError):
    """Raised when an LLM provider fails or returns an error."""
    pass


class RateLimitError(ProviderError):
    """Raised when an LLM provider hits rate limits."""
    pass


class DocumentTooLarge(ClauseWiseError):
    """Raised when an uploaded document exceeds size limits."""
    pass


class ExtractionFailed(ClauseWiseError):
    """Raised when text extraction from a file fails."""
    pass


class UnsupportedDocument(ClauseWiseError):
    """Raised when the document MIME type is not supported."""
    pass


class FeatureLocked(ClauseWiseError):
    """Raised when a feature requires a higher tier plan."""
    def __init__(self, message: str, feature: str | None = None, upgrade_target: str | None = None):
        super().__init__(message)
        self.feature = feature
        self.upgrade_target = upgrade_target


class QuotaExceeded(ClauseWiseError):
    """Raised when a usage quota is exhausted."""
    def __init__(self, message: str, upgrade_target: str | None = None, limit: int | None = None, used: int | None = None):
        super().__init__(message)
        self.upgrade_target = upgrade_target
        self.limit = limit
        self.used = used

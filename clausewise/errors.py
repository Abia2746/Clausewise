"""Application-specific exceptions for Clausewise."""

from __future__ import annotations


class ClausewiseError(Exception):
    """Base exception for all Clausewise errors."""
    pass


ClauseWiseError = ClausewiseError


class AuthError(ClausewiseError):
    """Raised when authentication or token validation fails."""
    pass


class PermissionDenied(ClausewiseError):
    """Raised when an operation is not permitted for the user/tenant."""
    pass


class AuditRefused(ClausewiseError):
    """Raised when an audit is refused due to policy or state."""
    pass


class ProviderError(ClausewiseError):
    """Raised when an LLM provider fails or returns an error."""
    pass


class RateLimitError(ProviderError):
    """Raised when an LLM provider hits rate limits."""
    pass


RateLimited = RateLimitError


class DocumentTooLarge(ClausewiseError):
    """Raised when an uploaded document exceeds size limits."""
    pass


class ExtractionFailed(ClausewiseError):
    """Raised when text extraction from a file fails."""
    pass


class UnsupportedDocument(ClausewiseError):
    """Raised when the document MIME type is not supported."""
    pass


class FeatureLocked(ClausewiseError):
    """Raised when a feature requires a higher tier plan."""
    def __init__(self, message: str, feature: str | None = None, upgrade_target: str | None = None):
        super().__init__(message)
        self.feature = feature
        self.upgrade_target = upgrade_target


class QuotaExceeded(ClausewiseError):
    """Raised when a usage quota is exhausted."""
    def __init__(self, message: str, upgrade_target: str | None = None, limit: int | None = None, used: int | None = None):
        super().__init__(message)
        self.upgrade_target = upgrade_target
        self.limit = limit
        self.used = used

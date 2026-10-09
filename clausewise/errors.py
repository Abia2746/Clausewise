"""Typed errors.

Every error that can reach a customer carries a user-facing `message` and, where
relevant, an `upgrade_target` — because in this product an error screen is
frequently a conversion surface.

Subclasses declare `default_code` and `http_status` as class attributes rather
than passing them through `super().__init__`, which keeps the inheritance chain
from colliding on keyword arguments as it deepens.
"""

from __future__ import annotations

from typing import Any, Optional


class ClausewiseError(Exception):
    """Base class. `message` is safe to render in the UI."""

    http_status: int = 400
    default_code: str = "error"

    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        detail: Optional[dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code or self.default_code
        self.detail = detail or {}

    def to_dict(self) -> dict[str, Any]:
        return {"error": self.code, "message": self.message, "detail": self.detail}


class ConfigurationError(ClausewiseError):
    """The deployment is misconfigured. Operator problem, not user problem."""

    http_status = 500
    default_code = "configuration_error"


# ------------------------------------------------------------------------- auth
class AuthError(ClausewiseError):
    http_status = 401
    default_code = "unauthenticated"

    def __init__(self, message: str = "Not authenticated.", **kw: Any):
        super().__init__(message, **kw)


class PermissionDenied(ClausewiseError):
    http_status = 403
    default_code = "forbidden"

    def __init__(self, message: str = "Your role does not allow this action.", **kw: Any):
        super().__init__(message, **kw)


class RateLimited(ClausewiseError):
    http_status = 429
    default_code = "rate_limited"

    def __init__(self, message: str = "Too many requests. Please slow down.", *, retry_after: int = 60, **kw: Any):
        super().__init__(message, **kw)
        self.retry_after = retry_after


# ----------------------------------------------------------- commercial / plans
class QuotaExceeded(ClausewiseError):
    """A monthly allowance ran out. Always carries the next plan up."""

    http_status = 402
    default_code = "quota_exceeded"

    def __init__(
        self,
        message: str,
        *,
        upgrade_target: Optional[str] = None,
        limit: Optional[int] = None,
        used: Optional[int] = None,
        **kw: Any,
    ):
        super().__init__(message, **kw)
        self.upgrade_target = upgrade_target
        self.limit = limit
        self.used = used

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data["upgrade_target"] = self.upgrade_target
        data["limit"] = self.limit
        data["used"] = self.used
        return data


class FeatureLocked(ClausewiseError):
    """A capability is not in the current plan."""

    http_status = 402
    default_code = "feature_locked"

    def __init__(self, message: str, *, feature: str, upgrade_target: Optional[str] = None, **kw: Any):
        super().__init__(message, **kw)
        self.feature = feature
        self.upgrade_target = upgrade_target

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data["feature"] = self.feature
        data["upgrade_target"] = self.upgrade_target
        return data


class BudgetExceeded(ClausewiseError):
    """Platform-level model spend guardrail tripped."""

    http_status = 503
    default_code = "budget_exceeded"

    def __init__(self, message: str = "The review service is temporarily paused for maintenance.", **kw: Any):
        super().__init__(message, **kw)


# ------------------------------------------------------------ document pipeline
class UnsupportedDocument(ClausewiseError):
    default_code = "unsupported_document"

    def __init__(self, message: str, **kw: Any):
        super().__init__(message, **kw)


class DocumentTooLarge(ClausewiseError):
    default_code = "document_too_large"

    def __init__(self, message: str, **kw: Any):
        super().__init__(message, **kw)


class ExtractionFailed(ClausewiseError):
    default_code = "extraction_failed"

    def __init__(self, message: str, **kw: Any):
        super().__init__(message, **kw)


# ------------------------------------------------------------------ model layer
class ProviderError(ClausewiseError):
    """The model call itself failed after retries."""

    http_status = 502
    default_code = "provider_error"


class ProviderTimeout(ProviderError):
    default_code = "provider_timeout"

    def __init__(self, message: str = "The review engine timed out. Please retry.", **kw: Any):
        super().__init__(message, **kw)


class InvalidModelOutput(ProviderError):
    """The model returned something that does not validate against the schema."""

    default_code = "invalid_model_output"

    def __init__(self, message: str = "The review engine returned an unreadable result.", **kw: Any):
        super().__init__(message, **kw)


class AuditRefused(ClausewiseError):
    """Deliberate refusal. Correct behaviour, not a failure.

    Raised when the engine cannot reach the confidence floor or the document is
    outside the supported scope. Surfaced to the user as a referral to their
    Shari'ah board.
    """

    http_status = 200
    default_code = "audit_refused"

    def __init__(self, message: str, *, reason: str = "low_confidence", **kw: Any):
        super().__init__(message, **kw)
        self.reason = reason

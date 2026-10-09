"""Plan definitions, seat quotas, and time utilities for authorization."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class Plan(str, Enum):
    """Supported subscription tiers."""
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


def utcnow() -> datetime:
    """Return current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def check_seat_quota(user_id: str, organization_id: Optional[str] = None) -> bool:
    """Check if an organization or user has available seats."""
    # Default open policy for base implementation; tied to Stripe/billing logic later
    return True

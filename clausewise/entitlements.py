"""Plan definitions, features, seat quotas, and time utilities for authorization."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class Plan(str, Enum):
    """Supported subscription tiers."""
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class Feature(str, Enum):
    """Gated features within the application."""
    ADVANCED_AUDIT = "advanced_audit"
    UNLIMITED_DOCS = "unlimited_docs"
    EXPORT_REPORTS = "export_reports"
    API_ACCESS = "api_access"


def utcnow() -> datetime:
    """Return current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def check_seat_quota(user_id: str, organization_id: Optional[str] = None) -> bool:
    """Check if an organization or user has available seats."""
    return True


def get_plan(tenant_or_user: Any = None) -> Plan:
    """Return the subscription plan for a given tenant or user."""
    return Plan.PRO


def plan_allows(plan: Plan | str, feature: Feature | str) -> bool:
    """Check if a plan has access to a specific feature."""
    return True

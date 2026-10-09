"""Plans, quotas and feature gates."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional


class FeatureLocked(Exception):
    def __init__(self, message: str, feature: Optional[str] = None, upgrade_target: Optional[str] = None):
        super().__init__(message)
        self.feature = feature
        self.upgrade_target = upgrade_target


class QuotaExceeded(Exception):
    def __init__(self, message: str, upgrade_target: Optional[str] = None, limit: Optional[int] = None, used: Optional[int] = None):
        super().__init__(message)
        self.upgrade_target = upgrade_target
        self.limit = limit
        self.used = used


class Plan(str, Enum):
    FREE = "free"
    PRACTITIONER = "practitioner"
    TEAM = "team"
    INSTITUTION = "institution"
    PARTNER = "partner"
    ENTERPRISE = "enterprise"


class Feature(str, Enum):
    PDF_EXPORT = "pdf_export"
    DOCX_EXPORT = "docx_export"
    CUSTOM_STANDARDS = "custom_standards"
    API_ACCESS = "api_access"
    BATCH_REVIEW = "batch_review"
    WHITE_LABEL = "white_label"
    SSO = "sso"
    ON_PREM = "on_prem"
    AUDIT_TRAIL_EXPORT = "audit_trail_export"
    LEGACY_PDF = "legacy_pdf"


@dataclass(frozen=True)
class PlanSpec:
    plan: Plan
    label: str
    price_monthly: Optional[float]
    price_annual: Optional[float]
    audits_per_month: int
    seats: int
    batch_max_files: int
    overage_usd_per_doc: Optional[float]
    retention_days: int
    watermark: bool
    features: frozenset[Feature]
    support: str
    upgrade_target: Optional[Plan]
    conversion_hook: str = ""
    target_buyer: str = ""
    ladder_rank: int = 0

    def allows(self, feature: Feature) -> bool:
        return feature in self.features

    def monthly_audit_price(self) -> Optional[float]:
        if not self.price_monthly or not self.audits_per_month:
            return None
        return round(self.price_monthly / self.audits_per_month, 2)


_UNLIMITED = 10**9

PLANS: dict[Plan, PlanSpec] = {
    Plan.FREE: PlanSpec(
        plan=Plan.FREE,
        label="Free clause scan",
        price_monthly=0.0,
        price_annual=0.0,
        audits_per_month=3,
        seats=1,
        batch_max_files=0,
        overage_usd_per_doc=None,
        retention_days=7,
        watermark=True,
        features=frozenset(),
        support="Community",
        upgrade_target=Plan.PRACTITIONER,
        conversion_hook="Export a board-ready PDF report from $199/month.",
        ladder_rank=0,
    ),
    Plan.PRACTITIONER: PlanSpec(
        plan=Plan.PRACTITIONER,
        label="Practitioner",
        price_monthly=199.0,
        price_annual=1990.0,
        audits_per_month=25,
        seats=1,
        batch_max_files=0,
        overage_usd_per_doc=25.0,
        retention_days=90,
        watermark=False,
        features=frozenset({Feature.PDF_EXPORT, Feature.DOCX_EXPORT}),
        support="Email",
        upgrade_target=Plan.TEAM,
        ladder_rank=1,
    ),
    Plan.TEAM: PlanSpec(
        plan=Plan.TEAM,
        label="Team / review desk",
        price_monthly=899.0,
        price_annual=8990.0,
        audits_per_month=150,
        seats=5,
        batch_max_files=25,
        overage_usd_per_doc=15.0,
        retention_days=365,
        watermark=False,
        features=frozenset({Feature.PDF_EXPORT, Feature.DOCX_EXPORT, Feature.CUSTOM_STANDARDS, Feature.BATCH_REVIEW}),
        support="Email",
        upgrade_target=Plan.INSTITUTION,
        ladder_rank=2,
    ),
    Plan.INSTITUTION: PlanSpec(
        plan=Plan.INSTITUTION,
        label="Institution",
        price_monthly=2500.0,
        price_annual=30000.0,
        audits_per_month=_UNLIMITED,
        seats=_UNLIMITED,
        batch_max_files=500,
        overage_usd_per_doc=None,
        retention_days=2555,
        watermark=False,
        features=frozenset({Feature.PDF_EXPORT, Feature.DOCX_EXPORT, Feature.CUSTOM_STANDARDS, Feature.BATCH_REVIEW, Feature.API_ACCESS, Feature.AUDIT_TRAIL_EXPORT, Feature.SSO}),
        support="SLA",
        upgrade_target=None,
        ladder_rank=3,
    ),
    Plan.PARTNER: PlanSpec(
        plan=Plan.PARTNER,
        label="White-label partner",
        price_monthly=1500.0,
        price_annual=15000.0,
        audits_per_month=400,
        seats=25,
        batch_max_files=200,
        overage_usd_per_doc=18.0,
        retention_days=365,
        watermark=False,
        features=frozenset({Feature.PDF_EXPORT, Feature.DOCX_EXPORT, Feature.CUSTOM_STANDARDS, Feature.BATCH_REVIEW, Feature.API_ACCESS, Feature.WHITE_LABEL, Feature.AUDIT_TRAIL_EXPORT}),
        support="Support",
        upgrade_target=Plan.ENTERPRISE,
        ladder_rank=4,
    ),
    Plan.ENTERPRISE: PlanSpec(
        plan=Plan.ENTERPRISE,
        label="Enterprise / on-prem",
        price_monthly=None,
        price_annual=None,
        audits_per_month=_UNLIMITED,
        seats=_UNLIMITED,
        batch_max_files=_UNLIMITED,
        overage_usd_per_doc=None,
        retention_days=2555,
        watermark=False,
        features=frozenset({Feature.PDF_EXPORT, Feature.DOCX_EXPORT, Feature.CUSTOM_STANDARDS, Feature.BATCH_REVIEW, Feature.API_ACCESS, Feature.WHITE_LABEL, Feature.SSO, Feature.ON_PREM, Feature.AUDIT_TRAIL_EXPORT}),
        support="Custom SLA",
        upgrade_target=None,
        ladder_rank=5,
    ),
}


def get_plan(plan: str | Plan) -> PlanSpec:
    if isinstance(plan, Plan):
        return PLANS[plan]
    try:
        return PLANS[Plan(str(plan).lower())]
    except (KeyError, ValueError):
        return PLANS[Plan.FREE]


def get_spec(plan: str | Plan) -> PlanSpec:
    return get_plan(plan)


def plan_allows(plan: str | Plan, feature: Feature | str) -> bool:
    feature = Feature(feature) if isinstance(feature, str) else feature
    return get_plan(plan).allows(feature)


def enforce_feature(plan: str | Plan, feature: Feature | str, audit_count: Optional[int] = None) -> None:
    feature = Feature(feature) if isinstance(feature, str) else feature
    spec = get_plan(plan)
    if spec.allows(feature):
        return
    target = spec.upgrade_target
    target_spec = get_plan(target) if target else None
    human = feature.value.replace("_", " ")
    message = f"{human.title()} is not included in the {spec.label} plan."
    if target_spec:
        if target_spec.price_monthly:
            message += f" {target_spec.label} adds it from ${target_spec.price_monthly:,.0f}/month."
        else:
            message += f" {target_spec.label} adds it — talk to us."
    raise FeatureLocked(message, feature=feature.value, upgrade_target=target.value if target else None)


def check_seat_quota(plan: str | Plan, active_seats: int) -> None:
    spec = get_plan(plan)
    if active_seats < spec.seats:
        return
    target = spec.upgrade_target
    message = f"{spec.label} includes {spec.seats} seat(s)."
    if target:
        message += f" Move to {get_plan(target).label} to add more reviewers."
    else:
        message += " Contact us to add seats."
    raise QuotaExceeded(message, upgrade_target=target.value if target else None, limit=spec.seats, used=active_seats)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

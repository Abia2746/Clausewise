"""Plans, quotas and feature gates.

This module is the commercial brain of the product. Two rules shape it:

1. **A block is a sales moment.** Every refusal returns the next plan up, the
   reason in the buyer's language, and a concrete call to action. `QuotaExceeded`
   and `FeatureLocked` are rendered as upgrade cards, not error text.
2. **Limits live in code, not in a pricing page someone forgot to update.**
   The marketing table, the paywall copy and the enforcement all read from the
   same `PlanSpec`, so they cannot drift.

Price points reflect the current positioning: value-priced against the 4-10
hours of qualified reviewer time each audit replaces, not against model cost.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from .errors import FeatureLocked, QuotaExceeded


class Plan(str, Enum):
    FREE = "free"
    PRACTITIONER = "practitioner"
    TEAM = "team"
    INSTITUTION = "institution"
    PARTNER = "partner"       # white-label: an advisory firm reselling to clients
    ENTERPRISE = "enterprise"  # negotiated institution+ terms


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
    #: USD per month, or None for "contact us"
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
    #: shown at the moment of the block — this is the conversion copy
    conversion_hook: str = ""
    target_buyer: str = ""
    #: 0-based position in the public pricing ladder
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
        conversion_hook="You are trialling the engine. Export a board-ready PDF report from $199/month.",
        target_buyer="Anyone evaluating the engine — not a revenue tier.",
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
        support="Email, 2 business days",
        upgrade_target=Plan.TEAM,
        conversion_hook="You are at the volume where a Team plan is cheaper than overages.",
        target_buyer="Solo Shari'ah consultants and boutique Islamic finance practices.",
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
        features=frozenset(
            {
                Feature.PDF_EXPORT,
                Feature.DOCX_EXPORT,
                Feature.CUSTOM_STANDARDS,
                Feature.BATCH_REVIEW,
            }
        ),
        support="Email + shared channel, next business day",
        upgrade_target=Plan.INSTITUTION,
        conversion_hook="Add your own SSB resolutions as a custom standard library, plus API access.",
        target_buyer="Islamic fintechs, takaful operators and halal lenders — their product IS the contract.",
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
        features=frozenset(
            {
                Feature.PDF_EXPORT,
                Feature.DOCX_EXPORT,
                Feature.CUSTOM_STANDARDS,
                Feature.BATCH_REVIEW,
                Feature.API_ACCESS,
                Feature.AUDIT_TRAIL_EXPORT,
                Feature.SSO,
            }
        ),
        support="Named contact, 4-hour response, SLA",
        upgrade_target=None,
        conversion_hook="In-region deployment and on-prem are available on negotiated terms.",
        target_buyer="Islamic banks, Islamic windows, large advisory and audit firms.",
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
        features=frozenset(
            {
                Feature.PDF_EXPORT,
                Feature.DOCX_EXPORT,
                Feature.CUSTOM_STANDARDS,
                Feature.BATCH_REVIEW,
                Feature.API_ACCESS,
                Feature.WHITE_LABEL,
                Feature.AUDIT_TRAIL_EXPORT,
            }
        ),
        support="Named contact, next business day",
        upgrade_target=Plan.ENTERPRISE,
        conversion_hook="Your brand on the report, your clients in their own workspaces.",
        target_buyer="Shari'ah advisory and audit firms — one firm is an entire client book.",
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
        features=frozenset(
            {
                Feature.PDF_EXPORT,
                Feature.DOCX_EXPORT,
                Feature.CUSTOM_STANDARDS,
                Feature.BATCH_REVIEW,
                Feature.API_ACCESS,
                Feature.WHITE_LABEL,
                Feature.SSO,
                Feature.ON_PREM,
                Feature.AUDIT_TRAIL_EXPORT,
            }
        ),
        support="Named contact, contractual SLA, on-prem support",
        upgrade_target=None,
        conversion_hook="",
        target_buyer="Regulated institutions and sovereign bodies requiring in-country processing.",
        ladder_rank=5,
    ),
}

ADDONS: list[dict] = [
    {
        "code": "overage",
        "label": "Additional audits",
        "price": "$15–$25 per document",
        "detail": "Beyond your monthly allowance. Billed automatically; no renegotiation.",
    },
    {
        "code": "api",
        "label": "API / metered access",
        "price": "$1.50–$5.00 per document",
        "detail": "Insert a pre-signature compliance gate into your own origination flow.",
    },
    {
        "code": "custom_library",
        "label": "Custom standard library build",
        "price": "$2,500–$10,000 one-time",
        "detail": "We encode your SSB resolutions, Shari'ah audit manual and jurisdiction rulebook.",
    },
    {
        "code": "audit_pack",
        "label": "Annual Shari'ah audit pack",
        "price": "$5,000–$15,000 per year",
        "detail": "Bulk review of the year's templates ahead of the external Shari'ah audit.",
    },
    {
        "code": "scholar",
        "label": "Scholar escalation",
        "price": "$150–$400 per escalation",
        "detail": "Route flagged clauses to a contracted qualified Shari'ah reviewer.",
    },
]

PRICING_LADDER: list[dict] = [
    {
        "plan": spec.plan.value,
        "label": spec.label,
        "price_monthly": spec.price_monthly,
        "price_annual": spec.price_annual,
        "audits_per_month": spec.audits_per_month,
        "seats": spec.seats,
        "per_audit": spec.monthly_audit_price(),
        "target_buyer": spec.target_buyer,
        "support": spec.support,
        "features": sorted(f.value for f in spec.features),
        "watermark": spec.watermark,
    }
    for spec in sorted(PLANS.values(), key=lambda s: s.ladder_rank)
]


class QuotaState(str, Enum):
    OK = "ok"
    WARNING = "warning"
    BLOCKED = "blocked"
    UNLIMITED = "unlimited"


@dataclass
class QuotaDecision:
    state: QuotaState
    used: int
    limit: int
    remaining: int
    percent_used: float
    message: str
    upgrade_target: Optional[Plan] = None
    cta_label: str = ""

    @property
    def allowed(self) -> bool:
        return self.state in {QuotaState.OK, QuotaState.WARNING, QuotaState.UNLIMITED}

    def to_dict(self) -> dict:
        d = asdict(self)
        d["state"] = self.state.value
        d["upgrade_target"] = self.upgrade_target.value if self.upgrade_target else None
        return d


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
    message += f" {spec.conversion_hook}".rstrip()
    raise FeatureLocked(message, feature=feature.value, upgrade_target=target.value if target else None)


def check_audit_quota(plan: str | Plan, used_this_period: int) -> QuotaDecision:
    spec = get_plan(plan)
    limit = spec.audits_per_month

    if limit >= _UNLIMITED:
        return QuotaDecision(
            state=QuotaState.UNLIMITED,
            used=used_this_period,
            limit=limit,
            remaining=_UNLIMITED,
            percent_used=0.0,
            message="Unlimited reviews included in your plan.",
        )

    used = max(used_this_period, 0)
    remaining = max(limit - used, 0)
    pct = round((used / limit) * 100, 1) if limit else 100.0

    if remaining <= 0:
        target = spec.upgrade_target
        cta = "Upgrade plan"
        message = f"You have used all {limit} reviews in this billing period."
        if spec.overage_usd_per_doc:
            message += (
                f" You can keep working at ${spec.overage_usd_per_doc:,.0f} per extra document,"
                " or move up for a lower effective rate."
            )
            cta = "Review options"
        elif target:
            message += f" Move to {get_plan(target).label} to continue."
        else:
            message += " Contact us to raise this allowance."
        return QuotaDecision(
            state=QuotaState.BLOCKED,
            used=used,
            limit=limit,
            remaining=0,
            percent_used=100.0,
            message=message,
            upgrade_target=target,
            cta_label=cta,
        )

    if pct >= 80.0 or remaining <= 1:
        target = spec.upgrade_target
        return QuotaDecision(
            state=QuotaState.WARNING,
            used=used,
            limit=limit,
            remaining=remaining,
            percent_used=pct,
            message=f"{remaining} of {limit} reviews left this period.",
            upgrade_target=target,
            cta_label=f"Compare {get_plan(target).label}" if target else "",
        )

    return QuotaDecision(
        state=QuotaState.OK,
        used=used,
        limit=limit,
        remaining=remaining,
        percent_used=pct,
        message=f"{remaining} of {limit} reviews left this period.",
    )


def enforce_audit_quota(plan: str | Plan, used_this_period: int) -> QuotaDecision:
    decision = check_audit_quota(plan, used_this_period)
    if not decision.allowed:
        raise QuotaExceeded(
            decision.message,
            upgrade_target=decision.upgrade_target.value if decision.upgrade_target else None,
            limit=decision.limit,
            used=decision.used,
        )
    return decision


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


def check_batch_quota(plan: str | Plan, requested_files: int) -> int:
    spec = get_plan(plan)
    if not spec.allows(Feature.BATCH_REVIEW):
        enforce_feature(plan, Feature.BATCH_REVIEW)
    if requested_files > spec.batch_max_files:
        raise QuotaExceeded(
            f"{spec.label} allows up to {spec.batch_max_files} documents per batch; you submitted {requested_files}.",
            upgrade_target=spec.upgrade_target.value if spec.upgrade_target else None,
            limit=spec.batch_max_files,
            used=requested_files,
        )
    return requested_files


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def period_bounds(now: Optional[datetime] = None) -> tuple[datetime, datetime]:
    now = now or utcnow()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


def retention_expiry(plan: str | Plan, *, tenant_override_days: Optional[int] = None) -> datetime:
    days = tenant_override_days if tenant_override_days is not None else get_plan(plan).retention_days
    return utcnow() + timedelta(days=days)


def upgrade_cta_block(plan: str | Plan, blocker: str = "") -> dict:
    spec = get_plan(plan)
    target = spec.upgrade_target
    if target is None:
        return {
            "headline": "Talk to us about a tailored arrangement",
            "body": "We can widen allowances, deployment region or on-prem terms.",
            "cta": "Book a 20-minute call",
            "blocker": blocker,
        }
    target_spec = get_plan(target)
    if target_spec.price_monthly:
        price = f"${target_spec.price_monthly:,.0f}/month"
    else:
        price = "custom pricing"
    return {
        "headline": f"Move to {target_spec.label} — {price}",
        "body": target_spec.conversion_hook or target_spec.target_buyer,
        "cta": f"Upgrade to {target_spec.label}",
        "blocker": blocker,
        "target_plan": target.value,
    }

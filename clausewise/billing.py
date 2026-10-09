"""Subscription billing.

Two providers behind one interface:

- `StripeBilling` — checkout sessions, webhook reconciliation, plan sync.
- `ManualBilling` — the default. Records the plan on the tenant and lets an
operator or partner agreement provision it. Pilot deals close faster with a
purchase order than with a payment link.

The rule this module exists to enforce: **plan state is written in exactly one
place (`sync_plan`)**, whether it arrives from a webhook, an admin action, or a
partner agreement. Nothing else may set `Tenant.plan`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.orm import Session

from .config import get_settings
from .entitlements import Plan, get_plan
from .errors import ConfigurationError, PermissionDenied
from .models import Tenant, User
from .repository import log_event

@dataclass
class CheckoutResult:
    url: Optional[str]
    provider: str
    message: str
    pending_plan: Optional[str] = None

def sync_plan(
    session: Session,
    *,
    tenant: Tenant,
    plan: Plan | str,
    source: str = "manual",
    acting_user: Optional[User] = None,
    subscription_id: Optional[str] = None,
    current_period_end: Optional[Any] = None,
    note: str = "",
) -> Tenant:
    """The single writer of `Tenant.plan`."""
    target = plan if isinstance(plan, Plan) else Plan(str(plan).lower())
    previous = tenant.plan
    tenant.plan = target.value
    if subscription_id:
        tenant.billing_subscription_id = subscription_id
    if current_period_end:
        tenant.current_period_end = current_period_end

    log_event(
        session,
        action="billing.plan_changed",
        tenant_id=tenant.id,
        actor_user_id=acting_user.id if acting_user else None,
        actor_label=acting_user.email if acting_user else source,
        object_type="tenant",
        object_id=tenant.id,
        meta={"from": previous, "to": target.value, "source": source, "note": note},
    )
    session.flush()
    return tenant

class ManualBilling:
    """Default provider. No external dependency, no webhook to misconfigure."""

    name = "manual"

    def start_checkout(self, *, tenant: Tenant, plan: Plan | str, interval: str = "monthly") -> CheckoutResult:
        spec = get_plan(plan)
        price = spec.price_annual if interval == "annual" else spec.price_monthly
        if price is None:
            return CheckoutResult(
                url=get_settings().sales_calendar_url or None,
                provider=self.name,
                message=f"{spec.label} is priced on scope. Book a call and we will issue a quote.",
            )
        return CheckoutResult(
            url=None,
            provider=self.name,
            pending_plan=spec.plan.value,
            message=(
                f"{spec.label} at ${price:,.0f}/{interval}. We will send an invoice and activate the plan "
                "as soon as it is settled - no card required for pilots."
            ),
        )

class StripeBilling:
    """Stripe checkout + reconciliation."""

    name = "stripe"

    def __init__(self) -> None:
        self.settings = get_settings()
        if not self.settings.stripe_secret_key:
            raise ConfigurationError("STRIPE_SECRET_KEY is not configured.")

    def _stripe(self):
        try:
            import stripe
        except ImportError as exc:
            raise ConfigurationError("The stripe package is not installed in this deployment.") from exc
        stripe.api_key = self.settings.stripe_secret_key
        return stripe

    def start_checkout(self, *, tenant: Tenant, plan: Plan | str, interval: str = "monthly") -> CheckoutResult:
        stripe = self._stripe()
        spec = get_plan(plan)
        price_key = f"{spec.plan.value}_{interval}"
        price_id = self.settings.stripe_prices.get(price_key, "")

        if not price_id:
            return CheckoutResult(
                url=self.settings.sales_calendar_url or None,
                provider=self.name,
                message=f"No self-serve price configured for {spec.label}. Contact sales.",
                pending_plan=spec.plan.value,
            )

        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            customer=tenant.billing_customer_id or None,
            customer_email=None if tenant.billing_customer_id else None,
            client_reference_id=tenant.id,
            success_url=f"{self.settings.app_base_url}/?billing=success",
            cancel_url=f"{self.settings.app_base_url}/?billing=cancelled",
            metadata={"tenant_id": tenant.id, "plan": spec.plan.value},
            subscription_data={"metadata": {"tenant_id": tenant.id, "plan": spec.plan.value}},
        )
        return CheckoutResult(
            url=session.get("url"),
            provider=self.name,
            message="Complete checkout to activate the plan.",
            pending_plan=spec.plan.value,
        )

    def handle_webhook(self, session: Session, payload: bytes, signature: str) -> dict[str, Any]:
        """Reconcile a Stripe event into plan state."""
        stripe = self._stripe()
        try:
            event = stripe.Webhook.construct_event(
                payload, signature, self.settings.stripe_webhook_secret
            )
        except Exception as exc:
            raise PermissionDenied(f"Invalid webhook signature: {exc}")

        event_type = event["type"]
        obj = event["data"]["object"]
        handled = False

        if event_type == "checkout.session.completed":
            tenant_id = (obj.get("metadata") or {}).get("tenant_id") or obj.get("client_reference_id")
            plan = (obj.get("metadata") or {}).get("plan")
            tenant = session.get(Tenant, tenant_id) if tenant_id else None
            if tenant and plan:
                if obj.get("customer"):
                    tenant.billing_customer_id = obj["customer"]
                sync_plan(
                    session,
                    tenant=tenant,
                    plan=plan,
                    source="stripe.checkout.completed",
                    subscription_id=obj.get("subscription"),
                )
                handled = True

        elif event_type in {"customer.subscription.updated", "customer.subscription.deleted"}:
            subscription_id = obj.get("id")
            tenant = (
                session.query(Tenant)
                .filter(Tenant.billing_subscription_id == subscription_id)
                .one_or_none()
            )
            if tenant:
                status = obj.get("status")
                if event_type.endswith("deleted") or status in {"canceled", "unpaid", "incomplete_expired"}:
                    sync_plan(session, tenant=tenant, plan=Plan.FREE, source=f"stripe.{status}")
                else:
                    plan = (obj.get("metadata") or {}).get("plan") or tenant.plan
                    sync_plan(session, tenant=tenant, plan=plan, source="stripe.subscription.updated")
                tenant.billing_status = status
                handled = True

        session.flush()
        return {"event": event_type, "handled": handled}

def get_billing():
    settings = get_settings()
    if settings.billing_enabled and settings.stripe_secret_key:
        try:
            return StripeBilling()
        except ConfigurationError:
            return ManualBilling()
    return ManualBilling()

def billing_enabled() -> bool:
    return isinstance(get_billing(), StripeBilling)

def overage_estimate(tenant: Tenant, extra_documents: int) -> dict[str, Any]:
    """Show the marginal cost of more volume, and where it stops making sense."""
    spec = get_plan(tenant.plan)
    if spec.overage_usd_per_doc is None:
        return {"applicable": False, "message": "Your plan has no per-document overage; volume is included."}
    cost = spec.overage_usd_per_doc * extra_documents
    upgrade_note = ""
    if spec.upgrade_target:
        target = get_plan(spec.upgrade_target)
        if target.price_monthly and target.audits_per_month:
            implied = target.price_monthly / max(target.audits_per_month, 1)
            if implied < spec.overage_usd_per_doc:
                upgrade_note = (
                    f"At this volume {target.label} is cheaper per document "
                    f"(${implied:,.2f} vs${spec.overage_usd_per_doc:,.2f})."
                )
    return {
        "applicable": True,
        "documents": extra_documents,
        "unit_price": spec.overage_usd_per_doc,
        "estimated_cost": round(cost, 2),
        "upgrade_note": upgrade_note,
    }

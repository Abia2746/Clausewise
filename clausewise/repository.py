"""Persistence and orchestration.

This is the only module that writes to the database. Every public function
takes a `tenant_id` (or a `Tenant`) as its first argument after the session, so
omitting the tenant filter is a visible omission in review rather than an
invisible one at runtime.

`execute_audit` is the orchestrator the UI, the API and the batch worker all
call. One code path means one set of quota, cache, metering and audit-trail
semantics, regardless of surface.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .audit_engine import AuditOutcome, run_audit
from .config import PROMPT_VERSION, STANDARDS_REGISTRY_VERSION, get_settings
from .entitlements import (
    Feature,
    Plan,
    QuotaDecision,
    check_audit_quota,
    enforce_audit_quota,
    enforce_feature,
    period_bounds,
    retention_expiry,
    utcnow,
)
from .errors import PermissionDenied, QuotaExceeded
from .extraction import ExtractedDocument, extract_document
from .models import (
    ApiKey,
    Audit,
    AuditCache,
    AuditLogEntry,
    Contract,
    Finding,
    LeadCapture,
    StandardLibrary,
    Tenant,
    UsageEvent,
    User,
)
from .providers import LLMProvider, provider_health
from .security import encrypt_text, sha256_bytes
from .standards import global_library_id

# ================================================================== small helpers
def resolve_library(session: Session, tenant: Tenant, requested_id: Optional[str]) -> Optional[str]:
    """Pick the library to score against.

    Order: explicitly requested (if the tenant may use it) -> the tenant's own
    default -> the global AAOIFI library. A tenant may never load another
    tenant's library, which is the one access-control mistake that would be
    commercially fatal here.
    """
    if requested_id:
        library = session.get(StandardLibrary, requested_id)
        if library and (library.tenant_id in (None, tenant.id)):
            if library.tenant_id is not None:
                enforce_feature(tenant.plan, Feature.CUSTOM_STANDARDS)
            return library.id
    own_default = (
        session.query(StandardLibrary)
        .filter(
            StandardLibrary.tenant_id == tenant.id,
            StandardLibrary.is_default_for_tenant.is_(True),
            StandardLibrary.is_active.is_(True),
        )
        .one_or_none()
    )
    if own_default:
        enforce_feature(tenant.plan, Feature.CUSTOM_STANDARDS)
        return own_default.id
    return global_library_id()

def usage_this_period(session: Session, tenant_id: str, *, kind: str = "audit") -> int:
    start, _ = period_bounds()
    total = (
        session.query(func.coalesce(func.sum(UsageEvent.quantity), 0))
        .filter(
            UsageEvent.tenant_id == tenant_id,
            UsageEvent.kind == kind,
            UsageEvent.created_at >= start,
        )
        .scalar()
    )
    return int(total or 0)

def quota_decision_for(session: Session, tenant: Tenant) -> QuotaDecision:
    return check_audit_quota(tenant.plan, usage_this_period(session, tenant.id))

def record_usage(
    session: Session,
    *,
    tenant_id: str,
    kind: str,
    user_id: Optional[str] = None,
    quantity: int = 1,
    audit_id: Optional[str] = None,
    meta: Optional[dict] = None,
) -> UsageEvent:
    event = UsageEvent(
        tenant_id=tenant_id,
        user_id=user_id,
        kind=kind,
        quantity=quantity,
        audit_id=audit_id,
        meta=meta or {},
    )
    session.add(event)
    return event

def log_event(
    session: Session,
    *,
    action: str,
    tenant_id: Optional[str] = None,
    actor_user_id: Optional[str] = None,
    actor_label: str = "",
    object_type: str = "",
    object_id: str = "",
    ip_address: str = "",
    user_agent: str = "",
    meta: Optional[dict] = None,
) -> AuditLogEntry:
    entry = AuditLogEntry(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        actor_label=actor_label,
        action=action,
        object_type=object_type,
        object_id=object_id,
        ip_address=ip_address,
        user_agent=user_agent,
        meta=meta or {},
    )
    session.add(entry)
    return entry

# ==================================================================== tenancy
def get_tenant(session: Session, tenant_id: str) -> Optional[Tenant]:
    return session.get(Tenant, tenant_id)

def get_tenant_by_slug(session: Session, slug: str) -> Optional[Tenant]:
    return session.query(Tenant).filter(Tenant.slug == slug).one_or_none()

def create_tenant(
    session: Session,
    *,
    name: str,
    slug: str,
    plan: Plan | str = Plan.FREE,
    is_white_label: bool = False,
    brand_name: Optional[str] = None,
    partner_tenant_id: Optional[str] = None,
    data_region: str = "global",
) -> Tenant:
    plan_value = plan.value if isinstance(plan, Plan) else str(plan)
    tenant = Tenant(
        name=name,
        slug=slug,
        plan=plan_value,
        is_white_label=is_white_label,
        brand_name=brand_name,
        partner_tenant_id=partner_tenant_id,
        data_region=data_region,
    )
    session.add(tenant)
    session.flush()
    return tenant

def tenant_branding(tenant: Tenant) -> dict[str, str]:
    """Brand resolution for reports and the UI, including white-label partners."""
    settings = get_settings()
    if tenant.is_white_label and tenant.brand_name:
        return {
            "name": tenant.brand_name,
            "accent": tenant.brand_accent or settings.brand_accent,
            "footer": tenant.report_footer or "",
            "powered_by": "" if tenant.brand_name else settings.brand_name,
        }
    return {
        "name": tenant.brand_name or settings.brand_name,
        "accent": tenant.brand_accent or settings.brand_accent,
        "footer": tenant.report_footer or "",
        "powered_by": "",
    }

# ================================================================== contracts
@dataclass
class DocumentInput:
    """Everything the engine needs, already validated and extracted."""

    filename: str
    content: bytes
    mime_type: str
    text: str
    document_type: str = "general"
    page_count: int = 0
    char_count: int = 0
    truncated: bool = False
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def from_bytes(cls, filename: str, content: bytes, *, mime_type: str) -> "DocumentInput":
        from .security import validate_upload

        validated = validate_upload(filename, content, declared_mime=mime_type)
        extracted: ExtractedDocument = extract_document(
            validated.content, filename=validated.filename, mime_type=validated.mime_type
        )
        return cls(
            filename=validated.filename,
            content=validated.content,
            mime_type=validated.mime_type,
            text=extracted.text,
            document_type=extracted.document_type,
            page_count=extracted.page_count,
            char_count=extracted.char_count,
            truncated=extracted.truncated,
            warnings=list(extracted.warnings),
        )

    @classmethod
    def from_text(cls, text: str, *, filename: str = "Pasted contract text") -> "DocumentInput":
        from .extraction import detect_document_type

        return cls(
            filename=filename,
            content=text.encode("utf-8"),
            mime_type="text/plain",
            text=text,
            document_type=detect_document_type(text),
            page_count=0,
            char_count=len(text),
        )

def create_contract(session: Session, tenant: Tenant, document: DocumentInput, *, user_id: Optional[str] = None) -> Contract:
    settings = get_settings()
    store_text = settings.store_document_text or tenant.store_document_text

    contract = Contract(
        tenant_id=tenant.id,
        uploaded_by=user_id,
        filename=document.filename,
        safe_filename=document.filename,
        document_type=document.document_type,
        mime_type=document.mime_type,
        size_bytes=len(document.content),
        page_count=document.page_count,
        char_count=document.char_count,
        content_sha256=sha256_bytes(document.content),
        extraction_warnings={"warnings": document.warnings} if document.warnings else None,
        retention_expires_at=retention_expiry(tenant.plan, tenant_override_days=tenant.retention_days),
    )
    if store_text:
        contract.encrypted_text = encrypt_text(document.text)
    session.add(contract)
    session.flush()
    return contract

# ===================================================================== caching
def _lookup_cached_audit(
    session: Session, tenant: Tenant, contract: Contract, library_id: Optional[str]
) -> Optional[Audit]:
    settings = get_settings()
    if not (settings.cache_identical_documents and tenant.plan not in {Plan.FREE.value}):
        return None

    entry = (
        session.query(AuditCache)
        .filter(
            AuditCache.tenant_id == tenant.id,
            AuditCache.content_sha256 == contract.content_sha256,
            AuditCache.prompt_version == PROMPT_VERSION,
            AuditCache.standards_version == STANDARDS_REGISTRY_VERSION,
            AuditCache.library_id == (library_id or "global"),
        )
        .order_by(AuditCache.created_at.desc())
        .first()
    )
    if entry is None:
        return None
    cached = session.get(Audit, entry.audit_id)
    if cached is None or cached.status != "succeeded":
        return None
    return cached

def _store_cache_entry(session: Session, tenant: Tenant, contract: Contract, audit: Audit, library_id: Optional[str]) -> None:
    session.add(
        AuditCache(
            tenant_id=tenant.id,
            content_sha256=contract.content_sha256,
            prompt_version=PROMPT_VERSION,
            standards_version=STANDARDS_REGISTRY_VERSION,
            library_id=library_id or "global",
            audit_id=audit.id,
        )
    )

def _clone_from_cache(session: Session, tenant: Tenant, contract: Contract, cached: Audit, *, user_id: Optional[str]) -> Audit:
    """Reuse a prior result for an identical document."""
    clone = Audit(
        tenant_id=tenant.id,
        contract_id=contract.id,
        requested_by=user_id,
        library_id=cached.library_id,
        status="succeeded",
        provider=cached.provider,
        model=cached.model,
        prompt_version=cached.prompt_version,
        standards_version=cached.standards_version,
        temperature=cached.temperature,
        redaction_applied=cached.redaction_applied,
        source_label="cache",
        overall_summary=(
            f"{cached.overall_summary} "
            "[Identical document reviewed previously; this result was reused rather than re-run.]"
        ).strip(),
        risk_status=cached.risk_status,
        risk_score=cached.risk_score,
        findings_total=cached.findings_total,
        findings_critical=cached.findings_critical,
        findings_high=cached.findings_high,
        findings_medium=cached.findings_medium,
        findings_advisory=cached.findings_advisory,
        findings_referred=cached.findings_referred,
        confidence=cached.confidence,
        needs_human_review=True,
        review_reason=cached.review_reason,
        chunks_total=cached.chunks_total,
        tokens_in=0,
        tokens_out=0,
        cost_usd=0.0,
        latency_ms=0,
        cache_hit=True,
        started_at=utcnow(),
        finished_at=utcnow(),
    )
    session.add(clone)
    session.flush()

    for source in session.query(Finding).filter(Finding.audit_id == cached.id).all():
        session.add(
            Finding(
                audit_id=clone.id,
                tenant_id=tenant.id,
                ordinal=source.ordinal,
                clause_ref=source.clause_ref,
                clause_excerpt=source.clause_excerpt,
                issue_type=source.issue_type,
                severity=source.severity,
                standard_id=source.standard_id,
                standard_title=source.standard_title,
                citation_ref=source.citation_ref,
                citation_status=source.citation_status,
                rationale=source.rationale,
                remedial_wording=source.remedial_wording,
                confidence=source.confidence,
                needs_human_review=source.needs_human_review,
                detected_by=source.detected_by,
            )
        )
    session.flush()
    return clone

# ================================================================= the orchestrator
def execute_audit(
    session: Session,
    *,
    tenant: Tenant,
    document: DocumentInput,
    user_id: Optional[str] = None,
    library_id: Optional[str] = None,
    jurisdiction: str = "GLOBAL",
    source_label: str = "upload",
    provider: Optional[LLMProvider] = None,
    idempotency_key: Optional[str] = None,
    ip_address: str = "",
    user_agent: str = "",
    enforce_quota: bool = True,
) -> Audit:
    """Run one review end to end: quota -> cache -> engine -> persist -> meter."""
    settings = get_settings()

    if idempotency_key:
        existing = (
            session.query(Audit)
            .filter(Audit.tenant_id == tenant.id, Audit.idempotency_key == idempotency_key)
            .one_or_none()
        )
        if existing is not None:
            return existing

    if enforce_quota:
        enforce_audit_quota(tenant.plan, usage_this_period(session, tenant.id))

    resolved_library = resolve_library(session, tenant, library_id)
    contract = create_contract(session, tenant, document, user_id=user_id)

    cached = _lookup_cached_audit(session, tenant, contract, resolved_library)
    if cached is not None:
        clone = _clone_from_cache(session, tenant, contract, cached, user_id=user_id)
        record_usage(
            session,
            tenant_id=tenant.id,
            kind="audit",
            user_id=user_id,
            quantity=0,
            audit_id=clone.id,
            meta={"cache_hit": True, "source_audit": cached.id},
        )
        log_event(
            session,
            action="audit.cache_hit",
            tenant_id=tenant.id,
            actor_user_id=user_id,
            object_type="audit",
            object_id=clone.id,
            ip_address=ip_address,
            user_agent=user_agent,
            meta={"filename": contract.filename},
        )
        return clone

    from .providers import get_provider

    active_provider = provider or get_provider(tenant.llm_provider_override)

    audit = Audit(
        tenant_id=tenant.id,
        contract_id=contract.id,
        requested_by=user_id,
        library_id=resolved_library,
        status="running",
        provider=active_provider.name,
        model=settings.active_model,
        prompt_version=PROMPT_VERSION,
        standards_version=STANDARDS_REGISTRY_VERSION,
        temperature=settings.llm_temperature,
        source_label=source_label,
        idempotency_key=idempotency_key,
        started_at=utcnow(),
    )
    session.add(audit)
    session.flush()

    started = time.perf_counter()
    try:
        outcome: AuditOutcome = run_audit(
            document.text,
            provider=active_provider,
            document_type=document.document_type,
            library_id=resolved_library,
            jurisdiction=jurisdiction,
            truncated=document.truncated,
        )
    except Exception as exc:
        audit.status = "failed"
        audit.error = str(exc)[:2000]
        audit.finished_at = utcnow()
        audit.latency_ms = int((time.perf_counter() - started) * 1000)
        session.flush()
        log_event(
            session,
            action="audit.failed",
            tenant_id=tenant.id,
            actor_user_id=user_id,
            object_type="audit",
            object_id=audit.id,
            ip_address=ip_address,
            user_agent=user_agent,
            meta={"error": str(exc)[:500]},
        )
        raise

    _apply_outcome(audit, outcome)
    audit.finished_at = utcnow()
    audit.latency_ms = int((time.perf_counter() - started) * 1000)
    audit.redaction_applied = bool(outcome.redaction_note and "Redacted" in outcome.redaction_note)
    audit.review_reason = outcome.review_reason or audit.review_reason

    if document.warnings:
        audit.error = " | ".join(document.warnings)[:2000] if outcome.status != "failed" else audit.error

    session.flush()

    for ordinal, finding in enumerate(outcome.findings):
        session.add(
            Finding(
                audit_id=audit.id,
                tenant_id=tenant.id,
                ordinal=ordinal,
                clause_ref=finding.clause_ref,
                clause_excerpt=finding.clause_excerpt,
                issue_type=finding.issue_type,
                severity=finding.severity,
                standard_id=finding.standard_id,
                standard_title=finding.standard_title,
                citation_ref=finding.citation_ref,
                citation_status=finding.citation_status,
                rationale=finding.rationale,
                remedial_wording=finding.remedial_wording,
                confidence=finding.confidence,
                needs_human_review=finding.needs_human_review,
                detected_by=finding.detected_by,
            )
        )

    billable = 1 if outcome.status == "succeeded" else 0
    record_usage(
        session,
        tenant_id=tenant.id,
        kind="audit",
        user_id=user_id,
        quantity=billable,
        audit_id=audit.id,
        meta={
            "status": outcome.status,
            "risk_status": outcome.risk_status,
            "tokens_in": outcome.usage.tokens_in,
            "tokens_out": outcome.usage.tokens_out,
            "cost_usd": audit.cost_usd,
            "provider": outcome.provider,
        },
    )

    if outcome.status == "succeeded":
        _store_cache_entry(session, tenant, contract, audit, resolved_library)

    log_event(
        session,
        action=f"audit.{outcome.status}",
        tenant_id=tenant.id,
        actor_user_id=user_id,
        object_type="audit",
        object_id=audit.id,
        ip_address=ip_address,
        user_agent=user_agent,
        meta={
            "filename": contract.filename,
            "risk_status": outcome.risk_status,
            "findings": audit.findings_total,
            "refusal_reason": outcome.refusal_reason,
        },
    )
    session.flush()
    return audit

def _apply_outcome(audit: Audit, outcome: AuditOutcome) -> None:
    audit.status = outcome.status
    audit.refusal_reason = outcome.refusal_reason
    audit.overall_summary = outcome.summary
    audit.risk_status = outcome.risk_status
    audit.risk_score = outcome.risk_score
    audit.findings_total = sum(
        outcome.counts.get(key, 0)
        for key in ("critical", "high", "medium", "advisory")
    )
    audit.findings_critical = outcome.counts.get("critical", 0)
    audit.findings_high = outcome.counts.get("high", 0)
    audit.findings_medium = outcome.counts.get("medium", 0)
    audit.findings_advisory = outcome.counts.get("advisory", 0)
    audit.findings_referred = outcome.counts.get("referred", 0)
    audit.confidence = outcome.confidence
    audit.needs_human_review = outcome.needs_human_review
    audit.review_reason = outcome.review_reason
    audit.chunks_total = outcome.chunks_total
    audit.chunks_failed = outcome.chunks_failed
    audit.tokens_in = outcome.usage.tokens_in
    audit.tokens_out = outcome.usage.tokens_out
    audit.cost_usd = get_settings().cost_for(outcome.model, outcome.usage.tokens_in, outcome.usage.tokens_out)
    audit.provider = outcome.provider
    audit.model = outcome.model

# ======================================================================= reads
def list_audits(
    session: Session,
    tenant_id: str,
    *,
    limit: int = 200,
    status: Optional[str] = None,
    risk_status: Optional[str] = None,
    remediation_status: Optional[str] = None,
    search: str = "",
) -> list[Audit]:
    query = (
        session.query(Audit)
        .join(Contract, Audit.contract_id == Contract.id)
        .filter(Audit.tenant_id == tenant_id)
    )
    if status:
        query = query.filter(Audit.status == status)
    if risk_status:
        query = query.filter(Audit.risk_status == risk_status)
    if remediation_status:
        query = query.filter(Audit.remediation_status == remediation_status)
    if search:
        like = f"%{search.strip()}%"
        query = query.filter(or_(Contract.filename.ilike(like), Audit.id.ilike(like)))
    return query.order_by(Audit.created_at.desc()).limit(limit).all()

def get_audit(session: Session, tenant_id: str, audit_id: str) -> Optional[Audit]:
    return (
        session.query(Audit)
        .filter(Audit.tenant_id == tenant_id, Audit.id == audit_id)
        .one_or_none()
    )

def get_contract(session: Session, tenant_id: str, contract_id: str) -> Optional[Contract]:
    return (
        session.query(Contract)
        .filter(Contract.tenant_id == tenant_id, Contract.id == contract_id)
        .one_or_none()
    )

def findings_for(session: Session, audit_id: str) -> list[Finding]:
    return (
        session.query(Finding)
        .filter(Finding.audit_id == audit_id)
        .order_by(Finding.ordinal)
        .all()
    )

def portfolio_summary(session: Session, tenant_id: str) -> dict[str, Any]:
    """The figures an institution puts in front of its Shari'ah audit committee."""
    total = session.query(func.count(Audit.id)).filter(Audit.tenant_id == tenant_id).scalar() or 0

    by_risk = dict(
        session.query(Audit.risk_status, func.count(Audit.id))
        .filter(Audit.tenant_id == tenant_id)
        .group_by(Audit.risk_status)
        .all()
    )
    by_severity = dict(
        session.query(Finding.severity, func.count(Finding.id))
        .filter(Finding.tenant_id == tenant_id)
        .group_by(Finding.severity)
        .all()
    )
    by_issue = dict(
        session.query(Finding.issue_type, func.count(Finding.id))
        .filter(Finding.tenant_id == tenant_id)
        .group_by(Finding.issue_type)
        .all()
    )
    open_items = (
        session.query(func.count(Audit.id))
        .filter(Audit.tenant_id == tenant_id, Audit.remediation_status == "open")
        .scalar()
        or 0
    )
    signed_off = (
        session.query(func.count(Audit.id))
        .filter(Audit.tenant_id == tenant_id, Audit.signed_off_at.isnot(None))
        .scalar()
        or 0
    )
    cost = (
        session.query(func.coalesce(func.sum(Audit.cost_usd), 0.0))
        .filter(Audit.tenant_id == tenant_id)
        .scalar()
        or 0.0
    )
    return {
        "audits_total": int(total),
        "by_risk": by_risk,
        "by_severity": by_severity,
        "by_issue": by_issue,
        "open_remediation": int(open_items),
        "signed_off": int(signed_off),
        "internal_cost_usd": round(float(cost), 4),
    }

def audit_log_for(session: Session, tenant_id: str, *, limit: int = 200) -> list[AuditLogEntry]:
    return (
        session.query(AuditLogEntry)
        .filter(AuditLogEntry.tenant_id == tenant_id)
        .order_by(AuditLogEntry.created_at.desc())
        .limit(limit)
        .all()
    )

# ============================================================== reviewer workflow
def set_remediation_status(
    session: Session,
    *,
    tenant: Tenant,
    audit_id: str,
    status: str,
    user_id: Optional[str],
    note: str = "",
) -> Audit:
    audit = get_audit(session, tenant.id, audit_id)
    if audit is None:
        raise PermissionDenied("That review does not belong to this workspace.")
    audit.remediation_status = status
    if note:
        audit.signoff_note = note
    log_event(
        session,
        action="audit.remediation_status",
        tenant_id=tenant.id,
        actor_user_id=user_id,
        object_type="audit",
        object_id=audit_id,
        meta={"status": status},
    )
    return audit

def sign_off_audit(
    session: Session, *, tenant: Tenant, audit_id: str, user_id: str, note: str = ""
) -> Audit:
    """Record a human Shari'ah reviewer's disposition."""
    audit = get_audit(session, tenant.id, audit_id)
    if audit is None:
        raise PermissionDenied("That review does not belong to this workspace.")
    audit.signed_off_by = user_id
    audit.signed_off_at = utcnow()
    audit.signoff_note = note
    audit.remediation_status = "reviewed"
    log_event(
        session,
        action="audit.signed_off",
        tenant_id=tenant.id,
        actor_user_id=user_id,
        object_type="audit",
        object_id=audit_id,
        meta={"note": note[:300]},
    )
    return audit

# ==================================================================== retention
def purge_expired_documents(session: Session, *, tenant_id: Optional[str] = None) -> int:
    """Delete document artefacts past their retention window."""
    now = utcnow()
    query = session.query(Contract).filter(
        Contract.retention_expires_at.isnot(None),
        Contract.retention_expires_at <= now,
        Contract.deleted_at.is_(None),
    )
    if tenant_id:
        query = query.filter(Contract.tenant_id == tenant_id)

    count = 0
    for contract in query.all():
        contract.encrypted_text = None
        contract.storage_path = None
        contract.deleted_at = now
        count += 1
    if count:
        session.flush()
    return count

# ================================================================== lead capture
def capture_lead(
    session: Session,
    *,
    email: str,
    tenant_id: Optional[str] = None,
    full_name: str = "",
    company: str = "",
    segment: str = "",
    intent: str = "demo_request",
    blocker: str = "",
    message: str = "",
) -> LeadCapture:
    """A blocked free user is the warmest lead the product will ever produce."""
    lead = LeadCapture(
        email=email.strip().lower(),
        tenant_id=tenant_id,
        full_name=full_name,
        company=company,
        segment=segment,
        intent=intent,
        blocker=blocker,
        message=message,
    )
    session.add(lead)
    session.flush()
    log_event(
        session,
        action="lead.captured",
        tenant_id=tenant_id,
        actor_label=email,
        object_type="lead",
        object_id=lead.id,
        meta={"intent": intent, "blocker": blocker},
    )
    return lead

def leads(session: Session, *, limit: int = 500) -> list[LeadCapture]:
    return session.query(LeadCapture).order_by(LeadCapture.created_at.desc()).limit(limit).all()

# ============================================================== platform metrics
def platform_metrics(session: Session) -> dict[str, Any]:
    """Admin cockpit: is the machine converting and is it affordable?"""
    total_tenants = session.query(func.count(Tenant.id)).scalar() or 0
    paying = (
        session.query(func.count(Tenant.id))
        .filter(Tenant.plan.notin_([Plan.FREE.value]))
        .scalar()
        or 0
    )
    total_users = session.query(func.count(User.id)).scalar() or 0
    total_audits = session.query(func.count(Audit.id)).scalar() or 0
    month_start, _ = period_bounds()
    audits_this_month = (
        session.query(func.count(Audit.id)).filter(Audit.created_at >= month_start).scalar() or 0
    )
    refused = (
        session.query(func.count(Audit.id)).filter(Audit.status == "refused").scalar() or 0
    )
    failed = session.query(func.count(Audit.id)).filter(Audit.status == "failed").scalar() or 0
    spend = session.query(func.coalesce(func.sum(Audit.cost_usd), 0.0)).scalar() or 0.0
    spend_month = (
        session.query(func.coalesce(func.sum(Audit.cost_usd), 0.0))
        .filter(Audit.created_at >= month_start)
        .scalar()
        or 0.0
    )
    mrr = 0.0
    for tenant in session.query(Tenant).filter(Tenant.plan.notin_([Plan.FREE.value])).all():
        from .entitlements import get_plan

        spec = get_plan(tenant.plan)
        if spec.price_monthly:
            mrr += spec.price_monthly

    return {
        "tenants_total": int(total_tenants),
        "tenants_paying": int(paying),
        "conversion_rate": round((paying / total_tenants) * 100, 1) if total_tenants else 0.0,
        "users_total": int(total_users),
        "audits_total": int(total_audits),
        "audits_this_month": int(audits_this_month),
        "refused_total": int(refused),
        "failed_total": int(failed),
        "model_spend_total_usd": round(float(spend), 4),
        "model_spend_this_month_usd": round(float(spend_month), 4),
        "mrr_usd": round(mrr, 2),
        "gross_margin_estimate": (
            round(100 - (float(spend_month) / mrr) * 100, 1) if mrr > 0 else None
        ),
        "budget_usd": get_settings().global_monthly_budget_usd,
        "budget_utilisation": (
            round((float(spend_month) / get_settings().global_monthly_budget_usd) * 100, 1)
            if get_settings().global_monthly_budget_usd
            else 0.0
        ),
        "provider": provider_health(),
    }

def budget_exceeded(session: Session) -> bool:
    settings = get_settings()
    if not settings.global_monthly_budget_usd:
        return False
    month_start, _ = period_bounds()
    spend = (
        session.query(func.coalesce(func.sum(Audit.cost_usd), 0.0))
        .filter(Audit.created_at >= month_start)
        .scalar()
        or 0.0
    )
    return float(spend) >= settings.global_monthly_budget_usd

def api_keys_for(session: Session, tenant_id: str) -> list[ApiKey]:
    return (
        session.query(ApiKey)
        .filter(ApiKey.tenant_id == tenant_id)
        .order_by(ApiKey.created_at.desc())
        .all()
    )

def libraries_for(session: Session, tenant_id: str) -> list[StandardLibrary]:
    return (
        session.query(StandardLibrary)
        .filter(
            or_(StandardLibrary.tenant_id.is_(None), StandardLibrary.tenant_id == tenant_id),
            StandardLibrary.is_active.is_(True),
        )
        .order_by(StandardLibrary.tenant_id.is_(None).desc(), StandardLibrary.name)
        .all()
    )

def audit_dates(session: Session, tenant_id: str) -> Iterable[datetime]:
    rows = session.query(Audit.created_at).filter(Audit.tenant_id == tenant_id).all()
    return [r[0] for r in rows]

"""FastAPI surface — the metered, integration revenue line.

Design intent: this is the same engine the UI uses, exposed for a bank to insert
a pre-signature Shari'ah compliance gate into its own origination flow. It is
sold from the Institution plan up, metered per document.

    uvicorn api:app --host 0.0.0.0 --port 8000

Authentication is an API key in `X-API-Key`. Every key is scoped; every call is
metered; every call writes an audit-trail entry.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from clausewise import auth
from clausewise.config import get_settings
from clausewise.db import init_db, session_scope
from clausewise.entitlements import Feature, enforce_feature
from clausewise.errors import ClausewiseError
from clausewise.models import ApiKey, Tenant
from clausewise.repository import (
    DocumentInput,
    execute_audit,
    findings_for,
    get_audit,
    log_event,
    portfolio_summary,
    record_usage,
    usage_this_period,
)
from clausewise.security import RateLimiter
from clausewise.standards import STANDARD_INDEX

@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Create the schema and load the standards registry before serving."""
    init_db()
    from clausewise.standards import seed_global_library

    seed_global_library()
    yield


app = FastAPI(
    title="Clausewise Shari'ah API",
    version="2.0.0",
    description=(
        "Assistive Shari'ah contract review. Findings cite the standard relied on and are "
        "explicitly assistive: compliance determinations rest with the client's Shari'ah board."
    ),
    lifespan=lifespan,
)

_limiter = RateLimiter(get_settings().rate_limit_requests_per_minute)


# ================================================================== dependencies
def _tenant_and_key(request: Request, x_api_key: Optional[str] = Header(default=None)) -> tuple[Tenant, ApiKey]:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header.")
    with session_scope() as session:
        resolved = auth.verify_api_key(session, x_api_key)
        if resolved is None:
            raise HTTPException(status_code=401, detail="Invalid, expired or revoked API key.")
        tenant, key = resolved
        _limiter.check(f"key:{key.id}")
        log_event(
            session,
            action="api.request",
            tenant_id=tenant.id,
            object_type="api_key",
            object_id=key.id,
            ip_address=request.client.host if request.client else "",
            user_agent=request.headers.get("user-agent", "")[:300],
            meta={"path": request.url.path, "method": request.method},
        )
        session.expunge(tenant)
        session.expunge(key)
        return tenant, key


def _require_scope(key: ApiKey, scope: str) -> None:
    if not auth.api_key_scope_allows(key.scopes, scope):
        raise HTTPException(status_code=403, detail=f"This API key lacks the '{scope}' scope.")


def _commercial_error(exc: ClausewiseError) -> HTTPException:
    return HTTPException(status_code=getattr(exc, "http_status", 400), detail=exc.to_dict())


# ======================================================================= models
class AuditFinding(BaseModel):
    clause_ref: str = ""
    clause_excerpt: str = ""
    issue_type: str = ""
    severity: str = ""
    standard_id: Optional[str] = None
    standard_title: str = ""
    citation_ref: str = ""
    citation_status: str = ""
    rationale: str = ""
    remedial_wording: str = ""
    confidence: float = 0.0


class AuditResponse(BaseModel):
    audit_id: str
    status: str
    risk_status: str
    risk_score: float
    summary: str
    findings_critical: int
    findings_high: int
    findings_medium: int
    findings_advisory: int
    findings_referred: int
    confidence: float
    needs_human_review: bool
    refusal_reason: Optional[str] = None
    standards_version: str
    prompt_version: str
    cache_hit: bool
    disclaimer: str
    findings: list[AuditFinding] = Field(default_factory=list)


class TextAuditRequest(BaseModel):
    text: str = Field(..., description="Contract text to review.")
    filename: str = "api-submission.txt"
    document_type: Optional[str] = None
    jurisdiction: str = "GLOBAL"
    library_id: Optional[str] = None
    idempotency_key: Optional[str] = None


class UsageResponse(BaseModel):
    plan: str
    reviews_this_period: int
    allowance: int
    overage_usd_per_doc: Optional[float] = None


# ========================================================================= routes
@app.get("/health")
def health() -> dict[str, Any]:
    from clausewise.providers import provider_health

    return {"status": "ok", "provider": provider_health()}


@app.get("/v1/standards")
def standards(_: tuple[Tenant, ApiKey] = Depends(_tenant_and_key)) -> dict[str, Any]:
    return {
        "registry_version": get_settings().llm_provider,
        "standards": [
            {
                "standard_id": spec.standard_id,
                "title": spec.title,
                "domain": spec.domain,
                "citation_ref": spec.citation_ref,
                "verify_status": spec.verify_status,
                "summary": spec.requirement_summary,
            }
            for spec in STANDARD_INDEX.values()
        ],
    }


@app.get("/v1/usage", response_model=UsageResponse)
def usage(principal: tuple[Tenant, ApiKey] = Depends(_tenant_and_key)) -> UsageResponse:
    tenant, _ = principal
    from clausewise.entitlements import get_plan

    spec = get_plan(tenant.plan)
    with session_scope() as session:
        used = usage_this_period(session, tenant.id)
        record_usage(session, tenant_id=tenant.id, kind="api_call", quantity=0, meta={"endpoint": "usage"})
    return UsageResponse(
        plan=spec.plan.value,
        reviews_this_period=used,
        allowance=spec.audits_per_month,
        overage_usd_per_doc=spec.overage_usd_per_doc,
    )


@app.post("/v1/audits", response_model=AuditResponse)
def create_audit(
    payload: TextAuditRequest, principal: tuple[Tenant, ApiKey] = Depends(_tenant_and_key)
) -> AuditResponse:
    tenant, key = principal
    _require_scope(key, "audit:write")
    try:
        enforce_feature(tenant.plan, Feature.API_ACCESS)
    except ClausewiseError as exc:
        raise _commercial_error(exc)

    if not payload.text.strip():
        raise HTTPException(status_code=422, detail="`text` is empty.")

    try:
        document = DocumentInput.from_text(payload.text, filename=payload.filename)
        if payload.document_type:
            document.document_type = payload.document_type
        with session_scope() as session:
            audit = execute_audit(
                session,
                tenant=tenant,
                document=document,
                library_id=payload.library_id,
                jurisdiction=payload.jurisdiction,
                source_label="api",
                idempotency_key=payload.idempotency_key,
                ip_address="api",
                user_agent="api",
            )
            return _serialise(session, tenant.id, audit.id)
    except ClausewiseError as exc:
        raise _commercial_error(exc)


@app.post("/v1/audits/upload", response_model=AuditResponse)
async def create_audit_from_file(
    file: UploadFile = File(...),
    jurisdiction: str = Form("GLOBAL"),
    library_id: Optional[str] = Form(None),
    principal: tuple[Tenant, ApiKey] = Depends(_tenant_and_key),
) -> AuditResponse:
    tenant, key = principal
    _require_scope(key, "audit:write")
    try:
        enforce_feature(tenant.plan, Feature.API_ACCESS)
    except ClausewiseError as exc:
        raise _commercial_error(exc)

    content = await file.read()
    try:
        document = DocumentInput.from_bytes(file.filename or "upload", content, mime_type=file.content_type or "")
        with session_scope() as session:
            audit = execute_audit(
                session,
                tenant=tenant,
                document=document,
                library_id=library_id,
                jurisdiction=jurisdiction,
                source_label="api",
                ip_address="api",
            )
            return _serialise(session, tenant.id, audit.id)
    except ClausewiseError as exc:
        raise _commercial_error(exc)


@app.get("/v1/audits/{audit_id}", response_model=AuditResponse)
def read_audit(
    audit_id: str, principal: tuple[Tenant, ApiKey] = Depends(_tenant_and_key)
) -> AuditResponse:
    tenant, key = principal
    _require_scope(key, "audit:read")
    with session_scope() as session:
        record_usage(session, tenant_id=tenant.id, kind="api_call", quantity=0, meta={"endpoint": "read"})
        return _serialise(session, tenant.id, audit_id)


@app.get("/v1/portfolio")
def portfolio(principal: tuple[Tenant, ApiKey] = Depends(_tenant_and_key)) -> dict[str, Any]:
    tenant, key = principal
    _require_scope(key, "audit:read")
    with session_scope() as session:
        return portfolio_summary(session, tenant.id)


@app.post("/v1/audits/batch")
def create_batch(
    files: list[UploadFile] = File(...),
    jurisdiction: str = Form("GLOBAL"),
    library_id: Optional[str] = Form(None),
    principal: tuple[Tenant, ApiKey] = Depends(_tenant_and_key),
) -> dict[str, Any]:
    """Queue a portfolio review. Returns immediately; poll /v1/jobs/{id}."""
    tenant, key = principal
    _require_scope(key, "audit:write")
    from clausewise.jobs import BatchDocument, create_batch_job

    try:
        enforce_feature(tenant.plan, Feature.BATCH_REVIEW)
    except ClausewiseError as exc:
        raise _commercial_error(exc)

    with session_scope() as session:
        documents = []
        for item in files:
            documents.append(
                BatchDocument(
                    filename=item.filename or "document",
                    content=item.file.read(),
                    mime_type=item.content_type or "application/pdf",
                )
            )
        try:
            job = create_batch_job(
                session, tenant=tenant, documents=documents, library_id=library_id, jurisdiction=jurisdiction
            )
        except ClausewiseError as exc:
            raise _commercial_error(exc)
        return {"job_id": job.id, "status": job.status, "total": job.total, "failed_at_submission": job.failed}


@app.get("/v1/jobs/{job_id}")
def read_job(job_id: str, principal: tuple[Tenant, ApiKey] = Depends(_tenant_and_key)) -> dict[str, Any]:
    tenant, key = principal
    _require_scope(key, "audit:read")
    from clausewise.jobs import get_job, job_items

    with session_scope() as session:
        job = get_job(session, tenant.id, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found.")
        return {
            "job_id": job.id,
            "status": job.status,
            "total": job.total,
            "processed": job.processed,
            "failed": job.failed,
            "result": job.result,
            "items": [
                {
                    "id": item.id,
                    "status": item.status,
                    "audit_id": item.audit_id,
                    "error": item.error,
                }
                for item in job_items(session, job.id)
            ],
        }


# ==================================================================== internals
def _serialise(session: Any, tenant_id: str, audit_id: str) -> AuditResponse:
    from clausewise.config import DISCLAIMER_TEXT

    audit = get_audit(session, tenant_id, audit_id)
    if audit is None:
        raise HTTPException(status_code=404, detail="Audit not found in this workspace.")
    findings = findings_for(session, audit.id)
    return AuditResponse(
        audit_id=audit.id,
        status=audit.status,
        risk_status=audit.risk_status,
        risk_score=audit.risk_score,
        summary=audit.overall_summary,
        findings_critical=audit.findings_critical,
        findings_high=audit.findings_high,
        findings_medium=audit.findings_medium,
        findings_advisory=audit.findings_advisory,
        findings_referred=audit.findings_referred,
        confidence=audit.confidence,
        needs_human_review=audit.needs_human_review,
        refusal_reason=audit.refusal_reason,
        standards_version=audit.standards_version,
        prompt_version=audit.prompt_version,
        cache_hit=audit.cache_hit,
        disclaimer=DISCLAIMER_TEXT,
        findings=[
            AuditFinding(
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
            )
            for finding in findings
        ],
    )

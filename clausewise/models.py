"""SQLAlchemy 2.0 models.

Multi-tenancy model
-------------------
Every business object hangs off `tenant_id`. There is exactly one query
surface (`Repository`) and every method takes a tenant, so a missing tenant
filter is a startup-time type error rather than a production data leak.

White-labelling is modelled as a tenant with `partner_tenant_id` set: an
advisory firm can create sub-workspaces for its clients, each isolated, each
branded, all metered against the firm's plan.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    """Naive UTC.

    Timestamps are stored as naive UTC on purpose. It renders identically on
    SQLite and Postgres, and it removes the naive/aware comparison class of bug
    from every query path. All display conversion happens in the UI layer.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


# =============================================================== tenancy & identity
class Tenant(Base, TimestampMixin):
    """A paying entity. One row per firm / bank / advisory practice."""

    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    plan: Mapped[str] = mapped_column(String(32), default="free", nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # --- commercial
    billing_customer_id: Mapped[Optional[str]] = mapped_column(String(120))
    billing_subscription_id: Mapped[Optional[str]] = mapped_column(String(120))
    billing_status: Mapped[Optional[str]] = mapped_column(String(40))
    current_period_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    trial_ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # --- partner / white-label
    partner_tenant_id: Mapped[Optional[str]] = mapped_column(ForeignKey("tenants.id"), index=True)
    is_white_label: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    brand_name: Mapped[Optional[str]] = mapped_column(String(200))
    brand_accent: Mapped[Optional[str]] = mapped_column(String(16))
    brand_logo_path: Mapped[Optional[str]] = mapped_column(String(400))
    report_footer: Mapped[Optional[str]] = mapped_column(String(400))

    # --- governance / privacy posture (per-tenant, because banks differ)
    data_region: Mapped[str] = mapped_column(String(40), default="global", nullable=False)
    retention_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    store_document_text: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    llm_provider_override: Mapped[Optional[str]] = mapped_column(String(40))
    llm_model_override: Mapped[Optional[str]] = mapped_column(String(80))
    require_reviewer_signoff: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    users: Mapped[list["User"]] = relationship(back_populates="tenant", cascade="all, delete-orphan")


class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_user_tenant_email"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(200), default="")
    job_title: Mapped[str] = mapped_column(String(200), default="")
    # owner | admin | reviewer | analyst | viewer | api
    role: Mapped[str] = mapped_column(String(20), default="reviewer", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    password_hash: Mapped[Optional[str]] = mapped_column(String(255))
    password_salt: Mapped[Optional[str]] = mapped_column(String(64))
    external_subject: Mapped[Optional[str]] = mapped_column(String(255), index=True)  # OIDC `sub`
    mfa_secret: Mapped[Optional[str]] = mapped_column(String(64))
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    tenant: Mapped["Tenant"] = relationship(back_populates="users")


class SessionToken(Base):
    """Server-side sessions. The browser only ever holds an opaque token hash."""

    __tablename__ = "session_tokens"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64))
    user_agent: Mapped[Optional[str]] = mapped_column(String(300))


class ApiKey(Base):
    """Metered programmatic access — the stickiest revenue line in the product."""

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    created_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(120), default="default")
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    scopes: Mapped[str] = mapped_column(String(300), default="audit:read,audit:write")
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


# =============================================================== standards registry
class StandardLibrary(Base, TimestampMixin):
    """A ruleset a document can be scored against.

    `tenant_id is None` == the global AAOIFI library shipped with the product.
    A tenant-created library carries the client's own SSB resolutions — this is
    the switching-cost moat: after encoding their governance here, migrating
    away means rebuilding it.
    """

    __tablename__ = "standard_libraries"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[Optional[str]] = mapped_column(ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(40), default="GLOBAL")
    description: Mapped[str] = mapped_column(Text, default="")
    is_default_for_tenant: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(200))  # countersigning scholar
    version: Mapped[str] = mapped_column(String(40), default="1.0")

    entries: Mapped[list["StandardEntry"]] = relationship(
        back_populates="library", cascade="all, delete-orphan"
    )


class StandardEntry(Base):
    __tablename__ = "standard_entries"
    __table_args__ = (Index("ix_standard_lib_key", "library_id", "standard_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    library_id: Mapped[str] = mapped_column(ForeignKey("standard_libraries.id"), nullable=False)
    # e.g. "SS-3", "SS-8", or a client-internal code such as "CLIENT-SSB-14"
    standard_id: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    domain: Mapped[str] = mapped_column(String(60), default="general")
    citation_ref: Mapped[str] = mapped_column(String(200), default="")
    # Our own paraphrase of the requirement — NEVER verbatim standard text.
    requirement_summary: Mapped[str] = mapped_column(Text, default="")
    common_breaches: Mapped[str] = mapped_column(Text, default="")
    default_severity: Mapped[str] = mapped_column(String(20), default="high")
    detect_hints: Mapped[Optional[dict]] = mapped_column(JSON)  # deterministic pre-scan
    source_url: Mapped[str] = mapped_column(String(400), default="")
    # verified_title | confirm_before_use — honesty flag surfaced in the appendix
    verify_status: Mapped[str] = mapped_column(String(30), default="confirm_before_use")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    library: Mapped["StandardLibrary"] = relationship(back_populates="entries")


# ==================================================================== documents
class Contract(Base, TimestampMixin):
    __tablename__ = "contracts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    uploaded_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"))
    filename: Mapped[str] = mapped_column(String(400), nullable=False)
    safe_filename: Mapped[str] = mapped_column(String(400), default="")
    document_type: Mapped[str] = mapped_column(String(60), default="unknown")
    mime_type: Mapped[str] = mapped_column(String(120), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # Written only when the tenant has explicitly opted in to text retention.
    storage_path: Mapped[Optional[str]] = mapped_column(String(400))
    encrypted_text: Mapped[Optional[str]] = mapped_column(Text)
    extraction_warnings: Mapped[Optional[dict]] = mapped_column(JSON)
    retention_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class Audit(Base, TimestampMixin):
    """One review run. This row is the product's unit of record."""

    __tablename__ = "audits"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.id"), nullable=False, index=True)
    requested_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"))
    library_id: Mapped[Optional[str]] = mapped_column(ForeignKey("standard_libraries.id"))

    # queued | running | succeeded | refused | failed
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False, index=True)
    refusal_reason: Mapped[Optional[str]] = mapped_column(String(60))

    provider: Mapped[str] = mapped_column(String(40), default="")
    model: Mapped[str] = mapped_column(String(80), default="")
    prompt_version: Mapped[str] = mapped_column(String(40), default="")
    standards_version: Mapped[str] = mapped_column(String(40), default="")
    temperature: Mapped[float] = mapped_column(Float, default=0.0)
    redaction_applied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_label: Mapped[str] = mapped_column(String(40), default="upload")  # upload|paste|api|batch

    overall_summary: Mapped[str] = mapped_column(Text, default="")
    risk_status: Mapped[str] = mapped_column(String(20), default="Unknown", index=True)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    findings_total: Mapped[int] = mapped_column(Integer, default=0)
    findings_critical: Mapped[int] = mapped_column(Integer, default=0)

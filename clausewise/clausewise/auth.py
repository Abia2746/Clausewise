"""Authentication, sessions, RBAC and API keys.

Sessions are server-side: the client holds an opaque token whose SHA-256 hash is
stored. Revocation is therefore immediate, which is what a bank's security
review asks for and what a signed JWT cannot offer.

Email is treated as globally unique across tenants. That is a deliberate
simplification: it makes "sign in" a single field, and it prevents one person
accidentally holding accounts in two tenants with different passwords.

SSO is a first-class extension point (`AUTH_MODE=oidc`), not an afterthought —
no institution-level deal closes without it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from .config import get_settings
from .entitlements import Plan, check_seat_quota, utcnow
from .errors import AuthError, PermissionDenied
from .models import ApiKey, SessionToken, Tenant, User
from .security import (
    hash_password,
    new_token,
    password_problems,
    slugify,
    token_hash,
    verify_password,
)

# ------------------------------------------------------------------ role model
ROLES = ("owner", "admin", "reviewer", "analyst", "viewer", "api")

_PERMISSIONS: dict[str, set[str]] = {
    "view": {"owner", "admin", "reviewer", "analyst", "viewer"},
    "run_audit": {"owner", "admin", "reviewer", "analyst"},
    "export_report": {"owner", "admin", "reviewer", "analyst"},
    "sign_off": {"owner", "admin", "reviewer"},
    "manage_standards": {"owner", "admin", "reviewer"},
    "manage_users": {"owner", "admin"},
    "manage_billing": {"owner"},
    "manage_api_keys": {"owner", "admin"},
    "view_audit_log": {"owner", "admin", "reviewer"},
}


def can(user: User | None, permission: str) -> bool:
    if user is None:
        return False
    if getattr(user, "is_platform_admin", False):
        return True
    return user.role in _PERMISSIONS.get(permission, set())


def require(user: User | None, permission: str) -> User:
    if user is None:
        raise AuthError("Please sign in to continue.")
    if not can(user, permission):
        raise PermissionDenied(
            f"Your role ({user.role}) does not allow this action. Ask a workspace owner or admin."
        )
    return user


# ================================================================== registration
@dataclass
class RegistrationResult:
    tenant: Tenant
    user: User


def get_user_by_email(session: Session, email: str) -> Optional[User]:
    return (
        session.query(User)
        .filter(func.lower(User.email) == email.strip().lower())
        .order_by(User.created_at.asc())
        .first()
    )


def _unique_slug(session: Session, base: str) -> str:
    candidate = slugify(base)
    suffix = 1
    while session.query(Tenant).filter(Tenant.slug == candidate).one_or_none() is not None:
        suffix += 1
        candidate = f"{slugify(base)}-{suffix}"
    return candidate


def register_workspace(
    session: Session,
    *,
    company: str,
    email: str,
    password: str,
    full_name: str = "",
    job_title: str = "",
    plan: Plan | str = Plan.FREE,
) -> RegistrationResult:
    """Create a tenant and its first owner. Self-serve signup path."""
    settings = get_settings()
    if not settings.allow_self_signup and str(plan) == Plan.FREE.value:
        raise PermissionDenied("Self-serve signup is closed. Ask us for an invitation.")

    email = email.strip().lower()
    if not email or "@" not in email:
        raise AuthError("Enter a valid work email address.")
    if get_user_by_email(session, email) is not None:
        raise AuthError("An account with that email already exists. Sign in instead.")

    problems = password_problems(password)
    if problems:
        raise AuthError(" ".join(problems))

    if not company.strip():
        raise AuthError("Enter your organisation name — reports are issued in its name.")

    plan_value = plan.value if isinstance(plan, Plan) else str(plan)
    tenant = Tenant(
        name=company.strip(),
        slug=_unique_slug(session, company),
        plan=plan_value,
        retention_days=settings.default_retention_days,
    )
    session.add(tenant)
    session.flush()

    password_hash, salt = hash_password(password)
    user = User(
        tenant_id=tenant.id,
        email=email,
        full_name=full_name.strip(),
        job_title=job_title.strip(),
        role="owner",
        password_hash=password_hash,
        password_salt=salt,
        is_platform_admin=email in settings.admin_emails,
    )
    session.add(user)
    session.flush()

    from .repository import log_event

    log_event(
        session,
        action="auth.workspace_created",
        tenant_id=tenant.id,
        actor_user_id=user.id,
        actor_label=email,
        object_type="tenant",
        object_id=tenant.id,
        meta={"plan": plan_value},
    )
    return RegistrationResult(tenant=tenant, user=user)


def create_member(
    session: Session,
    *,
    tenant: Tenant,
    email: str,
    password: str,
    full_name: str = "",
    role: str = "reviewer",
    acting_user: Optional[User] = None,
) -> User:
    require(acting_user, "manage_users")
    role = role if role in ROLES else "reviewer"
    if role == "owner" and not (acting_user and acting_user.role == "owner"):
        raise PermissionDenied("Only an owner can create another owner.")

    if get_user_by_email(session, email) is not None:
        raise AuthError("That email is already registered.")

    problems = password_problems(password)
    if problems:
        raise AuthError(" ".join(problems))

    active_seats = (
        session.query(func.count(User.id))
        .filter(User.tenant_id == tenant.id, User.is_active.is_(True))
        .scalar()
        or 0
    )
    check_seat_quota(tenant.plan, int(active_seats))

    password_hash, salt = hash_password(password)
    user = User(
        tenant_id=tenant.id,
        email=email.strip().lower(),
        full_name=full_name,
        job_title="",
        role=role,
        password_hash=password_hash,
        password_salt=salt,
    )
    session.add(user)
    session.flush()
    return user


def deactivate_member(session: Session, *, tenant: Tenant, user_id: str, acting_user: User) -> None:
    require(acting_user, "manage_users")
    user = session.get(User, user_id)
    if user is None or user.tenant_id != tenant.id:
        raise PermissionDenied("That user is not in your workspace.")
    if user.role == "owner" and acting_user.id != user.id:
        raise PermissionDenied("An owner can only be removed by themselves.")
    user.is_active = False
    for token in session.query(SessionToken).filter(SessionToken.user_id == user.id).all():
        token.revoked = True


# ======================================================================= login
def authenticate(session: Session, *, email: str, password: str) -> User:
    user = get_user_by_email(session, email)
    if user is None or not user.password_hash or not user.password_salt:
        # Same message either way: do not leak which emails exist.
        raise AuthError("Email or password is incorrect.")
    if not user.is_active:
        raise AuthError("That account has been deactivated. Contact your workspace owner.")
    if not verify_password(password, user.password_hash, user.password_salt):
        raise AuthError("Email or password is incorrect.")
    user.last_login_at = utcnow()
    return user


def create_session(
    session: Session, *, user: User, ip_address: str = "", user_agent: str = ""
) -> str:
    settings = get_settings()
    token = new_token()
    session.add(
        SessionToken(
            token_hash=token_hash(token),
            user_id=user.id,
            expires_at=utcnow() + timedelta(hours=settings.session_ttl_hours),
            ip_address=ip_address,
            user_agent=user_agent[:300],
        )
    )
    # The session factory runs with autoflush=False so that a failed audit never
    # half-writes. Anything that must be visible to a later read in the same
    # transaction is flushed explicitly here.
    session.flush()
    from .repository import log_event

    log_event(
        session,
        action="auth.login",
        tenant_id=user.tenant_id,
        actor_user_id=user.id,
        actor_label=user.email,
        object_type="user",
        object_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return token


def resolve_session(session: Session, token: Optional[str]) -> Optional[User]:
    if not token:
        return None
    row = (
        session.query(SessionToken)
        .filter(SessionToken.token_hash == token_hash(token))
        .one_or_none()
    )
    if row is None or row.revoked:
        return None
    if row.expires_at <= utcnow():
        return None
    user = session.get(User, row.user_id)
    if user is None or not user.is_active:
        return None
    return user


def revoke_session(session: Session, token: str) -> None:
    row = (
        session.query(SessionToken)
        .filter(SessionToken.token_hash == token_hash(token))
        .one_or_none()
    )
    if row is not None:
        row.revoked = True
        session.flush()


def revoke_all_sessions(session: Session, user_id: str) -> int:
    rows = session.query(SessionToken).filter(SessionToken.user_id == user_id, SessionToken.revoked.is_(False)).all()
    for row in rows:
        row.revoked = True
    return len(rows)


def purge_expired_sessions(session: Session) -> int:
    rows = session.query(SessionToken).filter(SessionToken.expires_at <= utcnow()).all()
    for row in rows:
        session.delete(row)
    return len(rows)


# ==================================================================== api keys
def issue_api_key(
    session: Session,
    *,
    tenant: Tenant,
    acting_user: User,
    name: str = "default",
    scopes: str = "audit:read,audit:write",
    expires_in_days: Optional[int] = None,
) -> tuple[ApiKey, str]:
    """Create a key. The plaintext is returned once and never stored."""
    require(acting_user, "manage_api_keys")
    from .entitlements import enforce_feature

    enforce_feature(tenant.plan, "api_access")

    plaintext = new_token("cwk_")
    record = ApiKey(
        tenant_id=tenant.id,
        created_by=acting_user.id,
        name=name[:120],
        key_prefix=plaintext[:12],
        key_hash=token_hash(plaintext),
        scopes=scopes,
        expires_at=utcnow() + timedelta(days=expires_in_days) if expires_in_days else None,
    )
    session.add(record)
    session.flush()

    from .repository import log_event

    log_event(
        session,
        action="apikey.created",
        tenant_id=tenant.id,
        actor_user_id=acting_user.id,
        object_type="api_key",
        object_id=record.id,
        meta={"name": name, "scopes": scopes},
    )
    return record, plaintext


def verify_api_key(session: Session, plaintext: str) -> Optional[tuple[Tenant, ApiKey]]:
    if not plaintext:
        return None
    record = (
        session.query(ApiKey)
        .filter(ApiKey.key_hash == token_hash(plaintext), ApiKey.revoked.is_(False))
        .one_or_none()
    )
    if record is None:
        return None
    if record.expires_at and record.expires_at <= utcnow():
        return None
    tenant = session.get(Tenant, record.tenant_id)
    if tenant is None or not tenant.is_active:
        return None
    record.last_used_at = utcnow()
    return tenant, record


def revoke_api_key(session: Session, *, tenant: Tenant, key_id: str, acting_user: User) -> None:
    require(acting_user, "manage_api_keys")
    record = session.get(ApiKey, key_id)
    if record is None or record.tenant_id != tenant.id:
        raise PermissionDenied("That API key is not in your workspace.")
    record.revoked = True
    session.flush()  # revocation must be visible to the very next verification
    from .repository import log_event

    log_event(
        session,
        action="apikey.revoked",
        tenant_id=tenant.id,
        actor_user_id=acting_user.id,
        object_type="api_key",
        object_id=key_id,
    )


def api_key_scope_allows(scopes: str, needed: str) -> bool:
    granted = {s.strip() for s in (scopes or "").split(",") if s.strip()}
    return needed in granted or "*" in granted or "audit:*" in granted


# ======================================================================== SSO
def oidc_configured() -> bool:
    settings = get_settings()
    return bool(settings.oidc_discovery_url and settings.oidc_client_id and settings.oidc_client_secret)


def oidc_authorization_url(state: str = "") -> str:
    """Extension point for Okta / Entra ID / Google Workspace.

    Implemented as an explicit stub rather than a half-finished flow, because a
    broken SSO button in front of a bank's identity team costs the deal. The
    contract is: complete the code exchange, resolve the `sub` claim to
    `User.external_subject`, then call `create_session`.
    """
    settings = get_settings()
    if not oidc_configured():
        raise AuthError("Single sign-on is not configured for this deployment.")
    raise AuthError(
        "SSO is configured but the code-exchange step is not implemented in this build. "
        "Wire your identity provider in clausewise/auth.py:oidc_authorization_url."
    )


def provision_oidc_user(
    session: Session, *, subject: str, email: str, full_name: str = "", company: str = ""
) -> User:
    """Resolve or create a user from an IdP subject, after a successful exchange."""
    existing = (
        session.query(User).filter(User.external_subject == subject).one_or_none()
    )
    if existing is not None:
        return existing

    user = get_user_by_email(session, email)
    if user is not None:
        user.external_subject = subject
        return user

    from .repository import log_event

    result = register_workspace(
        session,
        company=company or email.split("@")[-1],
        email=email,
        password=new_token(),  # unusable password: SSO only
        full_name=full_name,
    )
    result.user.external_subject = subject
    log_event(
        session,
        action="auth.oidc_provisioned",
        tenant_id=result.tenant.id,
        actor_user_id=result.user.id,
        actor_label=email,
        object_type="user",
        object_id=result.user.id,
    )
    return result.user

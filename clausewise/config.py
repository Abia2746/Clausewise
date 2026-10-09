"""Central configuration.

Deliberately dependency-light: a dataclass over `os.environ` with `.env`
loaded once. No settings framework, so the core stays importable in a
customer's VPC, in a worker, in tests and in the Streamlit runtime alike.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

try:  # optional in tests / minimal installs
    from dotenv import load_dotenv

    load_dotenv(override=False)
except Exception:  # pragma: no cover
    pass

BASE_DIR = Path(__file__).resolve().parent.parent
VAR_DIR = BASE_DIR / "var"
REPORT_DIR = VAR_DIR / "reports"
UPLOAD_DIR = VAR_DIR / "uploads"

# Bumped whenever the prompt or the standards registry changes. Stamped onto
# every audit so a report can always be reproduced and defended later.
PROMPT_VERSION = "2026-10-aaoifi-v2"
STANDARDS_REGISTRY_VERSION = "2026-10-01"

DISCLAIMER_TEXT = (
    "This report is an assistive, machine-generated review prepared for the "
    "internal use of the commissioning institution. It is not a fatwa, not a "
    "Shari'ah ruling, and not legal advice. Compliance determinations rest "
    "solely with the institution's Shari'ah Supervisory Board or appointed "
    "Shari'ah reviewer, whose sign-off is required before this report is "
    "relied upon. Cited standards are referenced for navigation only; the "
    "authoritative text is the institution's own licensed copy."
)


def _env(key: str, default: str = "") -> str:
    return (os.environ.get(key) or default).strip()


def _env_bool(key: str, default: bool = False) -> bool:
    raw = _env(key, str(default)).lower()
    return raw in {"1", "true", "yes", "on"}


def _env_int(key: str, default: int) -> int:
    try:
        return int(_env(key, str(default)))
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(_env(key, str(default)))
    except ValueError:
        return default


def _env_json(key: str, default: Any) -> Any:
    raw = _env(key, "")
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


@dataclass(frozen=True)
class Settings:
    # ------------------------------------------------------------ application
    env: str = field(default_factory=lambda: _env("ENV", "development"))
    debug: bool = field(default_factory=lambda: _env_bool("DEBUG", False))
    app_base_url: str = field(default_factory=lambda: _env("APP_BASE_URL", "http://localhost:8501"))
    secret_key: str = field(default_factory=lambda: _env("SECRET_KEY", ""))

    # ------------------------------------------------------------- data store
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL", "sqlite:///./clausewise.db"))
    data_encryption_key: str = field(default_factory=lambda: _env("DATA_ENCRYPTION_KEY", ""))

    # ------------------------------------------------------------------- auth
    auth_mode: str = field(default_factory=lambda: _env("AUTH_MODE", "password").lower())
    allow_self_signup: bool = field(default_factory=lambda: _env_bool("ALLOW_SELF_SIGNUP", True))
    session_ttl_hours: int = field(default_factory=lambda: _env_int("SESSION_TTL_HOURS", 12))
    oidc_discovery_url: str = field(default_factory=lambda: _env("OIDC_DISCOVERY_URL", ""))
    oidc_client_id: str = field(default_factory=lambda: _env("OIDC_CLIENT_ID", ""))
    oidc_client_secret: str = field(default_factory=lambda: _env("OIDC_CLIENT_SECRET", ""))

    # -------------------------------------------------------------------- LLM
    llm_provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", "gemini").lower())
    llm_model_override: str = field(default_factory=lambda: _env("LLM_MODEL_OVERRIDE", ""))
    gemini_api_key: str = field(default_factory=lambda: _env("GEMINI_API_KEY", ""))
    gemini_model: str = field(default_factory=lambda: _env("GEMINI_MODEL", "gemini-2.5-flash"))
    openai_base_url: str = field(default_factory=lambda: _env("OPENAI_BASE_URL", ""))
    openai_api_key: str = field(default_factory=lambda: _env("OPENAI_API_KEY", ""))
    openai_model: str = field(default_factory=lambda: _env("OPENAI_MODEL", ""))
    llm_timeout_seconds: int = field(default_factory=lambda: _env_int("LLM_TIMEOUT_SECONDS", 90))
    llm_max_retries: int = field(default_factory=lambda: _env_int("LLM_MAX_RETRIES", 3))
    llm_max_output_tokens: int = field(default_factory=lambda: _env_int("LLM_MAX_OUTPUT_TOKENS", 8192))
    llm_temperature: float = field(default_factory=lambda: _env_float("LLM_TEMPERATURE", 0.0))
    # Confidence floor. Below this the audit refuses rather than guesses.
    llm_min_confidence: float = field(default_factory=lambda: _env_float("LLM_MIN_CONFIDENCE", 0.55))
    global_monthly_budget_usd: float = field(default_factory=lambda: _env_float("GLOBAL_MONTHLY_BUDGET_USD", 500.0))
    llm_cost_table: dict = field(
        default_factory=lambda: _env_json(
            "LLM_COST_TABLE_JSON",
            # REFERENCE ONLY. Provider pricing changes; keep this in sync with your
            # current price list. Used for internal cost reporting, never billing.
            {"gemini-2.5-flash": [0.30, 2.50], "heuristic": [0.0, 0.0]},
        )
    )

    # -------------------------------------------------------- document limits
    max_upload_mb: int = field(default_factory=lambda: _env_int("MAX_UPLOAD_MB", 25))
    max_pages_per_document: int = field(default_factory=lambda: _env_int("MAX_PAGES_PER_DOCUMENT", 250))
    max_chars_per_document: int = field(default_factory=lambda: _env_int("MAX_CHARS_PER_DOCUMENT", 900_000))
    chunk_target_chars: int = field(default_factory=lambda: _env_int("CHUNK_TARGET_CHARS", 12_000))
    chunk_overlap_chars: int = field(default_factory=lambda: _env_int("CHUNK_OVERLAP_CHARS", 800))

    # ------------------------------------------------- privacy, retention, PII
    redaction_enabled: bool = field(default_factory=lambda: _env_bool("REDACTION_ENABLED", True))
    store_document_text: bool = field(default_factory=lambda: _env_bool("STORE_DOCUMENT_TEXT", False))
    default_retention_days: int = field(default_factory=lambda: _env_int("DEFAULT_RETENTION_DAYS", 30))
    cache_identical_documents: bool = field(default_factory=lambda: _env_bool("CACHE_IDENTICAL_DOCUMENTS", True))
    rate_limit_requests_per_minute: int = field(default_factory=lambda: _env_int("RATE_LIMIT_REQUESTS_PER_MINUTE", 60))

    # ---------------------------------------------------------------- billing
    billing_enabled: bool = field(default_factory=lambda: _env_bool("BILLING_ENABLED", False))
    stripe_secret_key: str = field(default_factory=lambda: _env("STRIPE_SECRET_KEY", ""))
    stripe_webhook_secret: str = field(default_factory=lambda: _env("STRIPE_WEBHOOK_SECRET", ""))
    stripe_prices: dict = field(
        default_factory=lambda: {
            "practitioner_monthly": _env("STRIPE_PRICE_PRACTITIONER_MONTHLY", ""),
            "practitioner_annual": _env("STRIPE_PRICE_PRACTITIONER_ANNUAL", ""),
            "team_monthly": _env("STRIPE_PRICE_TEAM_MONTHLY", ""),
            "team_annual": _env("STRIPE_PRICE_TEAM_ANNUAL", ""),
            "institution_monthly": _env("STRIPE_PRICE_INSTITUTION_MONTHLY", ""),
            "institution_annual": _env("STRIPE_PRICE_INSTITUTION_ANNUAL", ""),
        }
    )

    # ----------------------------------------------------------------- brand
    brand_name: str = field(default_factory=lambda: _env("BRAND_NAME", "Clausewise Shari'ah"))
    brand_accent: str = field(default_factory=lambda: _env("BRAND_ACCENT", "#2F6F6B"))
    support_email: str = field(default_factory=lambda: _env("SUPPORT_EMAIL", "support@example.com"))
    sales_calendar_url: str = field(default_factory=lambda: _env("SALES_CALENDAR_URL", ""))
    admin_emails: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            e.strip().lower() for e in _env("ADMIN_EMAILS", "").split(",") if e.strip()
        )
    )

    # -------------------------------------------------------------- derived
    @property
    def is_production(self) -> bool:
        return self.env.lower() in {"production", "prod"}

    @property
    def active_model(self) -> str:
        if self.llm_model_override:
            return self.llm_model_override
        if self.llm_provider == "gemini":
            return self.gemini_model
        if self.llm_provider == "openai_compatible":
            return self.openai_model or "gpt-4o-mini"
        return "heuristic"

    def cost_for(self, model: str, tokens_in: int, tokens_out: int) -> float:
        """Internal cost estimate in USD. Never used for customer billing."""
        rate = self.llm_cost_table.get(model)
        if not rate:
            return 0.0
        return round((tokens_in / 1_000_000) * rate[0] + (tokens_out / 1_000_000) * rate[1], 6)

    def validate(self) -> list[str]:
        """Return a list of blocking misconfigurations (empty == healthy)."""
        problems: list[str] = []
        if self.is_production:
            if not self.secret_key or len(self.secret_key) < 32:
                problems.append("SECRET_KEY must be set to a 32+ character random value in production.")
            if not self.data_encryption_key:
                problems.append("DATA_ENCRYPTION_KEY must be set in production.")
            if self.database_url.startswith("sqlite"):
                problems.append("SQLite is not supported for multi-tenant production; use Postgres.")
            if self.allow_self_signup and self.auth_mode == "password":
                problems.append("ALLOW_SELF_SIGNUP=true in production exposes the free tier to abuse. Disable it or front it with a waitlist.")
            if self.llm_provider == "gemini" and not self.gemini_api_key:
                problems.append("GEMINI_API_KEY is missing, so paid reviews cannot run. Demo mode (LLM_PROVIDER=heuristic) still works.")
            if self.billing_enabled and not self.stripe_secret_key:
                problems.append("BILLING_ENABLED=true but STRIPE_SECRET_KEY is empty.")
        return problems

    def ensure_dirs(self) -> None:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings


def reset_settings_cache() -> None:
    """Test helper: force settings to be re-read from the environment."""
    get_settings.cache_clear()

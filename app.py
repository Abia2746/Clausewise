"""Streamlit entry point.

The UI is a thin surface over `clausewise`. Everything that decides anything —
quotas, citations, refusal, scoring, metering, the audit trail — lives in the
core package, so the API and the batch worker behave identically.

Run locally:
streamlit run app.py
"""

from __future__ import annotations

import os

import streamlit as st

# --------------------------------------------------------------- secrets bridge
# Streamlit Community Cloud and most managed hosts inject secrets via st.secrets
# rather than the environment. Bridge them BEFORE any clausewise import reads
# configuration, so a deployment only has to be configured in one place.
#
# `st.secrets` fails LAZILY: reading the attribute is harmless, but iterating it
# raises StreamlitSecretNotFoundError when no secrets.toml exists. Guarding only
# the attribute access therefore crashes the whole app on any fresh clone or
# Streamlit Cloud deploy with no secrets configured — so the iteration itself
# must be inside the try. Materialise it first, then read from the plain dict.
def _bridge_secrets() -> None:
    try:
        items = dict(st.secrets)
    except Exception:
        return
    for key, value in items.items():
        if isinstance(value, (str, int, float, bool)) and not os.environ.get(key):
            os.environ[key] = str(value)


_bridge_secrets()

from clausewise.config import get_settings, reset_settings_cache  # noqa: E402
from clausewise.db import init_db, session_scope  # noqa: E402
from clausewise.providers import provider_health  # noqa: E402
from clausewise.standards import seed_global_library  # noqa: E402
from ui import pages  # noqa: E402

reset_settings_cache()
SETTINGS = get_settings()

st.set_page_config(
    page_title=f"{SETTINGS.brand_name} — Shari'ah contract review",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ------------------------------------------------------------------- bootstrap
@st.cache_resource(show_spinner=False)
def _bootstrap() -> dict:
    """One-time setup per process: schema, global standards library, health."""
    init_db()
    stats = seed_global_library()
    return {"library_entries": stats.entries, "health": provider_health()}


BOOTSTRAP = _bootstrap()


def _current_user():
    """Resolve the signed-in user from the server-side session token."""
    from clausewise import auth

    token = st.session_state.get("token")
    if not token:
        return None, None
    from clausewise.models import Tenant

    with session_scope() as session:
        user = auth.resolve_session(session, token)
        if user is None:
            return None, None
        tenant = session.get(Tenant, user.tenant_id)
        if tenant is None or not tenant.is_active:
            return None, None
        # Detach copies: expire_on_commit is False, so attribute access stays valid.
        return tenant, user


def _flash_configuration_problems() -> None:
    problems = SETTINGS.validate()
    if problems and not SETTINGS.is_production:
        with st.sidebar.expander("⚠️ Deployment notes", expanded=False):
            for problem in problems:
                st.caption(f"• {problem}")


# ------------------------------------------------------------------------ main
def main() -> None:
    tenant, user = _current_user()

    if tenant is None or user is None:
        st.session_state.pop("token", None)
        pages.render_auth()
        _flash_configuration_problems()
        return

    nav = pages.render_sidebar(tenant, user)
    _flash_configuration_problems()

    dispatch = {
        "Review a contract": pages.page_audit,
        "Repository": pages.page_repository,
        "Batch review": pages.page_batch,
        "Standards library": pages.page_standards,
        "Team": pages.page_team,
        "Plan & billing": pages.page_billing,
        "Admin": pages.page_admin,
    }

    if nav == "Talk to us":
        pages.page_sales(tenant, user)
    else:
        handler = dispatch.get(nav)
        if handler is None:
            st.error("That page is unavailable.")
        else:
            handler(tenant, user)

    _render_footer()


def _render_footer() -> None:
    st.divider()
    st.caption(
        "Clausewise Shari'ah produces assistive, machine-generated reviews. It is not a fatwa, not a "
        "Shari'ah ruling and not legal advice; compliance determinations rest with your Shari'ah board "
        "or appointed reviewer, whose sign-off is required. "
        f"Standards registry {SETTINGS.brand_name} · entries loaded: {BOOTSTRAP['library_entries']}."
    )


if __name__ == "__main__":
    main()

"""Application pages.

Each page receives the authenticated `tenant` and `user` and opens a short-lived
session for reads and writes. Nothing here re-implements a business rule: quota,
citation enforcement and refusal all live in `clausewise`.
"""

from __future__ import annotations

from typing import Any, Optional

import streamlit as st

from clausewise import auth
from clausewise.config import get_settings
from clausewise.db import session_scope
from clausewise.entitlements import Feature, Plan, get_plan, plan_allows
from clausewise.errors import (
    AuthError,
    ClausewiseError,
    FeatureLocked,
    PermissionDenied,
    QuotaExceeded,
)
from clausewise.models import Tenant, User
from clausewise.repository import (
    DocumentInput,
    audit_log_for,
    capture_lead,
    findings_for,
    get_audit,
    get_contract,
    libraries_for,
    list_audits,
    platform_metrics,
    portfolio_summary,
    quota_decision_for,
    set_remediation_status,
    sign_off_audit,
    tenant_branding,
    usage_this_period,
)
from clausewise.standards import (
    ISSUE_TYPE_LABELS,
    JURISDICTION_PACKS,
    STANDARD_INDEX,
    standards_needing_verification,
)

from . import components as C

SAMPLE_CONTRACT = """ISLAMIC TRADE FACILITY & INVESTMENT AGREEMENT

2.1 The Bank agrees to provide a trade facility of USD 5,000,000 to the Client on a deferred payment basis.
2.3 All risk of asset loss passes completely to the Client prior to the execution of the separate Murabahah sale contract.
3.1 The Bank guarantees the Client a fixed profit rate of 6% per annum on invested capital.
3.4 Invoice balances unpaid after 14 days shall accrue default interest at a rate of 4% per annum.
4.2 The Client shall bear all insurance, maintenance and ownership-related taxes on the leased asset.
5.1 The Investor shall be paid a guaranteed minimum return of 8% per annum regardless of actual profit.
6.3 Any amounts owed by the Client may be set off against the Investor's capital contribution.
7.1 The Originator undertakes to repurchase the sukuk at par upon maturity.
"""

PAGES = [
    "Review a contract",
    "Repository",
    "Batch review",
    "Standards library",
    "Team",
    "Plan & billing",
    "Talk to us",
    "Admin",
]


# ================================================================== auth screens
def render_auth() -> None:
    """Sign-in / sign-up. The free tier is the top of the funnel, so it is one screen."""
    settings = get_settings()
    left, right = st.columns([1.1, 1])

    with left:
        st.title("Automate your Shari'ah contract risk reviews")
        st.markdown(
            "Upload an Islamic trade facility, a Murabahah or Ijarah agreement, a sukuk document or "
            "an investment contract. Clausewise reads it clause by clause against a defined standards "
            "library, cites the standard behind every finding, and proposes replacement wording."
        )
        st.markdown("##### What it is")
        st.markdown(
            "- Clause-level findings with the **standard cited** for each one\n"
            "- **Suggested replacement wording** your drafting team can act on\n"
            "- A **board-ready report** with a sign-off block and a reproducible audit trail\n"
            "- Personal data **redacted before analysis**\n"
            "- It **refuses** to give a view when it cannot be reliable"
        )
        st.markdown("##### What it is not")
        st.caption(
            "It is not a fatwa, not a Shari'ah ruling and not legal advice. Compliance determinations "
            "rest with your Shari'ah board or appointed reviewer, whose sign-off is required."
        )
        st.info(
            "No credit card for the free tier. Three reviews a month, findings on screen. "
            "Export a board-ready report from $199/month."
        )
        if settings.billing_enabled or settings.sales_calendar_url:
            st.caption("Prefer a walkthrough? Use the **Talk to us** tab after signing in.")

    with right:
        with st.container(border=True):
            tab_in, tab_up = st.tabs(["Sign in", "Create account"])
            with tab_in:
                with st.form("login"):
                    email = st.text_input("Work email")
                    password = st.text_input("Password", type="password")
                    if st.form_submit_button("Sign in", type="primary", use_container_width=True):
                        _do_login(email, password)
                if auth.oidc_configured():
                    if st.button("Continue with single sign-on", use_container_width=True):
                        st.info("Single sign-on is configured. Contact your administrator for the link.")

            with tab_up:
                if not settings.allow_self_signup:
                    st.caption("Self-serve signup is closed on this deployment. Ask us for an invitation.")
                else:
                    with st.form("signup"):
                        company = st.text_input("Organisation", help="Reports are issued in its name.")
                        full_name = st.text_input("Your name")
                        email = st.text_input("Work email", key="signup-email")
                        password = st.text_input(
                            "Password",
                            type="password",
                            help="At least 12 characters, with upper, lower and a digit.",
                        )
                        if st.form_submit_button("Create account", type="primary", use_container_width=True):
                            _do_signup(company, email, password, full_name)


def _do_login(email: str, password: str) -> None:
    try:
        with session_scope() as session:
            user = auth.authenticate(session, email=email, password=password)
            token = auth.create_session(session, user=user)
            st.session_state["token"] = token
            st.rerun()
    except AuthError as exc:
        st.error(exc.message)


def _do_signup(company: str, email: str, password: str, full_name: str) -> None:
    try:
        with session_scope() as session:
            result = auth.register_workspace(
                session, company=company, email=email, password=password, full_name=full_name
            )
            token = auth.create_session(session, user=result.user)
            st.session_state["token"] = token
            st.session_state["nav"] = "Review a contract"
            st.rerun()
    except ClausewiseError as exc:
        st.error(exc.message)


def render_sidebar(tenant: Tenant, user: User) -> str:
    brand = tenant_branding(tenant)
    st.sidebar.markdown(f"# {brand['name']}")
    st.sidebar.caption("🛡️ Zero data retention · PII redacted before analysis")
    C.plan_badge(tenant)

    with session_scope() as session:
        decision = quota_decision_for(session, tenant)
        C.usage_meter(decision, plan=tenant.plan)

    st.sidebar.divider()
    options = list(PAGES)
    if not user.is_platform_admin:
        options = [p for p in options if p != "Admin"]
    current = st.session_state.get("nav", options[0])
    if current not in options:
        current = options[0]
    nav = st.sidebar.radio("Navigate", options, index=options.index(current), label_visibility="collapsed")
    st.session_state["nav"] = nav

    st.sidebar.divider()
    st.sidebar.caption(f"{user.full_name or user.email} · {user.role}")
    if st.sidebar.button("Sign out", use_container_width=True):
        token = st.session_state.get("token")
        if token:
            with session_scope() as session:
                auth.revoke_session(session, token)
        st.session_state.pop("token", None)
        st.rerun()
    return nav


# ================================================================ shared helpers
def _handle_error(exc: Exception, tenant: Tenant, blocker: str) -> None:
    if isinstance(exc, QuotaExceeded):
        st.warning(exc.message)
        C.upgrade_card(plan=tenant.plan, blocker=blocker, context="Your allowance for this period is used up.")
    elif isinstance(exc, FeatureLocked):
        C.upgrade_card(plan=tenant.plan, blocker=exc.feature, context=exc.message)
    elif isinstance(exc, PermissionDenied):
        st.error(exc.message)
    elif isinstance(exc, ClausewiseError):
        st.error(exc.message)
    else:
        st.error(f"Something went wrong: {exc}")


def _library_selector(tenant: Tenant, key: str) -> Optional[str]:
    with session_scope() as session:
        libraries = libraries_for(session, tenant.id)
        rows = [(library.id, f"{library.name} ({library.jurisdiction})", library.tenant_id) for library in libraries]
        if not rows:
            return None
        labels = [row[1] for row in rows]
        chosen = st.selectbox("Standards library", labels, key=key)
        return rows[labels.index(chosen)][0]


def _jurisdiction_selector(key: str) -> str:
    codes = list(JURISDICTION_PACKS.keys())
    labels = [f"{JURISDICTION_PACKS[c].label}" for c in codes]
    chosen = st.selectbox("Jurisdiction overlay", labels, index=0, key=key)
    return codes[labels.index(chosen)]


def _render_audit_result(audit_id: str, tenant: Tenant, user: User) -> None:
    """The shared result view used by both the audit page and the repository."""
    with session_scope() as session:
        audit = get_audit(session, tenant.id, audit_id)
        if audit is None:
            st.error("That review is not available in this workspace.")
            return
        contract = get_contract(session, tenant.id, audit.contract_id)
        findings = findings_for(session, audit.id)

        if audit.status == "refused":
            C.refusal_panel(audit)
            if audit.needs_human_review and plan_allows(tenant.plan, Feature.PDF_EXPORT):
                st.caption("A refusal notice can still be exported for your board record.")
        elif audit.status == "failed":
            st.error(f"This review failed: {audit.error or 'unknown error'}")
            return
        else:
            C.audit_header(audit, contract)
            with st.container(border=True):
                st.markdown("##### Executive summary")
                st.write(audit.overall_summary)
                if audit.review_reason:
                    st.caption(f"Reviewer action: {audit.review_reason}")

            C.export_controls(audit=audit, contract=contract, findings=findings, tenant=tenant, user=user)

            actionable = [f for f in findings if f.severity != "referred"]
            referred = [f for f in findings if f.severity == "referred"]

            if actionable:
                st.markdown(f"#### Findings ({len(actionable)})")
                for index, finding in enumerate(actionable, start=1):
                    C.finding_card(finding, index)

            if referred:
                st.markdown(f"#### Referred to your Shari'ah board ({len(referred)})")
                st.caption(
                    "These could not be matched to a standard in the active library. They are recorded for the "
                    "board and are not compliance conclusions."
                )
                for index, finding in enumerate(referred, start=1):
                    C.finding_card(finding, index)

            if not actionable and not referred and audit.status == "succeeded":
                st.success("No clause in this document was flagged against the active standards library.")
                st.caption("Preliminary result. It does not replace a Shari'ah board determination.")

        _render_signoff(audit, tenant, user)


def _render_signoff(audit: Any, tenant: Tenant, user: User) -> None:
    st.divider()
    st.markdown("#### Reviewer disposition")
    if audit.signed_off_at:
        st.success(f"Signed off on {C.fmt_dt(audit.signed_off_at)} · status: {audit.remediation_status}")
        if audit.signoff_note:
            st.caption(f"Note: {audit.signoff_note}")
        return

    if not auth.can(user, "sign_off"):
        st.info(f"Your role ({user.role}) records dispositions but does not sign off. Ask a reviewer or admin.")
        return

    with st.form(f"signoff-{audit.id}"):
        status = st.selectbox(
            "Disposition",
            ["reviewed", "in_progress", "accepted", "rejected", "escalated_to_board"],
            help="This becomes part of the audit record.",
        )
        note = st.text_area("Note for the file", height=80)
        if st.form_submit_button("Record disposition", type="primary"):
            with session_scope() as session:
                signed = sign_off_audit(
                    session, tenant=tenant, audit_id=audit.id, user_id=user.id, note=note
                )
                if status != "reviewed":
                    set_remediation_status(
                        session, tenant=tenant, audit_id=signed.id, status=status, user_id=user.id
                    )
            st.success("Disposition recorded on the audit trail.")
            st.rerun()


# ==================================================================== page: audit
def page_audit(tenant: Tenant, user: User) -> None:
    st.header("Review a contract")
    st.caption(
        "Clause-level Shari'ah screening against your standards library. Findings are assistive and "
        "require your reviewer's sign-off."
    )

    tab_upload, tab_paste, tab_sample = st.tabs(["Upload a document", "Paste text", "Try the sample"])

    document: Optional[DocumentInput] = None
    source_label = "upload"

    with tab_upload:
        uploaded = st.file_uploader("Contract file (.pdf, .docx, .txt)", type=["pdf", "docx", "txt"])
        if uploaded is not None:
            st.caption(f"{uploaded.name} · {uploaded.size / 1024:,.0f} KB")
            document = None

    with tab_paste:
        pasted = st.text_area("Contract text", height=220, key="paste-text")
        if pasted.strip():
            document = DocumentInput.from_text(pasted, filename="Pasted contract text")
            source_label = "paste"

    with tab_sample:
        st.caption("A short Islamic trade facility containing the clauses this engine exists to catch.")
        st.code(SAMPLE_CONTRACT, language=None)
        if st.button("Load the sample", use_container_width=False):
            st.session_state["paste-text"] = SAMPLE_CONTRACT
            st.rerun()

    col_a, col_b, col_c = st.columns([2, 1, 1])
    library_id = col_b.selectbox("Library", _library_labels(tenant), key="audit-library-index", label_visibility="collapsed")
    jurisdiction = col_c.selectbox(
        "Jurisdiction", list(JURISDICTION_PACKS.keys()), key="audit-jurisdiction", label_visibility="collapsed"
    )
    col_a.caption(f"Library index {library_id} · overlay {jurisdiction}")

    submitted = st.button("Run Shari'ah review", type="primary", use_container_width=True)

    if submitted:
        try:
            if uploaded is not None and source_label == "upload":
                document = DocumentInput.from_bytes(uploaded.name, uploaded.getvalue(), mime_type=uploaded.type or "")
            if document is None:
                st.warning("Upload a document or paste the contract text first.")
                return

            with st.spinner("Reviewing against the standards library…"):
                with session_scope() as session:
                    from clausewise.repository import execute_audit

                    audit = execute_audit(
                        session,
                        tenant=tenant,
                        document=document,
                        user_id=user.id,
                        library_id=_resolve_library_id(tenant, library_id),
                        jurisdiction=jurisdiction,
                        source_label=source_label,
                        user_agent="streamlit",
                    )
                    audit_id = audit.id
                    cached = audit.cache_hit
                    warnings = [w for w in (document.warnings or [])]

            if cached:
                st.info("This document was reviewed before. The earlier result was reused rather than re-run.")
            for warning in warnings:
                st.warning(warning)
            st.session_state["active_audit"] = audit_id
        except Exception as exc:
            _handle_error(exc, tenant, blocker="audit_run")
            return

    active = st.session_state.get("active_audit")
    if active:
        st.divider()
        _render_audit_result(active, tenant, user)


def _library_labels(tenant: Tenant) -> list[str]:
    with session_scope() as session:
        libraries = libraries_for(session, tenant.id)
        return [f"{library.name} ({library.jurisdiction})" for library in libraries] or ["AAOIFI Shari'ah Standards"]


def _resolve_library_id(tenant: Tenant, label: str) -> Optional[str]:
    with session_scope() as session:
        libraries = libraries_for(session, tenant.id)
        for library in libraries:
            if f"{library.name} ({library.jurisdiction})" == label:
                return library.id
    return None


# =============================================================== page: repository
def page_repository(tenant: Tenant, user: User) -> None:
    st.header("Repository")

    with session_scope() as session:
        summary = portfolio_summary(session, tenant.id)
        decision = quota_decision_for(session, tenant)

    cols = st.columns(5)
    cols[0].metric("Reviews", summary["audits_total"])
    cols[1].metric("High risk", summary["by_risk"].get("High", 0))
    cols[2].metric("Critical findings", summary["by_severity"].get("critical", 0))
    cols[3].metric("Open remediation", summary["open_remediation"])
    cols[4].metric("Signed off", summary["signed_off"])

    if summary["by_issue"]:
        with st.expander("Findings by issue type"):
            import pandas as pd

            frame = pd.DataFrame(
                [
                    {"Issue": ISSUE_TYPE_LABELS.get(issue, issue), "Count": count}
                    for issue, count in sorted(summary["by_issue"].items(), key=lambda kv: -kv[1])
                ]
            )
            st.dataframe(frame, use_container_width=True, hide_index=True)

    st.divider()
    filters = st.columns(4)
    search = filters[0].text_input("Search filename or audit id")
    risk = filters[1].selectbox("Risk", ["Any", "High", "Medium", "Low"])
    status = filters[2].selectbox("Status", ["Any", "succeeded", "refused", "failed"])
    remediation = filters[3].selectbox("Remediation", ["Any", "open", "in_progress", "reviewed"])

    with session_scope() as session:
        audits = list_audits(
            session,
            tenant.id,
            search=search,
            risk_status=None if risk == "Any" else risk,
            status=None if status == "Any" else status,
            remediation_status=None if remediation == "Any" else remediation,
        )
        rows = []
        for audit in audits:
            contract = get_contract(session, tenant.id, audit.contract_id)
            rows.append(
                {
                    "Audit": audit.id[:12],
                    "Document": contract.filename if contract else "—",
                    "Type": (contract.document_type if contract else "—"),
                    "Date": C.fmt_dt(audit.finished_at or audit.created_at),
                    "Status": f"{C.STATUS_ICON.get(audit.status, '')} {audit.status}",
                    "Risk": audit.risk_status,
                    "Critical": audit.findings_critical,
                    "Findings": audit.findings_total,
                    "Referred": audit.findings_referred,
                    "Confidence": f"{audit.confidence:.0%}",
                    "Remediation": audit.remediation_status,
                    "id": audit.id,
                }
            )

    if not rows:
        st.info("No reviews yet. Run one from **Review a contract**.")
        return

    import pandas as pd

    frame = pd.DataFrame(rows)
    st.dataframe(
        frame.drop(columns=["id"]),
        use_container_width=True,
        hide_index=True,
        column_config={"Risk": st.column_config.TextColumn(width="small")},
    )

    options = {f"{row['Document']} · {row['Audit']} ({row['Date']})": row["id"] for row in rows}
    chosen = st.selectbox("Open a review", list(options.keys()))
    if chosen and st.button("Open", type="primary"):
        st.session_state["active_audit"] = options[chosen]
        st.session_state["nav"] = "Review a contract"
        st.rerun()


# =================================================================== page: batch
def page_batch(tenant: Tenant, user: User) -> None:
    st.header("Batch review")
    spec = get_plan(tenant.plan)

    if not plan_allows(spec.plan, Feature.BATCH_REVIEW):
        C.upgrade_card(
            plan=tenant.plan,
            blocker="batch_review",
            context=(
                "Review the whole template library at once — 180 documents, one heat map, one exception "
                "list. This is the deliverable your external Shari'ah audit asks for, and it is included "
                f"from {get_plan(Plan.TEAM).label}."
            ),
        )
        return

    st.caption(
        f"Up to {spec.batch_max_files} documents per batch on {spec.label}. "
        "Each document is reviewed with the same engine as a single review."
    )

    files = st.file_uploader(
        "Documents", type=["pdf", "docx", "txt"], accept_multiple_files=True, key="batch-files"
    )
    library_label = st.selectbox("Library", _library_labels(tenant), key="batch-library")
    jurisdiction = st.selectbox("Jurisdiction", list(JURISDICTION_PACKS.keys()), key="batch-jurisdiction")

    if st.button("Queue batch", type="primary", disabled=not files):
        try:
            from clausewise.jobs import BatchDocument, create_batch_job

            documents = [
                BatchDocument(
                    filename=item.name,
                    content=item.getvalue(),
                    mime_type=item.type or "application/pdf",
                )
                for item in files
            ]
            with session_scope() as session:
                job = create_batch_job(
                    session,
                    tenant=tenant,
                    documents=documents,
                    user_id=user.id,
                    library_id=_resolve_library_id(tenant, library_label),
                    jurisdiction=jurisdiction,
                )
                st.session_state["active_job"] = job.id
            st.success(f"Queued {job.total} document(s).")
        except Exception as exc:
            _handle_error(exc, tenant, blocker="batch_review")

    job_id = st.session_state.get("active_job")
    if not job_id:
        return

    st.divider()
    with session_scope() as session:
        from clausewise.jobs import get_job, job_items, run_job

        job = get_job(session, tenant.id, job_id)
        if job is None:
            st.error("That batch is not available.")
            return

        if job.status in {"queued", "running"}:
            if st.button("Process batch now", type="primary"):
                with st.spinner("Reviewing…"):
                    run_job(session, job)
                    session.commit()
                st.rerun()
            st.info(
                "Queued. The worker processes this automatically in production; here you can run it inline."
            )

        job = get_job(session, tenant.id, job_id)
        cols = st.columns(4)
        cols[0].metric("Status", f"{C.STATUS_ICON.get(job.status, '')} {job.status}")
        cols[1].metric("Processed", job.processed)
        cols[2].metric("Failed", job.failed)
        cols[3].metric("Total", job.total)

        if job.result:
            st.markdown("##### Portfolio result")
            risk = job.result.get("by_risk", {})
            cols = st.columns(4)
            cols[0].metric("Audits", job.result.get("audits", 0))
            cols[1].metric("High risk", risk.get("High", 0))
            cols[2].metric("Medium risk", risk.get("Medium", 0))
            cols[3].metric("Critical findings", job.result.get("critical_findings", 0))

        items = job_items(session, job.id)
        rows = [
            {
                "Document": _item_filename(session, tenant, item),
                "Status": f"{C.STATUS_ICON.get(item.status, '')} {item.status}",
                "Audit": (item.audit_id or "")[:12],
                "Error": (item.error or "")[:160],
                "audit_id": item.audit_id or "",
            }
            for item in items
        ]

        if rows:
            import pandas as pd

            st.dataframe(pd.DataFrame(rows).drop(columns=["audit_id"]), use_container_width=True, hide_index=True)
            openable = {f"{r['Document']} ({r['Status']})": r["audit_id"] for r in rows if r["audit_id"]}
            if openable:
                chosen = st.selectbox("Open a result", list(openable.keys()))
                if st.button("Open review"):
                    st.session_state["active_audit"] = openable[chosen]
                    st.session_state["nav"] = "Review a contract"
                    st.rerun()


def _item_filename(session: Any, tenant: Tenant, item: Any) -> str:
    if not item.contract_id:
        return "—"
    contract = get_contract(session, tenant.id, item.contract_id)
    return contract.filename if contract else "—"


# =============================================================== page: standards
def page_standards(tenant: Tenant, user: User) -> None:
    st.header("Standards library")
    st.caption(
        "Findings are scored against a library. The global AAOIFI library ships with the product; a "
        "tenant library lets you encode your own Shari'ah board resolutions and jurisdiction rulebook."
    )

    with session_scope() as session:
        libraries = libraries_for(session, tenant.id)
        rows = [
            {
                "Library": library.name,
                "Jurisdiction": library.jurisdiction,
                "Scope": "Global (product)" if library.tenant_id is None else "Your organisation",
                "Version": library.version,
                "Reviewed by": library.reviewed_by or "—",
                "id": library.id,
            }
            for library in libraries
        ]

    import pandas as pd

    st.dataframe(pd.DataFrame(rows).drop(columns=["id"]), use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("#### Registry entries in the global library")
    table = [
        {
            "Standard": spec.standard_id,
            "Title": spec.title,
            "Domain": spec.domain,
            "Default severity": spec.default_severity.value,
            "Verification": spec.verify_status.replace("_", " "),
        }
        for spec in STANDARD_INDEX.values()
    ]
    st.dataframe(pd.DataFrame(table), use_container_width=True, hide_index=True)

    unverified = standards_needing_verification()
    if unverified:
        st.warning(
            "These entries are marked **confirm before use**: their numbering or scope has not yet been "
            "validated against a licensed copy of the standards. Confirm them before relying on those "
            "citations: " + ", ".join(s.standard_id for s in unverified)
        )
        st.caption(
            "Requirement summaries in the registry are our own paraphrases written for navigation. The "
            "authoritative text is your own licensed copy of the standards."
        )

    st.divider()
    st.markdown("#### Your own standards")
    if not plan_allows(tenant.plan, Feature.CUSTOM_STANDARDS):
        C.upgrade_card(
            plan=tenant.plan,
            blocker="custom_standards",
            context=(
                "Encode your internal Shari'ah audit manual, your board's resolutions and your local "
                "regulator's rulebook. After that, every review is scored against your governance, not "
                f"a generic baseline. Included from {get_plan(Plan.TEAM).label}."
            ),
        )
        return

    with st.form("new-library"):
        name = st.text_input("Library name", placeholder="Example: Our SSB resolutions 2026")
        jurisdiction = st.selectbox("Jurisdiction", list(JURISDICTION_PACKS.keys()))
        reviewed_by = st.text_input("Countersigned by", placeholder="Name of Shari'ah reviewer")
        if st.form_submit_button("Create library", type="primary"):
            if not name.strip():
                st.error("Give the library a name.")
            else:
                from clausewise.models import StandardLibrary

                with session_scope() as session:
                    session.add(
                        StandardLibrary(
                            tenant_id=tenant.id,
                            name=name.strip(),
                            jurisdiction=jurisdiction,
                            reviewed_by=reviewed_by.strip(),
                            description="Tenant-authored standards library.",
                        )
                    )
                st.success("Library created. Add entries below or ask us to import your policy pack.")
                st.rerun()

    with st.expander("Add a standard entry (e.g. a board resolution)"):
        with st.form("new-entry"):
            library_label = st.selectbox("Library", _library_labels(tenant))
            standard_id = st.text_input("Standard id", placeholder="CLIENT-SSB-14")
            title = st.text_input("Title")
            citation_ref = st.text_input("Citation reference", placeholder="Board resolution 14, meeting 2026-02")
            summary = st.text_area("What it requires", height=100)
            breaches = st.text_area("Commonly breached by", height=80)
            severity = st.selectbox("Default severity", ["critical", "high", "medium", "advisory"], index=1)
            keywords = st.text_input("Detection keywords (comma separated)", placeholder="late fee, retained")
            if st.form_submit_button("Add entry"):
                from clausewise.models import StandardEntry

                target = _resolve_library_id(tenant, library_label)
                if not target or not standard_id.strip() or not title.strip():
                    st.error("Library, standard id and title are required.")
                else:
                    patterns = [k.strip() for k in keywords.split(",") if k.strip()]
                    with session_scope() as session:
                        session.add(
                            StandardEntry(
                                library_id=target,
                                standard_id=standard_id.strip().upper(),
                                title=title.strip(),
                                domain="custom",
                                citation_ref=citation_ref.strip(),
                                requirement_summary=summary.strip(),
                                common_breaches=breaches.strip(),
                                default_severity=severity,
                                detect_hints={"patterns": patterns} if patterns else None,
                                verify_status="verified_title",
                            )
                        )
                    st.success("Entry added. It will be cited on the next review that uses this library.")
                    st.rerun()


# ====================================================================== page: team
def page_team(tenant: Tenant, user: User) -> None:
    st.header("Team")
    spec = get_plan(tenant.plan)

    with session_scope() as session:
        from clausewise.models import User as UserModel

        members = (
            session.query(UserModel)
            .filter(UserModel.tenant_id == tenant.id)
            .order_by(UserModel.created_at)
            .all()
        )
        rows = [
            {
                "Name": member.full_name or "—",
                "Email": member.email,
                "Role": member.role,
                "Active": "yes" if member.is_active else "no",
                "Last sign-in": C.fmt_dt(member.last_login_at),
            }
            for member in members
        ]

    import pandas as pd

    cols = st.columns(2)
    used = len([r for r in rows if r["Active"] == "yes"])
    limit = "unlimited" if spec.seats >= 10**9 else spec.seats
    cols[0].metric("Active seats", used, f"of {limit}")
    cols[1].metric("Plan", spec.label)

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    if not auth.can(user, "manage_users"):
        st.info("Only owners and admins can manage members.")
        return

    if used >= spec.seats and spec.seats < 10**9:
        C.upgrade_card(
            plan=tenant.plan,
            blocker="seats",
            context=f"You are using all {spec.seats} seat(s) on {spec.label}.",
        )

    with st.expander("Invite a reviewer", expanded=False):
        with st.form("invite"):
            email = st.text_input("Work email")
            full_name = st.text_input("Name")
            role = st.selectbox(
                "Role",
                ["reviewer", "analyst", "viewer", "admin"],
                help=(
                    "reviewer can run reviews, export and sign off · analyst can run and export · "
                    "viewer can only read · admin can also manage members and keys"
                ),
            )
            password = st.text_input("Temporary password", type="password")
            if st.form_submit_button("Create member", type="primary"):
                try:
                    with session_scope() as session:
                        auth.create_member(
                            session,
                            tenant=tenant,
                            email=email,
                            password=password,
                            full_name=full_name,
                            role=role,
                            acting_user=user,
                        )
                    st.success("Member created. Ask them to change the password on first sign-in.")
                    st.rerun()
                except Exception as exc:
                    _handle_error(exc, tenant, blocker="seats")

    with st.expander("API keys"):
        if not plan_allows(tenant.plan, Feature.API_ACCESS):
            st.caption(f"API access is included from {get_plan(Plan.INSTITUTION).label}.")
        else:
            with session_scope() as session:
                keys = auth_repository_keys(session, tenant.id)
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "Name": key.name,
                                "Prefix": key.key_prefix,
                                "Scopes": key.scopes,
                                "Last used": C.fmt_dt(key.last_used_at),
                                "Revoked": "yes" if key.revoked else "no",
                            }
                            for key in keys
                        ]
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
            if st.button("Issue a new API key"):
                try:
                    with session_scope() as session:
                        _, plaintext = auth.issue_api_key(session, tenant=tenant, acting_user=user)
                    st.success("Copy this key now — it is not shown again.")
                    st.code(plaintext, language=None)
                except Exception as exc:
                    _handle_error(exc, tenant, blocker="api_access")


def auth_repository_keys(session: Any, tenant_id: str):
    from clausewise.repository import api_keys_for

    return api_keys_for(session, tenant_id)


# ================================================================== page: billing
def page_billing(tenant: Tenant, user: User) -> None:
    st.header("Plan & billing")
    spec = get_plan(tenant.plan)

    cols = st.columns(4)
    cols[0].metric("Current plan", spec.label)
    cols[1].metric("Monthly", C.money(spec.price_monthly))
    with session_scope() as session:
        used = usage_this_period(session, tenant.id)
        allowance = "unlimited" if spec.audits_per_month >= 10**9 else spec.audits_per_month
        cols[2].metric("Reviews this period", used, f"of {allowance}")
        cols[3].metric("Retention", f"{spec.retention_days} days")

    C.pricing_table()

    st.divider()
    st.markdown("#### Change plan")
    changeable = [p for p in (Plan.PRACTITIONER, Plan.TEAM, Plan.INSTITUTION) if p.value != spec.plan.value]
    cols = st.columns(len(changeable) + 1)
    for column, plan in zip(cols, changeable):
        target = get_plan(plan)
        with column:
            if st.button(
                f"{target.label} · {C.money(target.price_monthly)}",
                use_container_width=True,
                key=f"change-{plan.value}",
            ):
                _start_change(tenant, user, plan)
    with cols[-1]:
        if st.button("Talk to us", use_container_width=True, key="change-enterprise"):
            st.session_state["nav"] = "Talk to us"
            st.rerun()


def _start_change(tenant: Tenant, user: User, plan: Plan) -> None:
    settings = get_settings()
    if settings.billing_enabled:
        from clausewise.billing import create_checkout_session

        with session_scope() as session:
            url = create_checkout_session(session, tenant=tenant, user=user, target_plan=plan)
            st.markdown(f"[Proceed to checkout →]({url})")
    else:
        with session_scope() as session:
            from clausewise.billing import provision_plan

            provision_plan(session, tenant=tenant, plan=plan, note=f"Self-serve change by {user.email}")
        st.success(f"Plan updated to {get_plan(plan).label}.")
        st.rerun()


# ==================================================================== page: sales
def page_sales(tenant: Tenant, user: User) -> None:
    st.header("Talk to us")
    st.caption("Custom standards builds, enterprise deployments, and Shari'ah board workflow integration.")

    settings = get_settings()
    if settings.sales_calendar_url:
        st.markdown(f"[📅 Book a 30-minute walkthrough on our calendar]({settings.sales_calendar_url})")
        st.divider()

    with st.form("contact"):
        st.markdown("##### Request a custom standards build or in-region deployment")
        topic = st.selectbox(
            "Topic",
            [
                "Custom standards library build ($2,500 - $10,000)",
                "Annual Shari'ah audit pack ($5,000 - $15,000/yr)",
                "White-label partner workspace ($1,500/mo)",
                "Enterprise on-prem / VPC deployment",
                "General enquiry",
            ],
        )
        notes = st.text_area("Tell us about your organization and volume", height=120)
        if st.form_submit_button("Send request", type="primary"):
            with session_scope() as session:
                capture_lead(
                    session,
                    email=user.email,
                    company=tenant.name,
                    full_name=user.full_name,
                    source="sales_tab",
                    notes=f"[{topic}] {notes}",
                )
            st.success("Request received. We will respond on your work email within one business day.")


# ==================================================================== page: admin
def page_admin(tenant: Tenant, user: User) -> None:
    if not user.is_platform_admin:
        st.error("Platform admin privileges required.")
        return

    st.header("Platform Admin")

    with session_scope() as session:
        metrics = platform_metrics(session)

    cols = st.columns(4)
    cols[0].metric("Workspaces", metrics["tenants_total"])
    cols[1].metric("Users", metrics["users_total"])
    cols[2].metric("Total reviews", metrics["audits_total"])
    cols[3].metric("Reviews (30d)", metrics["audits_30d"])

    st.divider()
    st.markdown("#### Audit log")
    with session_scope() as session:
        logs = audit_log_for(session, tenant_id=None, limit=100)
        import pandas as pd

        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "When": C.fmt_dt(entry.created_at),
                        "Action": entry.action,
                        "Tenant": entry.tenant_id[:8] if entry.tenant_id else "system",
                        "User": entry.user_id[:8] if entry.user_id else "system",
                        "IP": entry.ip_address or "—",
                        "Details": str(entry.details or {}),
                    }
                    for entry in logs
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )

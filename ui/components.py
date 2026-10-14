"""Reusable Streamlit pieces used by ui/pages.py.

Nothing here applies a business rule. Plan limits, feature gates and quota
state all come from `clausewise.entitlements`; this module only renders them.
"""

from __future__ import annotations

import html
from datetime import datetime
from typing import Any, Optional

import streamlit as st

from clausewise.entitlements import (
    PRICING_LADDER,
    Feature,
    QuotaState,
    get_plan,
    plan_allows,
    upgrade_cta_block,
)
from clausewise.standards import ISSUE_TYPE_LABELS

_UNLIMITED = 10**9

STATUS_ICON = {
    "queued": "⏳",
    "running": "⏳",
    "succeeded": "✅",
    "completed": "✅",
    "partial": "⚠️",
    "refused": "🚫",
    "failed": "❌",
}

SEVERITY_ICON = {
    "critical": "🔴",
    "high": "🟠",
    "medium": "🟡",
    "advisory": "🔵",
    "referred": "⚪",
}

DISCLAIMER = (
    "This report is an assistive screening result. It is not a fatwa, not a Shari'ah ruling and not "
    "legal advice. Compliance determinations rest with your Shari'ah board or appointed reviewer."
)


# ===================================================================== formatting
def fmt_dt(value: Optional[datetime]) -> str:
    """Timestamps are stored as naive UTC; show them as such."""
    if not value:
        return "—"
    if isinstance(value, datetime):
        return value.strftime("%d %b %Y, %H:%M UTC")
    return str(value)


def money(value: Optional[float]) -> str:
    if value is None:
        return "Custom"
    return f"${value:,.0f}"


def _limit(value: int) -> str:
    return "Unlimited" if value >= _UNLIMITED else f"{value:,}"


# ======================================================================== sidebar
def plan_badge(tenant: Any) -> None:
    spec = get_plan(tenant.plan)
    st.sidebar.markdown(f"**Plan:** {spec.label}")


def usage_meter(decision: Any, plan: Any = None) -> None:
    if decision.state == QuotaState.UNLIMITED:
        st.sidebar.caption(f"Reviews this period: {decision.used} (unlimited)")
        return

    fraction = min(max(decision.percent_used / 100.0, 0.0), 1.0)
    st.sidebar.progress(fraction, text=f"{decision.used} of {decision.limit} reviews used")
    if decision.state in {QuotaState.WARNING, QuotaState.BLOCKED}:
        st.sidebar.warning(decision.message)
    else:
        st.sidebar.caption(decision.message)


# ===================================================================== upgrade card
def upgrade_card(plan: Any, blocker: str = "", context: str = "") -> None:
    block = upgrade_cta_block(plan, blocker)
    with st.container(border=True):
        st.markdown(f"##### {block['headline']}")
        if context:
            st.write(context)
        if block.get("body"):
            st.caption(block["body"])
        key = f"upgrade-{blocker}-{abs(hash((context, block['cta'])))}"
        if st.button(block["cta"], key=key, type="primary"):
            st.session_state["nav"] = "Plan & billing" if block.get("target_plan") else "Talk to us"
            st.rerun()


# ================================================================== pricing table
def pricing_table() -> None:
    import pandas as pd

    rows = []
    for tier in PRICING_LADDER:
        rows.append(
            {
                "Plan": tier["label"],
                "Monthly": money(tier["price_monthly"]),
                "Annual": money(tier["price_annual"]),
                "Reviews / month": _limit(tier["audits_per_month"]),
                "Seats": _limit(tier["seats"]),
                "Per review": money(tier["per_audit"]) if tier["per_audit"] else "—",
                "Support": tier["support"],
                "Best for": tier["target_buyer"],
            }
        )
    st.markdown("#### Plans")
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ================================================================ audit presentation
def refusal_panel(audit: Any) -> None:
    with st.container(border=True):
        st.markdown("##### 🚫 Clausewise declined to give a view")
        reason = (audit.refusal_reason or "unspecified").replace("_", " ")
        st.write(f"Reason: **{reason}**")
        if audit.overall_summary:
            st.write(audit.overall_summary)
        if audit.review_reason:
            st.caption(f"Reviewer action: {audit.review_reason}")
        st.caption(
            "A refusal means the engine could not produce a reliable result. "
            "Send this document to your Shari'ah reviewer."
        )


def audit_header(audit: Any, contract: Any) -> None:
    name = contract.filename if contract else "Document"
    st.markdown(f"### {name}")

    cols = st.columns(5)
    cols[0].metric("Risk", audit.risk_status)
    cols[1].metric("Findings", audit.findings_total)
    cols[2].metric("Critical", audit.findings_critical)
    cols[3].metric("Referred", audit.findings_referred)
    cols[4].metric("Confidence", f"{audit.confidence:.0%}")

    bits = [
        f"Reviewed {fmt_dt(audit.finished_at or audit.created_at)}",
        f"Audit {audit.id[:12]}",
    ]
    if audit.model:
        bits.append(f"Model {audit.model}")
    if audit.prompt_version:
        bits.append(f"Prompt {audit.prompt_version}")
    if audit.standards_version:
        bits.append(f"Standards {audit.standards_version}")
    if audit.redaction_applied:
        bits.append("PII redacted")
    if audit.cache_hit:
        bits.append("Reused earlier result")
    st.caption(" · ".join(bits))


def finding_card(finding: Any, index: int) -> None:
    severity = (finding.severity or "medium").lower()
    icon = SEVERITY_ICON.get(severity, "⚪")
    issue = ISSUE_TYPE_LABELS.get(finding.issue_type, finding.issue_type)

    with st.container(border=True):
        clause = f" · Clause {finding.clause_ref}" if finding.clause_ref else ""
        st.markdown(f"**{index}. {icon} {severity.title()}**{clause} · {issue}")

        if finding.clause_excerpt:
            st.markdown(f"> {finding.clause_excerpt}")

        if finding.standard_id:
            cite = f"**{finding.standard_id}**"
            if finding.standard_title:
                cite += f" · {finding.standard_title}"
            if finding.citation_ref:
                cite += f" ({finding.citation_ref})"
            st.markdown(f"Standard cited: {cite}")
        else:
            st.markdown("Standard cited: _none matched, referred to your Shari'ah board_")

        if finding.rationale:
            st.markdown("**Why this matters**")
            st.write(finding.rationale)

        if finding.remedial_wording:
            st.markdown("**Suggested replacement wording**")
            st.info(finding.remedial_wording)

        meta = [f"Confidence {finding.confidence:.0%}"]
        meta.append("Rule-detected" if finding.detected_by == "rule" else "Model-detected")
        if finding.citation_status:
            meta.append(f"Citation: {finding.citation_status.replace('_', ' ')}")
        if finding.needs_human_review:
            meta.append("Needs human review")
        st.caption(" · ".join(meta))


# ========================================================================= export
def _report_data(audit: Any, contract: Any, findings: list, tenant: Any, user: Any) -> dict:
    brand = tenant.brand_name if getattr(tenant, "is_white_label", False) and tenant.brand_name else tenant.name
    filename = contract.filename if contract else "document"
    return {
        "brand": brand,
        "title": f"Shari'ah contract risk review: {filename}",
        "meta": [
            ("Document", filename),
            ("Audit ID", audit.id),
            ("Reviewed", fmt_dt(audit.finished_at or audit.created_at)),
            ("Overall risk", audit.risk_status),
            ("Findings", f"{audit.findings_total} ({audit.findings_critical} critical, {audit.findings_referred} referred)"),
            ("Confidence", f"{audit.confidence:.0%}"),
            ("Model / prompt", f"{audit.model or '—'} / {audit.prompt_version or '—'}"),
            ("Standards version", audit.standards_version or "—"),
            ("PII redacted before analysis", "yes" if audit.redaction_applied else "no"),
            ("Prepared for", user.full_name or user.email),
        ],
        "summary": audit.overall_summary or "",
        "findings": [
            {
                "n": i,
                "severity": (f.severity or "medium").title(),
                "clause": f.clause_ref or "",
                "issue": ISSUE_TYPE_LABELS.get(f.issue_type, f.issue_type),
                "excerpt": f.clause_excerpt or "",
                "standard": " · ".join(
                    p for p in [f.standard_id or "", f.standard_title or "", f.citation_ref or ""] if p
                )
                or "None matched, referred to Shari'ah board",
                "rationale": f.rationale or "",
                "remedy": f.remedial_wording or "",
            }
            for i, f in enumerate(findings, start=1)
        ],
        "footer": tenant.report_footer or "",
    }


def _report_markdown(data: dict) -> str:
    out = [f"# {data['title']}", f"_{data['brand']}_", ""]
    out += [f"- **{k}:** {v}" for k, v in data["meta"]]
    out += ["", "## Executive summary", data["summary"] or "No summary recorded.", "", "## Findings", ""]
    if not data["findings"]:
        out.append("No clause was flagged against the active standards library.")
    for f in data["findings"]:
        clause = f" (clause {f['clause']})" if f["clause"] else ""
        out += [f"### {f['n']}. {f['severity']}: {f['issue']}{clause}", ""]
        if f["excerpt"]:
            out += [f"> {f['excerpt']}", ""]
        out += [f"**Standard:** {f['standard']}", ""]
        if f["rationale"]:
            out += [f"**Rationale:** {f['rationale']}", ""]
        if f["remedy"]:
            out += [f"**Suggested replacement wording:** {f['remedy']}", ""]
    out += [
        "## Reviewer sign-off",
        "",
        "Reviewer name: ______________________   Signature: ______________________   Date: ____________",
        "",
        f"_{DISCLAIMER}_",
    ]
    if data["footer"]:
        out += ["", data["footer"]]
    return "\n".join(out)


def _report_html(data: dict) -> str:
    e = html.escape
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        f"<title>{e(data['title'])}</title>",
        "<style>body{font-family:Georgia,serif;max-width:820px;margin:2rem auto;padding:0 1rem;line-height:1.5}"
        "h1{font-size:1.6rem}h3{margin-top:1.6rem}blockquote{border-left:3px solid #999;margin:.6rem 0;"
        "padding-left:.8rem;color:#444}table{border-collapse:collapse}td{padding:.2rem .8rem .2rem 0;"
        "vertical-align:top}.sig{margin-top:2rem}.note{color:#555;font-size:.9rem}"
        "@media print{body{margin:0}}</style></head><body>",
        f"<h1>{e(data['title'])}</h1><p><em>{e(data['brand'])}</em></p><table>",
    ]
    parts += [f"<tr><td><strong>{e(k)}</strong></td><td>{e(str(v))}</td></tr>" for k, v in data["meta"]]
    parts += ["</table><h2>Executive summary</h2>", f"<p>{e(data['summary'] or 'No summary recorded.')}</p>"]
    parts.append("<h2>Findings</h2>")
    if not data["findings"]:
        parts.append("<p>No clause was flagged against the active standards library.</p>")
    for f in data["findings"]:
        clause = f" (clause {e(f['clause'])})" if f["clause"] else ""
        parts.append(f"<h3>{f['n']}. {e(f['severity'])}: {e(f['issue'])}{clause}</h3>")
        if f["excerpt"]:
            parts.append(f"<blockquote>{e(f['excerpt'])}</blockquote>")
        parts.append(f"<p><strong>Standard:</strong> {e(f['standard'])}</p>")
        if f["rationale"]:
            parts.append(f"<p><strong>Rationale:</strong> {e(f['rationale'])}</p>")
        if f["remedy"]:
            parts.append(f"<p><strong>Suggested replacement wording:</strong> {e(f['remedy'])}</p>")
    parts += [
        "<h2>Reviewer sign-off</h2>",
        "<p class='sig'>Reviewer name: ______________________ &nbsp; Signature: ______________________ "
        "&nbsp; Date: ____________</p>",
        f"<p class='note'>{e(DISCLAIMER)}</p>",
    ]
    if data["footer"]:
        parts.append(f"<p class='note'>{e(data['footer'])}</p>")
    parts.append("</body></html>")
    return "".join(parts)


def export_controls(audit: Any, contract: Any, findings: list, tenant: Any, user: Any) -> None:
    if not plan_allows(tenant.plan, Feature.PDF_EXPORT):
        upgrade_card(
            plan=tenant.plan,
            blocker=Feature.PDF_EXPORT.value,
            context="Board-ready report export is not included in your plan. Findings stay available on screen.",
        )
        return

    data = _report_data(audit, contract, findings, tenant, user)
    stem = f"clausewise-{audit.id[:12]}"
    cols = st.columns([1, 1, 2])
    cols[0].download_button(
        "Download report (HTML)",
        data=_report_html(data),
        file_name=f"{stem}.html",
        mime="text/html",
        key=f"dl-html-{audit.id}",
    )
    cols[1].download_button(
        "Download (Markdown)",
        data=_report_markdown(data),
        file_name=f"{stem}.md",
        mime="text/markdown",
        key=f"dl-md-{audit.id}",
    )
    cols[2].caption("Open the HTML file and use Print → Save as PDF for a board-ready copy.")

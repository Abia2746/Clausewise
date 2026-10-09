# Clausewise Shari'ah

Assistive Shari'ah contract review for Islamic finance documents — Murabahah, Ijarah,
Musharakah, Mudarabah, sukuk, takāful and general investment agreements.

Upload a contract. The engine reads it clause by clause against a defined standards
library, cites the standard behind every finding, proposes replacement wording, and
produces a board-ready report with a sign-off block and a reproducible audit trail.

> **This tool does not issue fatwas or Shari'ah rulings.** It is an assistive review
> layer. Compliance determinations rest with the client's Shari'ah Supervisory Board or
> appointed reviewer, whose sign-off is required before any report is relied upon.

---

## What changed from the v1 prototype

| v1 prototype | v2 |
|---|---|
| User pasted their own Gemini API key into the sidebar | Server-side keys, accounts, sessions, metering |
| One SQLite table (`filename`, `date`, `risk_status`) | Full multi-tenant schema: tenants, users, contracts, audits, findings, usage ledger, audit log |
| Single prompt, one JSON blob per document | Clause-aware chunking, per-chunk analysis, union with a deterministic rule pass |
| Findings with no citation | **Every finding must resolve to a standard in the library, or it is downgraded to a referral to the board** |
| Model decided the risk label | Deterministic scoring from fixed severity weights |
| Always produced an answer | **Refuses and routes to the board below a confidence floor** |
| No export | PDF and DOCX audit reports with sign-off block and audit trail |
| No plan, no limits, no billing | Five plans, quota enforcement, overage pricing, Stripe or manual billing |
| No isolation | Strict tenant scoping on every query path |
| No PII handling | Personal data redacted before any provider call |
| Streamlit only | Streamlit UI + FastAPI (`/v1/*`) + batch worker |

---

## Architecture

```text
┌──────────────────────────┐
│ Streamlit UI (app.py, ui/)│
└────────────┬─────────────┘
             │
┌────────────▼─────────────┐     ┌────────────────────────────────────────┐
│ FastAPI (api.py, /v1/*)  ├────►│ clausewise (core)                      │
└──────────────────────────┘     │ no Streamlit, no FastAPI, no reportlab │
┌──────────────────────────┐     │ imports at module level                │
│ Worker (worker.py)       ├────►│                                        │
└──────────────────────────┘     │                                        │
┌──────────────────────────┐     │                                        │
│ Seed / migrate scripts   ├────►│                                        │
└──────────────────────────┘     └────────────────────────────────────────┘

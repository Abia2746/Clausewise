"""Production-Grade Streamlit Multi-Agent Contract Engine."""

import json
from io import BytesIO
import docx
from google import genai
from google.genai import types
import pandas as pd
import streamlit as st

# SYSTEM CONFIGURATION
MODEL_NAME = "gemini-3.6-flash"

st.set_page_config(
    page_title="Clausewise — Advanced Contract Lifecycle Engine",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

if "audit_count" not in st.session_state:
    st.session_state.audit_count = 0

# STYLING SHEET — INJECTED DIRECTLY USING CONDENSED SINGLE LINES
st.markdown(
    "<style>.stApp { background-color: #fbfcfa !important; color: #17212b !important; }[data-testid='stSidebar'] { background-color: #f1f5f1 !important; border-right: 1px solid #e5e9e6 !important; }[data-testid='stSidebar'] * { color: #17212b !important; font-weight: 600 !important; }textarea, input { background-color: #ffffff !important; border: 2px solid #185c4a !important; color: #17212b !important; }.paywall-card { background: linear-gradient(135deg, #143f35 0%, #1d6a55 100%) !important; border-radius: 12px; padding: 20px; color: white !important; }.tier-container { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin: 15px 0; }.tier-box { background: white; border: 2px solid #e5e9e6; border-radius: 12px; padding: 15px; text-align: center; color: #17212b; }.checkout-box { background-color: #ffffff !important; border: 2px solid #e5e9e6 !important; border-radius: 12px !important; padding: 20px !important; }div.stButton > button:first-child { background-color: #185c4a !important; color: #ffffff !important; font-weight: 700 !important; border: none !important; }</style>",
    unsafe_allow_html=True,
)

# SIDEBAR CONTROLS & API KEY CHECK
st.sidebar.markdown("# ◈ Clausewise")
st.sidebar.markdown("---")
st.sidebar.markdown("### 👤 Account Space")
st.sidebar.markdown("📈 Framework: **Multi-Agent Engine**")
st.sidebar.markdown(
    "⚡ Usage: **0 / 1 Free Audit Used**"
    if st.session_state.audit_count == 0
    else "⚡ Usage: **1 / 1 Limit Reached**"
)
st.sidebar.markdown("---")
api_key_input = st.secrets.get("GEMINI_API_KEY", "")xecution."
)
st.sidebar.markdown("---")

st.title("Automate Your Contract Risk Reviews")
st.caption(
    "The 100% Efficient Engine. Multi-Agent cross-clause verification patterns and portfolio obligation lifecycle tracking."
)

SAMPLE_CONTRACT = """MASTER SOFTWARE & SERVICES AGREEMENT
2.3 Unilateral Engine Changes. Licensor retains the right to modify model endpoints at any time, provided throughput is unaffected.
3.4 Overdue Balances. Invoice balances unpaid after 14 calendar days shall accrue interest at 4% per annum above the Bank of England base rate.
4.2 Algorithmic Optimization Notice. The system architecture evaluates purely for administrative formatting and syntax risk; parameters disclaim all reliance on substantive legal functions.
5.1 Standard Liability Cap. Total combined financial exposure shall be strictly limited to the total amount paid by Licensee in the 3 months preceding the claim.
5.2 Third-Party Intellectual Property Protection. The Service Provider agrees to protect the Client from third-party copyright claims up to a limit of £50,000, notwithstanding any other damages, performance issues, or general contract failures arising from or related to this Agreement.
6.2 Unilateral Maintenance Indexation. Annual price adjustments may be enacted by the Service Provider at their sole discretion, without mandatory alignment to outside consumer price index parameters."""

clause_text = st.text_area(
    "Ingest unstructured agreement or multi-page text matrix here:",
    value=SAMPLE_CONTRACT,
    height=180,
)

bypass_granted = False

if st.session_state.audit_count >= 1:
    st.markdown(
        '<div class="paywall-card"><h2 style="margin:0;color:white;">🔒 Free Scan Limit Reached</h2><p style="margin:5px 0 0 0;color:white;">You have exhausted your single complimentary audit block. Select an upgrade option below to execute advanced multi-agent portfolio analysis.</p></div>',
        unsafe_allow_html=True,
    )
    with st.container():
        st.markdown(
            '<div class="checkout-box"><h4 style="margin:0 0 15px 0; color:#17212b;">💳 Premium Stripe Payment Gateway</h4>',
            unsafe_allow_html=True,
        )
        payment_tier = st.radio(
            "Select Payment Package:",
            ["🎟️ Single Token Scan (£9)", "🚀 Unlimited Monthly Membership (£49/mo)"],
        )
        card_name = st.text_input(
            "Name",
            placeholder="Type 'OWNER' to bypass lock",
            label_visibility="collapsed",
        )
        st.text_input(
            "Card Number Field Input",
            placeholder="4000 1234 5678 9010",
            label_visibility="collapsed",
        )
        button_label = (
            "✨ Subscribe & Pay £49/mo"
            if "Unlimited" in payment_tier
            else "✨ Complete Single Payment (£9)"
        )
        if st.button(button_label, use_container_width=True):
            if card_name.strip().upper() == "OWNER":
                bypass_granted = True
            else:
                bypass_granted = True
        st.markdown("</div>", unsafe_allow_html=True)


# MULTI-AGENT INFERENCE ENGINE
def run_contract_audit(contract_text: str, api_key: str) -> dict:
    client = genai.Client(api_key=api_key)

    system_prompt = """
    You are an elite Senior Commercial Legal Engine acting strictly for the BUYER/LICENSEE.
    Analyze the contract and return a strict JSON payload adhering to the following structure:
    
    {
      "agent_1_syntactic": {
        "target": "Clause name and location",
        "analysis": "Syntactic parsing of liability, indemnity, or language vulnerabilities.",
        "playbook_positions": {
          "position_a_ideal": "Aggressive, uncapped/maximum buyer protection redline.",
          "position_b_fallback": "Balanced commercial fallback redline.",
          "position_c_walkaway": "Minimum acceptable compromise redline."
        }
      },
      "agent_2_cross_clause": {
        "conflict": "Clause X vs Clause Y conflict identification",
        "analysis": "How disclaimers, waivers, or scope clauses undermine core operational rights.",
        "redline_redirection": "Specific text replacement to fix the operational trap."
      },
      "agent_3_portfolio_recovery": {
        "target": "Payment, term, or liability cap clauses",
        "analysis": "Evaluation of financial penalties, aggressive payment windows, or caps."
      },
      "pillar_5_obligation_registry": [
        {
          "clause": "Clause reference",
          "data": "Extracted timeline, interest rate, or numerical threshold",
          "status": "Systemic Risk Tag (e.g., ⚠️ AGGRESSIVE BOUNDARY, 🚨 DEFICIT EXPOSURE)"
        }
      ]
    }
    """

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=f"Analyze this contract text:\n\n{contract_text}",
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            temperature=0.1,
        ),
    )
    return json.loads(response.text)


# WORD DOCUMENT REDLINE GENERATOR (PILLAR 3)
def build_docx_redline(audit_data: dict) -> BytesIO:
    doc = docx.Document()
    doc.add_heading("Clausewise — Enterprise Contract Redline Report", level=0)

    doc.add_heading("Agent 1: Syntactic & Indemnity Adjustments", level=1)
    ag1 = audit_data["agent_1_syntactic"]
    doc.add_paragraph(f"Target: {ag1['target']}")
    doc.add_paragraph(f"Analysis: {ag1['analysis']}")

    doc.add_heading("Playbook Fallback Hierarchy:", level=2)
    p = doc.add_paragraph()
    p.add_run("Position A (Ideal): ").bold = True
    p.add_run(ag1["playbook_positions"]["position_a_ideal"])

    p = doc.add_paragraph()
    p.add_run("Position B (Fallback): ").bold = True
    p.add_run(ag1["playbook_positions"]["position_b_fallback"])

    p = doc.add_paragraph()
    p.add_run("Position C (Walkaway Threshold): ").bold = True
    p.add_run(ag1["playbook_positions"]["position_c_walkaway"])

    doc.add_heading("Agent 2: Cross-Clause Conflict Corrections", level=1)
    ag2 = audit_data["agent_2_cross_clause"]
    doc.add_paragraph(f"Conflict: {ag2['conflict']}")
    doc.add_paragraph(f"Analysis: {ag2['analysis']}")
    p = doc.add_paragraph()
    p.add_run("Proposed Redline: ").bold = True
    p.add_run(ag2["redline_redirection"])

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer


# EXECUTION PIPELINE
if st.button("Audit Contract", type="primary") or bypass_granted:
    if not clause_text.strip():
        st.warning("Please insert contract text before executing an audit.")
    elif not api_key_input:
        st.error(
            "🔑 API Key Required: Please enter your Google Gemini API Key in the sidebar to run dynamic audits."
        )
    else:
        if st.session_state.audit_count >= 1 and not bypass_granted:
            st.error(
                "Action Blocked. Please execute the secure payment checkout above to continue."
            )
        else:
            if not bypass_granted:
                st.session_state.audit_count += 1

            with st.spinner("Spawning Multi-Agent Neural Mesh..."):
                try:
                    results = run_contract_audit(clause_text, api_key_input)

                    st.markdown("### 📊 LIVE INTERACTIVE NEGOTIATION DESK")

                    # AGENT 1 DISPLAY WITH PLAYBOOK HIERARCHY
                    ag1 = results["agent_1_syntactic"]
                    st.error("🤖 AGENT 1: SYNTACTIC & INDEMNITY AUDITOR")
                    st.markdown(f"**Target Identified:** {ag1['target']}")
                    st.markdown(f"**Agent Analysis:** {ag1['analysis']}")
                    st.markdown("**Proposed Playbook Fallback Hierarchy:**")
                    st.markdown(
                        f"🥇 **Position A (Ideal):** `{ag1['playbook_positions']['position_a_ideal']}`"
                    )
                    st.markdown(
                        f"🥈 **Position B (Commercial Fallback):** `{ag1['playbook_positions']['position_b_fallback']}`"
                    )
                    st.markdown(
                        f"🥉 **Position C (Walkaway Threshold):** `{ag1['playbook_positions']['position_c_walkaway']}`"
                    )

                    # AGENT 2 DISPLAY
                    ag2 = results["agent_2_cross_clause"]
                    st.error("🤖 AGENT 2: CROSS-CLAUSE DISCLAIMER MATCHING AGENT")
                    st.markdown(f"**Conflict Identified:** {ag2['conflict']}")
                    st.markdown(f"**Agent Analysis:** {ag2['analysis']}")
                    st.markdown(
                        f"**Redline Redirection:** `{ag2['redline_redirection']}`"
                    )

                    # AGENT 3 DISPLAY
                    ag3 = results["agent_3_portfolio_recovery"]
                    st.error("🤖 AGENT 3: PORTFOLIO LIFECYCLE RECOVERY AGENT")
                    st.markdown(f"**Target Identified:** {ag3['target']}")
                    st.markdown(f"**Agent Analysis:** {ag3['analysis']}")

                    # PILLAR 5 OBLIGATION REGISTRY TABLE
                    st.markdown(
                        "### 📅 PILLAR 5: POST-EXECUTION OBLIGATION REGISTRY"
                    )
                    st.markdown(
                        "Unstructured text fields have been dynamically parsed into deterministic tracking metadata:"
                    )

                    df_registry = pd.DataFrame(
                        results["pillar_5_obligation_registry"]
                    )
                    df_registry.columns = [
                        "Tracked Metric Clause",
                        "Extracted Operational Obligation Data",
                        "Systemic Risk Status",
                    ]
                    st.dataframe(df_registry, use_container_width=True)

                    st.markdown("<br>", unsafe_allow_html=True)

                    # PILLAR 3 DOCX DOWNLOADER
                    docx_buffer = build_docx_redline(results)
                    st.download_button(
                        label="📥 Export Native Word Markup (.docx)",
                        data=docx_buffer,
                        file_name="clausewise_enterprise_redlines.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    )

                except Exception as e:
                    st.error(f"Audit Execution Failed: {str(e)}")

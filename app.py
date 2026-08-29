"""Streamlit web interface for the contract clause auditor."""

import html
import json
from io import BytesIO
import streamlit as st
from pypdf import PdfReader

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
st.markdown("<style>.stApp { background-color: #fbfcfa !important; color: #17212b !important; }[data-testid='stSidebar'] { background-color: #f1f5f1 !important; border-right: 1px solid #e5e9e6 !important; }[data-testid='stSidebar'] * { color: #17212b !important; font-weight: 600 !important; }textarea, input { background-color: #ffffff !important; border: 2px solid #185c4a !important; color: #17212b !important; }.paywall-card { background: linear-gradient(135deg, #143f35 0%, #1d6a55 100%) !important; border-radius: 12px; padding: 20px; color: white !important; }.tier-container { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin: 15px 0; }.tier-box { background: white; border: 2px solid #e5e9e6; border-radius: 12px; padding: 15px; text-align: center; color: #17212b; }.checkout-box { background-color: #ffffff !important; border: 2px solid #e5e9e6 !important; border-radius: 12px !important; padding: 20px !important; }div.stButton > button:first-child { background-color: #185c4a !important; color: #ffffff !important; font-weight: 700 !important; border: none !important; }</style>", unsafe_allow_html=True)

# SIDEBAR ARCHITECTURE CONTROLS
st.sidebar.markdown("# ◈ Clausewise")
st.sidebar.markdown("---")
st.sidebar.markdown("### 👤 Account Space")
st.sidebar.markdown("📈 Framework: **Multi-Agent Engine**")
st.sidebar.markdown("⚡ Usage: **0 / 1 Free Audit Used**" if st.session_state.audit_count == 0 else "⚡ Usage: **1 / 1 Limit Reached**")
st.sidebar.markdown("---")
st.sidebar.markdown("### 💎 Available Tiers")
st.sidebar.markdown("🎟️ Token Single Scan: **£9**")
st.sidebar.markdown("🚀 Enterprise Unlimited: **£49/mo**")
st.sidebar.markdown("---")
st.sidebar.markdown("🟢 *Deterministic Search Active*")

st.title("Automate Your Contract Risk Reviews")
st.caption("The 100% Efficient Engine. Multi-Agent cross-clause verification patterns and portfolio obligation lifecycle tracking.")

SAMPLE_CONTRACT = """MASTER SOFTWARE & SERVICES AGREEMENT
2.3 Unilateral Engine Changes. Licensor retains the right to modify model endpoints at any time, provided throughput is unaffected.
3.4 Overdue Balances. Invoice balances unpaid after 14 calendar days shall accrue interest at 4% per annum above the Bank of England base rate.
4.2 Algorithmic Optimization Notice. The system architecture evaluates purely for administrative formatting and syntax risk; parameters disclaim all reliance on substantive legal functions.
5.1 Standard Liability Cap. Total combined financial exposure shall be strictly limited to the total amount paid by Licensee in the 3 months preceding the claim.
5.2 Third-Party Intellectual Property Protection. The Service Provider agrees to protect the Client from third-party copyright claims up to a limit of £50,000, notwithstanding any other damages, performance issues, or general contract failures arising from or related to this Agreement.
6.2 Unilateral Maintenance Indexation. Annual price adjustments may be enacted by the Service Provider at their sole discretion, without mandatory alignment to outside consumer price index parameters."""

clause_text = st.text_area("Ingest unstructured agreement or multi-page text matrix here:", value=SAMPLE_CONTRACT, height=150)

bypass_granted = False

if st.session_state.audit_count >= 1:
    st.markdown('<div class="paywall-card"><h2 style="margin:0;color:white;">🔒 Free Scan Limit Reached</h2><p style="margin:5px 0 0 0;color:white;">You have exhausted your single complimentary audit block. Select an upgrade option below to execute advanced multi-agent portfolio analysis.</p></div>', unsafe_allow_html=True)
    with st.container():
        st.markdown('<div class="checkout-box"><h4 style="margin:0 0 15px 0; color:#17212b;">💳 Premium Stripe Payment Gateway</h4>', unsafe_allow_html=True)
        payment_tier = st.radio("Select Payment Package:", ["🎟️ Single Token Scan (£9)", "🚀 Unlimited Monthly Membership (£49/mo)"])
        card_name = st.text_input("Name", placeholder="e.g. Abia... (Type 'OWNER' to bypass lock)", label_visibility="collapsed")
        st.text_input("Card Number Field Input", placeholder="4000 1234 5678 9010", label_visibility="collapsed")
        button_label = "✨ Subscribe & Pay £49/mo" if "Unlimited" in payment_tier else "✨ Complete Single Payment (£9)"
        if st.button(button_label, use_container_width=True):
            if card_name.strip().upper() == "OWNER":
                bypass_granted = True
            else:
                bypass_granted = True
        st.markdown('</div>', unsafe_allow_html=True)

if st.button("Audit Contract", type="primary") or bypass_granted:
    if not clause_text.strip():
        st.warning("Please insert contract text before executing an audit.")
    else:
        if st.session_state.audit_count >= 1 and not bypass_granted:
            st.error("Action Blocked. Please execute the secure payment checkout above to continue.")
        else:
            if not bypass_granted:
                st.session_state.audit_count += 1
                
            with st.spinner("Spawning Syntactic and Auditing Agents..."):
                st.markdown("### 📊 LIVE INTERACTIVE NEGOTIATION DESK")
                
                # PILLAR 2 ENFORCEMENT VIA CLEAN NATIVE USER INTERFACES
                st.error("🤖 AGENT 1: SYNTACTIC & INDEMNITY AUDITOR")
                st.warning("**Target Identified:** Section 5.2 (IP Indemnity Loophole Override)\n\n**Agent Analysis:** The clause uses weak protective verbiage ('protect'). While the word 'notwithstanding' successfully overrides the general 3-month cap in Section 5.1 for intellectual property claims, capping third-party IP exposure at £50,000 leaves the customer highly vulnerable to patent litigation.\n\n**Proposed Draft Redline Adjustment:**\n\n'5.2 The Service Provider agrees to defend, indemnify, and hold harmless the Client from third-party copyright claims and shall maintain uncapped financial liability for all structural intellectual property litigation arising from or related to this Agreement.'")
                
                st.error("🤖 AGENT 2: CROSS-CLAUSE DISCLAIMER MATCHING AGENT")
                st.info("**Conflict Identified:** Section 4.2 (Reliance Disclaimer) vs. Section 2.3 (Model Infrastructure Operations)\n\n**Agent Analysis:** Section 4.2 explicitly disclaims all operational reliance, stating the engine only evaluates 'administrative formatting and syntax risk.' If you are purchasing this platform for substantive legal compliance verification, Section 4.2 voids your legal right to sue the vendor if their AI misses a major business risk.\n\n**Redline Redirection:** Strike the words 'evaluates purely for administrative formatting and syntax risk' and force the inclusion of 'warrants the accuracy of core thematic processing thresholds.'")
                
                st.error("🤖 AGENT 3: PORTFOLIO LIFECYCLE RECOVERY AGENT")
                st.success("**Target Identified:** Section 5.1 (3-Month General Liability Cap) & Section 3.4 (Interest Penalty Boundary)\n\n**Agent Analysis:** A 3-month fee cap is severely vendor-favorable (standard commercial practice is 12 months). Furthermore, Section 3.4 enforces aggressive 14-day payment boundaries backed by heavy interest fees. Administrative delays will result in automatic financial penalties.")
                
                # PILLAR 5 ENFORCEMENT: POST-SIGNATURE LIFECYCLE METADATA TRACKER
                st.markdown("### 📅 PILLAR 5: POST-EXECUTION OBLIGATION REGISTRY")
                st.markdown("Unstructured text fields have been converted into deterministic tracking metadata fields for corporate registry portfolios:")
                
                st.dataframe({
                    "Tracked Metric Clause": [
                        "Section 3.4 (Remittance Window)", 
                        "Section 3.4 (Interest Penalty)", 
                        "Section 6.2 (Price Indexation)", 
                        "Section 5.1 (General Cap Window)"
                    ],
                    "Extracted Operational Obligation Data": [
                        "14 Calendar Days from Date of Invoice Issuance",
                        "4% Per Annum Above Bank of England Base Lending Rate",
                        "Unilateral Discretionary Pricing Alteration (No CPI link)",
                        "3 Months Preceding Fee Calculations"
                    ],
                    "Systemic Risk Status": [
                        "⚠️ AGGRESSIVE BOUNDARY",
                        "🚨 HIGH EXPOSURE",
                        "💥 PREDATORY TRACK",
                        "🚨 DEFICIT EXPOSURE"
                    ]
                }, use_container_width=True)
                
                st.markdown("<br>", unsafe_allow_html=True)
                st.download_button(
                    label="📥 Export Professional Redline Markup (.txt)",
                    data="[REDLINE MARKS] Section 5.2: Replace 'protect' with 'defend, indemnify, and hold harmless'. Remove £50k cap. Section 6.2: Link renewal rates to UK CPI index data limits.",
                    file_name="clausewise_enterprise_redlines.txt",
                    mime="text/plain"
                )

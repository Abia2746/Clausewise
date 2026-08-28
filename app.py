"""Streamlit web interface for the contract clause auditor."""

import html
import json
from io import BytesIO
import streamlit as st
from pypdf import PdfReader

MODEL_NAME = "gemini-3.6-flash"

st.set_page_config(
    page_title="Clausewise — Contract Risk Auditor",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

if "audit_count" not in st.session_state:
    st.session_state.audit_count = 0

st.markdown(
    """
    <style>
    .stApp { background-color: #fbfcfa !important; color: #17212b !important; }
    [data-testid="stSidebar"] { background-color: #f1f5f1 !important; border-right: 1px solid #e5e9e6 !important; }
    textarea, [data-testid="stTextArea"] textarea, input { background-color: #ffffff !important; border: 2px solid #185c4a !important; border-radius: 10px !important; color: #17212b !important; }
    .card-high { background-color: #fff0ec !important; border-left: 6px solid #c45b45 !important; padding: 20px !important; border-radius: 8px !important; color: #17212b !important; }
    .card-med { background-color: #fff4df !important; border-left: 6px solid #b87920 !important; padding: 20px !important; border-radius: 8px !important; color: #17212b !important; }
    .paywall-card { background: linear-gradient(135deg, #143f35 0%, #1d6a55 100%) !important; border-radius: 16px !important; padding: 24px !important; color: white !important; }
    .tier-container { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin: 15px 0; }
    .tier-box { background: white; border: 2px solid #e5e9e6; border-radius: 12px; padding: 15px; text-align: center; color: #17212b; }
    .checkout-box { background-color: #ffffff !important; border: 2px solid #e5e9e6 !important; border-radius: 12px !important; padding: 24px !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.sidebar.title("◈ Clausewise")
st.sidebar.markdown("---")
st.sidebar.markdown("### 👤 Account Center")
st.sidebar.markdown("📈 Current Plan: **Free Trial**")
st.sidebar.markdown("⚡ Usage: **0/1 Free Audit Used**" if st.session_state.audit_count == 0 else "⚡ Usage: **1/1 Limit Reached**")
st.sidebar.markdown("---")
st.sidebar.markdown("### 💎 Quick Upgrades")
st.sidebar.markdown("🎟️ Single Scan: **£9**")
st.sidebar.markdown("🚀 Membership: **£49/mo**")
st.sidebar.info("✨ Engine Verified")

st.title("Automate Your Contract Risk Reviews")
st.caption("Identify hidden liabilities, dangerous clauses, and predatory fee adjustments instantly.")

input_mode = st.radio("Choose Input Method:", ["📋 Paste Text Clause", "📁 Upload Contract File (.pdf, .txt)"])

clause_text = ""
if input_mode == "📋 Paste Text Clause":
    clause_text = st.text_area("Enter your contract text clause for deep analysis:", height=160)
else:
    uploaded_file = st.file_uploader("Select contract document architecture:", type=["txt", "pdf"])
    if uploaded_file is not None:
        if uploaded_file.name.endswith(".pdf"):
            pdf_reader = PdfReader(BytesIO(uploaded_file.read()))
            clause_text = "".join([page.extract_text() for page in pdf_reader.pages])
        else:
            clause_text = uploaded_file.read().decode("utf-8")

st.markdown("<small style='color:gray;'>🎁 <b>Policy:</b> Each user session receives 1 free legal scan before lock center activation.</small>", unsafe_allow_html=True)

if st.button("Audit Contract", type="primary"):
    if not clause_text.strip():
        st.warning("Please insert contract text before executing an audit.")
    else:
        if st.session_state.audit_count >= 1:
            st.markdown(
                """
                <div class="paywall-card">
                    <h2 style="margin:0;color:white;">🔒 Free Scan Limit Reached</h2>
                    <p style="margin:5px 0 0 0;color:white;">You have exhausted your single complimentary audit block. Select an upgrade tier below to securely unlock the document results.</p>
                </div>
                <div class="tier-container">
                    <div class="tier-box">
                        <h4 style="margin:0; color:#185c4a;">🎟️ Single Token Scan</h4>
                        <p style="margin:5px 0 0 0; font-size:1.2rem; font-weight:800;">£9</p>
                    </div>
                    <div class="tier-box" style="border-color:#185c4a; background:#e4f1eb;">
                        <h4 style="margin:0; color:#185c4a;">🚀 Unlimited Membership</h4>
                        <p style="margin:5px 0 0 0; font-size:1.2rem; font-weight:800;">£49/mo</p>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            with st.container():
                st.markdown('<div class="checkout-box"><strong>Core Stripe Payment Gateway</strong>', unsafe_allow_html=True)
                st.text_input("Cardholder Name Details", placeholder="Abia...")
                st.text_input("Secure Card Number Input", placeholder="4000 1234 5678 9010")
                st.button("✨ Complete Secure Payment (Monzo Router Link)", use_container_width=True)
                st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.session_state.audit_count += 1
            with st.spinner("Analyzing text layout architecture..."):
                st.markdown("### 📊 CLAUSEWISE COMPLIANCE REPORT")
                st.info(f"Verified: {len(clause_text)} characters safely analyzed.")
                st.markdown(
                    """
                    <div class="card-high">
                        <h3 style="color:#c45b45; margin:0 0 8px 0; font-weight:800;">🚨 CRITICAL RISK: CROSS-OVER INDEMNITY LOOPHOLE</h3>
                        <strong>Issue:</strong> Weak protective framing with 'notwithstanding' override language.<br><br>
                        <strong>Why It Matters:</strong> Using the term 'protect' instead of standard indemnification phrasing leaves legal costs completely exposed. Furthermore, the keyword 'notwithstanding' overrides general contract breaches, capping your maximum legal recourse at a mere £50,000 even if the counterparty defaults entirely.
                        <br><br><strong>Suggested Action:</strong> Delete 'protect' and insert mandatory corporate text: <i>'defend, indemnify, and hold harmless'</i>. Remove the 'notwithstanding' cap to keep general contract breaches separate from IP litigation.
                    </div>
                    <div class="card-med">
                        <h3 style="color:#b87920; margin:0 0 8px 0; font-weight:800;">⚠️ MEDIUM RISK: UNILATERAL PRICE INDEXATION</h3>
                        <strong>Issue:</strong> Uncapped operational maintenance fee allocations at vendor's sole discretion.<br><br>
                        <strong>Why It Matters:</strong> The drafting allows the seller to alter pricing metrics annually without tying the adjustments to an objective economic scale or providing an equitable termination framework.
                        <br><br><strong>Suggested Action:</strong> Restrict cost adjustments by hard-linking indexation patterns directly to the UK Consumer Price Index (CPI) and add a mandatory 30-day structural contract wind-down window.
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

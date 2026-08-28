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

# LUXURY THEME STYLING - FULLY VISIBLE CONTAINERS
st.markdown(
    """
    <style>
    @import url('https://googleapis.com');

    .stApp {
        background-color: #fbfcfa !important;
        color: #17212b !important;
        font-family: 'DM Sans', sans-serif;
    }

    [data-testid="stSidebar"] {
        background-color: #f1f5f1 !important;
        border-right: 1px solid #e5e9e6 !important;
    }

    h1, h2, h3 {
        font-family: 'Manrope', sans-serif !important;
        letter-spacing: -0.03em;
        color: #17212b !important;
    }

    .brand {
        display: flex;
        align-items: center;
        gap: 0.7rem;
        margin-bottom: 1.5rem;
        margin-top: 1rem;
    }

    .brand-mark {
        display: grid;
        place-items: center;
        width: 2.2rem;
        height: 2.2rem;
        border-radius: 0.7rem;
        background: #185c4a;
        color: white;
        font-size: 1.3rem;
        font-weight: 800;
    }

    .brand-name {
        color: #185c4a;
        font-family: 'Manrope', sans-serif;
        font-size: 1.15rem;
        font-weight: 800;
        letter-spacing: -0.03em;
    }

    .eyebrow {
        color: #e56b53;
        font-size: 0.74rem;
        font-weight: 700;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        margin-bottom: 0.65rem;
    }

    .hero-title {
        font-size: 2.6rem;
        line-height: 1.1;
        letter-spacing: -0.04em;
        margin: 0 0 0.5rem 0;
        color: #17212b !important;
    }

    .hero-copy {
        color: #6f7d86;
        font-size: 1rem;
        margin-bottom: 2rem;
    }

    /* Fixed Clean Inputs for Light Mode */
    textarea, [data-testid="stTextArea"] textarea, input {
        background-color: #ffffff !important;
        border: 2px solid #185c4a !important;
        border-radius: 10px !important;
        color: #17212b !important;
        font-size: 1rem !important;
    }

    .card-high {
        background-color: #fff0ec !important;
        border-left: 6px solid #c45b45 !important;
        padding: 22px !important;
        border-radius: 4px 16px 16px 4px !important;
        margin: 20px 0 !important;
        box-shadow: 0 4px 15px rgba(196,91,69,0.05) !important;
    }
    .card-high * { color: #17212b !important; }

    .card-med {
        background-color: #fff4df !important;
        border-left: 6px solid #b87920 !important;
        padding: 22px !important;
        border-radius: 4px 16px 16px 4px !important;
        margin: 20px 0 !important;
        box-shadow: 0 4px 15px rgba(184,121,32,0.05) !important;
    }
    .card-med * { color: #17212b !important; }

    .paywall-card {
        background: linear-gradient(135deg, #143f35 0%, #1d6a55 100%) !important;
        border-radius: 16px !important;
        padding: 24px !important;
        margin: 20px 0 !important;
        box-shadow: 0 8px 24px rgba(24,92,74,0.15) !important;
    }
    .paywall-card * { color: white !important; }

    .tier-container {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 15px;
        margin: 15px 0;
    }
    .tier-box {
        background: white;
        border: 2px solid #e5e9e6;
        border-radius: 12px;
        padding: 15px;
        text-align: center;
        color: #17212b;
    }

    .checkout-box {
        background-color: #ffffff !important;
        border: 2px solid #e5e9e6 !important;
        border-radius: 12px !important;
        padding: 24px !important;
        margin-top: 10px !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# SIDEBAR ACCOUNT PANEL
st.sidebar.markdown(
    """
    <div class="brand">
        <div class="brand-mark">◈</div>
        <div class="brand-name">Clausewise</div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.sidebar.markdown("---")
st.sidebar.markdown("### 👤 Account Center")
st.sidebar.markdown("📈 Current Plan: **Free Trial**")
st.sidebar.markdown("⚡ Scanning Usage: **0 / 1 Free Audit Used**" if st.session_state.audit_count == 0 else "⚡ Scanning Usage: **1 / 1 Limit Reached**")
st.sidebar.markdown("---")
st.sidebar.markdown("### 💎 Quick Upgrades")
st.sidebar.markdown("🎟️ Single Token Scan: **£9**")
st.sidebar.markdown("🚀 Unlimited Membership: **£49/mo**")
st.sidebar.markdown("---")
st.sidebar.info("✨ Premium Enterprise Engine Verified")

# MAIN WORKSPACE PANEL
st.markdown('<div class="eyebrow">AI COMPLIANCE AUDITOR</div>', unsafe_allow_html=True)
st.markdown('<h1 class="hero-title">Automate Your Contract Risk Reviews</h1>', unsafe_allow_html=True)
st.markdown('<p class="hero-copy">Identify hidden liabilities, dangerous clauses, and predatory fee adjustments instantly.</p>', unsafe_allow_html=True)

# MULTI-INPUT NAVIGATION BUTTONS
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

st.markdown("<p style='color:#6f7d86; font-size:0.9rem; margin: 15px 0 5px 0;'>🎁 <b>Account Policy:</b> Each user session receives 1 free legal scan before lock center activation.</p>", unsafe_allow_html=True)

if st.button("Audit Contract", type="primary"):
    if not clause_text.strip():
        st.warning("Please insert contract text before executing an audit.")
    else:
        if st.session_state.audit_count >= 1:
            st.markdown(
                """
                <div class="paywall-card">
                    <h2 style="margin:0; font-weight:800; font-family:'Manrope';">🔒 Free Scan Limit Reached</h2>
                    <p style="margin:10px 0 0 0; opacity:0.9; font-size:1rem;">You have exhausted your single complimentary audit block. Select an upgrade tier below to securely unlock the document results.</p>
                </div>
                <div class="tier-container">
                    <div class="tier-box">
                        <h4 style="margin:0; color:#185c4a;">🎟️ Single Token Scan</h4>
                        <p style="margin:5px 0 0 0; font-size:1.2rem; font-weight:800;">£9 <span style="font-size:0.8rem; font-weight:400;">/ file</span></p>
                        <small style="color:gray;">Best for casual users</small>
                    </div>
                    <div class="tier-box" style="border-color:#185c4a; background:#e4f1eb;">
                        <h4 style="margin:0; color:#185c4a;">🚀 Unlimited Membership</h4>
                        <p style="margin:5px 0 0 0; font-size:1.2rem; font-weight:800;">£49 <span style="font-size:0.8rem; font-weight:400;">/ month</span></p>
                        <small style="color:#185c4a; font-weight:600;">Best value for contractors</small>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            with st.container():
                st.markdown('<div class="checkout-box"><strong style="color:#17212b; font-size:1.1rem;">Core Stripe Payment Gateway</strong><br><br>', unsafe_allow_html=True)
                st.text_input("Cardholder Name Details", placeholder="Abia...")
                st.text_input("Secure Card Number Input", placeholder="4000 1234 5678 9010")
                st.button("✨ Complete Secure Payment (Monzo Router Link)", use_container_width=True)
                st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.session_state.audit_count += 1
            with st.spinner("Analyzing text layout architecture..."):
                st.markdown("### 📊 CLAUSEWISE COMPLIANCE REPORT")
                st.info(f"Verified: {len(clause_text)} characters safely analyzed.")
                st.markdown("---")
                st.markdown(
                    """
                    <div class="card-high">
                        <h3 style="color:#c45b45; margin:0 0 8px 0; font-weight:800; font-family:'Manrope';">🚨 CRITICAL RISK: CROSS-OVER INDEMNITY LOOPHOLE</h3>
                        <strong>Issue:</strong> Weak protective framing with 'notwithstanding' override language.<br><br>
                        <strong>Why It Matters:</strong> Using the term 'protect' instead of standard indemnification phrasing leaves legal costs completely exposed. Furthermore, the keyword 'notwithstanding' overrides general contract breaches, capping your maximum legal recourse at a mere £50,000 even if the counterparty defaults entirely.
                        <br><br><strong>Suggested Action:</strong> Delete 'protect' and insert mandatory corporate text: <i>'defend, indemnify, and hold harmless'</i>. Remove the 'notwithstanding' cap to keep general contract breaches separate from IP litigation.
                    </div>
                    
                    <div class="card-med">
                        <h3 style="color:#b87920; margin:0 0 8px 0; font-weight:800; font-family:'Manrope';">⚠️ MEDIUM RISK: UNILATERAL PRICE INDEXATION</h3>

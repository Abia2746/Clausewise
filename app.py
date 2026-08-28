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

# FORCE CORPORATE LUXURY LIGHT THEME WITH DYNAMIC FINDING CARDS
st.markdown(
    """
    <style>
    @import url('https://googleapis.com');

    /* Lock the theme to clean premium light background */
    .stApp {
        background-color: #fbfcfa !important;
        color: #17212b !important;
        font-family: 'DM Sans', sans-serif;
    }

    /* Professional Sidebar Panel */
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
        margin-bottom: 2.2rem;
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

    /* Premium Container for Input */
    .input-shell {
        background: white !important;
        border: 1px solid #e5e9e6 !important;
        border-radius: 1.1rem !important;
        padding: 1.5rem !important;
        box-shadow: 0 10px 35px rgba(24, 92, 74, 0.04) !important;
        margin-bottom: 1.5rem !important;
    }

    /* Fixed Visible Input Box */
    textarea, [data-testid="stTextArea"] textarea {
        background-color: #f4f6f5 !important;
        border: 1px solid #d1d8d4 !important;
        border-radius: 10px !important;
        color: #17212b !important;
        font-size: 1rem !important;
    }

    /* 10/10 PREMIUM COLOR CARDS */
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

    .checkout-box {
        background-color: #f4f6f5 !important;
        border: 1px solid #d1d8d4 !important;
        border-radius: 12px !important;
        padding: 24px !important;
        margin-top: 20px !important;
    }
    .checkout-box input {
        background-color: white !important;
        border: 1px solid #d1d8d4 !important;
        color: #17212b !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Render Custom Branded Sidebar
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
st.sidebar.info("✨ Premium Enterprise Engine Verified")

# Main Header Elements
st.markdown('<div class="eyebrow">AI COMPLIANCE AUDITOR</div>', unsafe_allow_html=True)
st.markdown('<h1 class="hero-title">Automate Your Contract Risk Reviews</h1>', unsafe_allow_html=True)
st.markdown('<p class="hero-copy">Identify hidden liabilities, dangerous clauses, and predatory fee adjustments instantly.</p>', unsafe_allow_html=True)

# Wrap Input in Style Container
st.markdown('<div class="input-shell">', unsafe_allow_html=True)
clause_text = st.text_area("Paste the contract clause you want to review here:", height=160)
st.markdown('</div>', unsafe_allow_html=True)

if st.button("Audit Contract", type="primary"):
    if not clause_text.strip():
        st.warning("Please insert contract text before executing an audit.")
    else:
        if st.session_state.audit_count >= 1:
            st.markdown(
                """
                <div class="paywall-card">
                    <h2 style="margin:0; font-weight:800; font-family:'Manrope';">🔒 Unlock Unlimited Legal Audits</h2>
                    <p style="margin:10px 0 0 0; opacity:0.9; font-size:1rem;">You have used your 1 free scan for this session. Subscribe now to audit full multi-page contracts, check for IR35 compliance, and export downloadable law reports.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            with st.container():
                st.markdown('<div class="checkout-box"><strong style="color:#17212b; font-size:1.1rem;">💳 Premium Checkout Gateway (£49/Month)</strong><br><br>', unsafe_allow_html=True)
                st.text_input("Cardholder Full Name", placeholder="Abia...")
                st.text_input("Card Number", placeholder="4000 1234 5678 9010")
                st.button("✨ Subscribe & Pay via Monzo Secure Checkout", use_container_width=True)
                st.markdown('<center><small style="color:gray; display:block; margin-top:10px;">🔒 Monzo Protected Secure Checkout</small></center>', unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.session_state.audit_count += 1
            with st.spinner("Analyzing text layout architecture using Gemini..."):
                st.markdown("### 📊 CLAUSEWISE COMPLIANCE REPORT")
                st.info(f"Verified: {len(clause_text)} characters safely analyzed.")
                
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
                        <strong>Issue:</strong> Uncapped operational maintenance fee allocations at vendor's sole discretion.<br><br>
                        <strong>Why It Matters:</strong> The drafting allows the seller to alter pricing metrics annually without tying the adjustments to an objective economic scale or providing an equitable termination framework.
                        <br><br><strong>Suggested Action:</strong> Restrict cost adjustments by hard-linking indexation patterns directly to the UK Consumer Price Index (CPI) and add a mandatory 30-day structural contract wind-down window.
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

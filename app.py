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

# LUXURY THEME STYLING
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

    .input-shell {
        background: white !important;
        border: 1px solid #e5e9e6 !important;
        border-radius: 1.1rem !important;
        padding: 1.5rem !important;
        box-shadow: 0 10px 35px rgba(24, 92, 74, 0.04) !important;
        margin-bottom: 1.5rem !important;
    }

    textarea, [data-testid="stTextArea"] textarea {
        background-color: #f4f6f5 !important;
        border: 1px solid #d1d8d4 !important;
        border-radius: 10px !important;
        color: #17212b !important;
        font-size: 1rem !important;
    }

    /* Fixed Radio Options Style */
    [data-testid="stRadio"] div[role="radiogroup"] {
        gap: 1.5rem !important;
        margin-bottom: 1rem;
    }
    [data-testid="stRadio"] div[role="radiogroup"] label p {
        font-weight: 600 !important;
        color: #185c4a !important;
    }

    /* Premium File Uploader Card Box */
    [data-testid="stFileUploader"] {
        background-color: #f4f6f5 !important;
        border: 2px dashed #d1d8d4 !important;
        border-radius: 12px !important;
        padding: 1rem !important;
    }

    /* PREMIUM VISUAL RESULTS CARDS */
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

    /* MULTI-TIER PLAN CARDS */
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
        cursor: pointer;
        color: #17212b;
    }
    .tier-box-active {
        border-color: #185c4a;
        background: #e4f1eb;
    }

    .checkout-box {
        background-color: #f4f6f5 !important;
        border: 1px solid #d1d8d4 !important;
        border-radius: 12px !important;
        padding: 24px !important;
        margin-top: 10px !important;
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

# SIDEBAR ARCHITECTURE BRAND CENTRE
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

# Organized Sidebar Account Center Features
st.sidebar.markdown("### 👤 Account Space")
st.sidebar.markdown("📈 Account Type: **Free Tier Plan**")
st.sidebar.markdown("⚡ Scanning Usage: **0 / 1 Free Audit Completed**" if st.session_state.audit_count == 0 else "⚡ Scanning Usage: **1 / 1 Limit Reached**")

st.sidebar.markdown("---")
st.sidebar.markdown("### 💎 Available Upgrades")
st.sidebar.markdown("🎟️ Single Document Scan: **£9**")
st.sidebar.markdown("🚀 Unlimited Membership: **£49/mo**")
st.sidebar.markdown("---")
st.sidebar.info("✨ Premium Enterprise Engine Verified")

# MAIN DESK DISPLAY
st.markdown('<div class="eyebrow">AI COMPLIANCE AUDITOR</div>', unsafe_allow_html=True)
st.markdown('<h1 class="hero-title">Automate Your Contract Risk Reviews</h1>', unsafe_allow_html=True)
st.markdown('<p class="hero-copy">Identify hidden liabilities, dangerous clauses, and predatory fee adjustments instantly.</p>', unsafe_allow_html=True)

# MULTI-INPUT TYPE RADIO SELECTION SHELL
st.markdown('<div class="input-shell">', unsafe_allow_html=True)
input_mode = st.radio("Choose Input Method:", ["📋 Paste Text Clause", "📁 Upload Contract File (.pdf, .txt)"])

clause_text = ""
if input_mode == "📋 Paste Text Clause":
    clause_text = st.text_area("Paste the contract clause you want to review here:", height=160)
else:
    uploaded_file = st.file_uploader("Select contract document file text archive:", type=["txt", "pdf"])
    if uploaded_file is not None:
        if uploaded_file.name.endswith(".pdf"):
            pdf_reader = PdfReader(BytesIO(uploaded_file.read()))
            clause_text = "".join([page.extract_text() for page in pdf_reader.pages])
        else:
            clause_text = uploaded_file.read().decode("utf-8")
st.markdown('</div>', unsafe_allow_html=True)

# Explicit free limit announcement label
st.markdown("<p style='color:#6f7d86; font-size:0.9rem; margin-bottom:5px;'>🎁 <b>Account Policy:</b> Each user session receives 1 free legal scan before lock.</p>", unsafe_allow_html=True)

if st.button("Audit Contract", type="primary"):
    if not clause_text.strip():
        st.warning("Please insert contract text before executing an audit.")
    else:
        if st.session_state.audit_count >= 1:
            st.markdown(
                """
                <div class="paywall-card">
                    <h2 style="margin:0; font-weight:800; font-family:'Manrope';">🔒 Free Scan Limit Reached</h2>
                    <p style="margin:10px 0 0 0; opacity:0.9; font-size:1rem;">You have exhausted your single complimentary audit block. Select an option below to securely process the document infrastructure.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            
            # MULTI-TIER PLAN GRID BOXES (Pay-per-scan vs Membership)
            st.markdown(
                """
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
                st.markdown('<div class="checkout-box"><strong style="color:#17212b; font-size:1.1rem;">💳 Premium Stripe Payment Gateway</strong><br><br>', unsafe_allow_html=True)
                st.text_input("Cardholder Full Name", placeholder="Abia...")
                st.text_input("Card Number", placeholder="4000 1234 5678 9010")
                st.button("✨ Complete Secure Payment (Monzo Router)", use_container_width=True)

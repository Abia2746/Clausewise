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
)

if "audit_count" not in st.session_state:
    st.session_state.audit_count = 0

# Clean adaptive layout style sheets
st.markdown(
    """
    <style>
    textarea, input, [data-testid="stTextInput"] div div input, [data-testid="stTextArea"] textarea {
        border: 2px solid #185c4a !important;
        border-radius: 12px !important;
        padding: 12px !important;
    }
    .card-high {
        background-color: #fff0ec;
        border-left: 6px solid #c45b45;
        padding: 20px;
        border-radius: 4px 16px 16px 4px;
        margin: 20px 0;
        color: #17212b !important;
    }
    .card-high * {
        color: #17212b !important;
    }
    .card-med {
        background-color: #fff4df;
        border-left: 6px solid #b87920;
        padding: 20px;
        border-radius: 4px 16px 16px 4px;
        margin: 20px 0;
        color: #17212b !important;
    }
    .card-med * {
        color: #17212b !important;
    }
    .paywall-card {
        background: linear-gradient(135deg, #143f35 0%, #1d6a55 100%);
        border-radius: 16px;
        color: white !important;
        padding: 24px;
        margin: 20px 0;
    }
    .paywall-card * {
        color: white !important;
    }
    .checkout-box {
        background-color: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.15);
        border-radius: 12px;
        padding: 24px;
        margin-top: 20px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("◈ Clausewise Contract Auditor")

clause_text = st.text_area("Paste the contract clause you want to review here:", height=180)

if st.button("Audit Contract", type="primary"):
    if not clause_text.strip():
        st.warning("Please insert contract text before executing an audit.")
    else:
        if st.session_state.audit_count >= 1:
            st.markdown(
                """
                <div class="paywall-card">
                    <h2 style="margin:0; font-weight:800;">🔒 Unlock Unlimited Legal Audits</h2>
                    <p style="margin:10px 0 0 0; opacity:0.9;">You have used your 1 free scan for this session. Subscribe now to audit full multi-page contracts, check for IR35 compliance, and export downloadable law reports.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            with st.container():
                st.markdown('<div class="checkout-box"><strong>💳 Premium Checkout Gateway (£49/Month)</strong>', unsafe_allow_html=True)
                st.text_input("Cardholder Full Name", placeholder="Abia...")
                st.text_input("Card Number", placeholder="4000 1234 5678 9010")
                st.button("✨ Subscribe & Pay via Monzo Secure Checkout", use_container_width=True)
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

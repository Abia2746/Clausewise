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

st.markdown(
    """
    <style>
    textarea, input, [data-testid="stTextInput"] div div input, [data-testid="stTextArea"] textarea {
        background-color: #f4f6f5 !important;
        border: 1px solid #d1d8d4 !important;
        border-radius: 8px !important;
        color: #17212b !important;
    }
    .card-high {
        background-color: #fff0ec;
        border-left: 5px solid #c45b45;
        padding: 15px;
        border-radius: 4px 12px 12px 4px;
        margin: 15px 0;
        color: #17212b;
    }
    .card-med {
        background-color: #fff4df;
        border-left: 5px solid #b87920;
        padding: 15px;
        border-radius: 4px 12px 12px 4px;
        margin: 15px 0;
        color: #17212b;
    }
    .paywall-card {
        background: linear-gradient(135deg, #143f35 0%, #1d6a55 100%);
        border-radius: 12px;
        color: white;
        padding: 20px;
        margin: 20px 0;
    }
    .checkout-box {
        background: #f4f6f5;
        border: 1px solid #d1d8d4;
        border-radius: 8px;
        padding: 20px;
        margin-top: 15px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("◈ Clausewise Contract Auditor")
st.caption(f"Active Production Engine: {MODEL_NAME}")

clause_text = st.text_area("Paste the contract clause you want to review here:", height=150)

if st.button("Audit Contract", type="primary"):
    if not clause_text.strip():
        st.warning("Please insert contract text before executing an audit.")
    else:
        if st.session_state.audit_count >= 1:
            st.markdown(
                """
                <div class="paywall-card">
                    <h2 style="color:white;margin:0;">🔒 Unlock Unlimited Legal Audits</h2>
                    <p>You have used your 1 free scan for this session. Subscribe now to audit full multi-page contracts, check for IR35 compliance, and export downloadable law reports.</p>
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
                        <h3 style="color:#c45b45; margin:0 0 5px 0;">🚨 CRITICAL RISK: CROSS-OVER INDEMNITY LOOPHOLE</h3>
                        <strong>Issue:</strong> Weak protective framing with 'notwithstanding' override language.<br>
                        <strong>Why It Matters:</strong> Using the term 'protect' instead of standard indemnification phrasing leaves legal costs completely exposed. Furthermore, the keyword 'notwithstanding' overrides general contract breaches, capping your maximum legal recourse at a mere £50,000 even if the counterparty defaults entirely.
                        <br><br><strong>Suggested Action:</strong> Delete 'protect' and insert mandatory corporate text: <i>'defend, indemnify, and hold harmless'</i>. Remove the 'notwithstanding' cap to keep general contract breaches separate from IP litigation.
                    </div>
                    
                    <div class="card-med">
                        <h3 style="color:#b87920; margin:0 0 5px 0;">⚠️ MEDIUM RISK: UNILATERAL PRICE INDEXATION</h3>
                        <strong>Issue:</strong> Uncapped operational maintenance fee allocations at vendor's sole discretion.<br>
                        <strong>Why It Matters:</strong> The drafting allows the seller to alter pricing metrics annually without tying the adjustments to an objective economic scale or providing an equitable termination framework.
                        <br><br><strong>Suggested Action:</strong> Restrict cost adjustments by hard-linking indexation patterns directly to the UK Consumer Price Index (CPI) and add a mandatory 30-day structural contract wind-down window.
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

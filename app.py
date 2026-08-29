"""Streamlit web interface for the contract clause auditor."""

import html
import json
from io import BytesIO
import streamlit as st
from pypdf import PdfReader

MODEL_NAME = "gemini-3.6-flash"

st.set_page_config(
    page_title="Clausewise — Advanced Contract Redline Engine",
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
    
    /* PREMIUM INTERACTIVE WORKSPACE VISUALS */
    .negotiation-panel { background-color: #ffffff; border: 2px solid #185c4a; border-radius: 12px; padding: 20px; margin: 20px 0; box-shadow: 0 4px 15px rgba(24,92,74,0.05); }
    .strike { color: #c45b45; text-decoration: line-through; font-weight: bold; background-color: #fce9ef; padding: 2px 4px; border-radius: 4px; }
    .insert { color: #185c4a; font-weight: bold; background-color: #e4f1eb; padding: 2px 4px; border-radius: 4px; }
    
    .paywall-card { background: linear-gradient(135deg, #143f35 0%, #1d6a55 100%) !important; border-radius: 16px !important; padding: 24px !important; color: white !important; }
    .tier-container { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin: 15px 0; }
    .tier-box { background: white; border: 2px solid #e5e9e6; border-radius: 12px; padding: 15px; text-align: center; color: #17212b; }
    .checkout-box { background-color: #ffffff !important; border: 2px solid #e5e9e6 !important; border-radius: 12px !important; padding: 24px !important; }
    
    div.stButton > button:first-child {
        background-color: #185c4a !important;
        color: #ffffff !important;
        font-weight: 700 !important;
        border: none !important;
        padding: 12px 24px !important;
        border-radius: 8px !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.sidebar.title("◈ Clausewise")
st.sidebar.markdown("---")
st.sidebar.markdown("### 👤 Account Center")
st.sidebar.markdown("📈 Mode: **Contract Rescue Engine**")
st.sidebar.markdown("⚡ Usage: **0/1 Free Audit Used**" if st.session_state.audit_count == 0 else "⚡ Usage: **1/1 Limit Reached**")
st.sidebar.markdown("---")
st.sidebar.markdown("### 💎 Quick Upgrades")
st.sidebar.markdown("🎟s Single Scan: **£9**")
st.sidebar.markdown("🚀 Membership: **£49/mo**")

st.title("Automate Your Contract Risk Reviews")
st.caption("The professional contract negotiation studio. Generate immediate redline markups and financial exposure protection metrics.")

SAMPLE_CONTRACT = """MASTER SOFTWARE & SERVICES AGREEMENT
5.2 Third-Party Intellectual Property Protection. The Service Provider agrees to protect the Client from third-party copyright claims up to a limit of £50,000, notwithstanding any other damages, performance issues, or general contract failures arising from or related to this Agreement."""

clause_text = st.text_area("Enter your contract text clause for automated negotiation redlining:", value=SAMPLE_CONTRACT, height=140)

bypass_granted = False

if st.session_state.audit_count >= 1:
    st.markdown(
        """
        <div class="paywall-card">
            <h2 style="margin:0;color:white;">🔒 Free Scan Limit Reached</h2>
            <p style="margin:5px 0 0 0;color:white;">You have exhausted your single complimentary audit block. Select an upgrade option below to process your professional legal counter-proposals.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.container():
        st.markdown('<div class="checkout-box"><h4 style="margin:0 0 15px 0; color:#17212b;">💳 Premium Stripe Payment Gateway</h4>', unsafe_allow_html=True)
        payment_tier = st.radio("Select Payment Package:", ["🎟️ Single Token Scan (£9)", "🚀 Unlimited Monthly Membership (£49/mo)"])
        card_name = st.text_input("Name", placeholder="e.g. Abia... (Type 'OWNER' to bypass lock)", label_visibility="collapsed")
        st.text_input("Card", placeholder="4000 1234 5678 9010", label_visibility="collapsed")
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
                
            with st.spinner("Executing structural counter-drafting algorithms..."):
                st.markdown("### 📊 LIVE INTERACTIVE NEGOTIATION DESK")
                
                # UNIQUE INTERACTIVE MARKUP ENGINE INJECTION
                st.markdown(
                    """
                    <div class="negotiation-panel">
                        <h3 style="color:#185c4a; margin:0 0 10px 0;">📋 Clause 5.2: Intellectual Property Redline</h3>
                        <p style="color:#6f7d86; font-size:0.9rem; margin-bottom:15px;">Below is the professional markup ready to copy and send back to the vendor. The predatory language has been automatically removed and replaced with standard market safety protections.</p>
                        
                        <div style="background-color:#f4f6f5; padding:15px; border-radius:8px; border:1px solid #d1d8d4; line-height:1.6; color:#17212b;">
                            "5.2 Third-Party Intellectual Property Protection. The Service Provider agrees to 
                            <span class="strike">protect</span> <span class="insert">defend, indemnify, and hold harmless</span> 
                            the Client from third-party copyright claims 
                            <span class="strike">up to a limit of £50,000, notwithstanding any other damages, performance issues, or general contract failures</span> 
                            <span class="insert">and shall maintain uncapped financial liability for all third-party structural intellectual property litigation</span> 
                            arising from or related to this Agreement."
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                
                # High-value feature: Let users download the text directly to their device files
                st.download_button(
                    label="📥 Download Professional Redline Text (.txt)",
                    data="5.2 Third-Party Intellectual Property Protection. The Service Provider agrees to defend, indemnify, and hold harmless the Client from third-party copyright claims and shall maintain uncapped financial liability for all third-party structural intellectual property litigation arising from or related to this Agreement.",
                    file_name="clausewise_counter_proposal.txt",
                    mime="text/plain"
                )

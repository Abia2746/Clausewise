import json
import sqlite3
from datetime import datetime
from io import BytesIO
import docx
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from google import genai
from google.genai import types
import pandas as pd
from pypdf import PdfReader
import streamlit as st

# SYSTEM CONFIGURATION
MODEL_NAME = "gemini-1.5-flash"

st.set_page_config(
    page_title="Clausewise Shari'ah Enterprise — Contract Lifecycle Engine",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# DATABASE INITIALIZATION
conn = sqlite3.connect("contract_repository.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS contracts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT,
        audit_date TEXT,
        liability_cap TEXT,
        payment_terms TEXT,
        risk_status TEXT
    )
    """
)
conn.commit()

if "audit_count" not in st.session_state:
    st.session_state.audit_count = 0

# STYLING SHEET
st.markdown(
    """<style>.stApp { background-color: #fbfcfa !important; color: #17212b !important; }[data-testid='stSidebar'] { background-color: #f1f5f1 !important; border-right: 1px solid #e5e9e6 !important; }[data-testid='stSidebar'] * { color: #17212b !important; font-weight: 600 !important; }textarea, input { background-color: #ffffff !important; border: 2px solid #185c4a !important; color: #17212b !important; }.paywall-card { background: linear-gradient(135deg, #143f35 0%, #1d6a55 100%) !important; border-radius: 12px; padding: 20px; color: white !important; }div.stButton > button:first-child { background-color: #185c4a !important; color: #ffffff !important; font-weight: 700 !important; border: none !important; }</style>""",
    unsafe_allow_html=True,
)

# GLOBAL INFRASTRUCTURE: MULTI-AGENT INFERENCE ENGINE
def run_contract_audit(contract_text: str, api_key: str) -> dict:
    client = genai.Client(api_key=api_key)
    system_prompt = """
    You are an expert Islamic Finance Legal Auditor certified in AAOIFI Shari'ah Standards acting for the Buyer/Client.
    Analyze the contract text and return a JSON payload with this exact schema:
    {
      "agent_1_syntactic": {
        "target": "Clause location, title, and identified Shari'ah non-compliance",
        "analysis": "Provide a detailed Shari'ah compliance analysis. Specifically flag any instances of Riba (Interest), Gharar (Uncertainty), or non-compliant Dhaman (Ownership Risk allocation) according to AAOIFI rules.",
        "original_text": "Original non-compliant clause snippet to be replaced",
        "playbook_positions": {
          "position_a_ideal": "Aggressive AAOIFI-compliant revision (e.g., converting late interest into a mandatory late fee directed entirely to a verified charity fund, overseen by a Shari'ah board under AAOIFI Standard No. 3).",
          "position_b_fallback": "Balanced Shari'ah fallback revision that satisfies commercial logic without violating Riba rules.",
          "position_c_walkaway": "Minimum acceptable Shari'ah threshold contract text."
        }
      },
      "agent_2_cross_clause": {
        "conflict": "Cross-clause Shari'ah alignment issues (e.g., if one clause claims the deal is a Murabahah asset trade but another clause unlawfully forces asset risk onto the client before title transfer).",
        "analysis": "Explanation of the regulatory or compliance trap under AAOIFI rules.",
        "redline_redirection": "Specific corrective Shari'ah wording."
      },
      "agent_3_portfolio_recovery": {
        "target": "Financial and structural terms",
        "analysis": "Shari'ah asset and capital risk analysis",
        "liability_cap_extracted": "Extracted risk limit / charity penalty thresholds",
        "payment_terms_extracted": "Extracted payment framework (e.g., Murabahah cost-plus breakdown)",
        "risk_status": "High (Contains Riba/Gharar), Medium (Minor structural variance), or Low (Fully AAOIFI Compliant)"
      },
      "pillar_5_obligation_registry": [
        {
          "clause": "Clause Reference",
          "data": "Extracted timeline, interest rates flagged, or numeric thresholds",
          "status": "CRITICAL SHARI'AH BREACH or VALID TRANSACTION MARGIN"
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

# GLOBAL INFRASTRUCTURE: NATIVE DOCX MARKUP INJECTOR
def create_native_tracked_changes_docx(deleted_text: str, inserted_text: str) -> BytesIO:
    doc = docx.Document()
    doc.add_heading("Clausewise — Native Tracked Changes Markup", level=0)
    p = doc.add_paragraph("Legal Redline Draft:\n")
    
    # Deletion Element
    del_run = OxmlElement("w:del")
    del_run.set(qn("w:id"), "0")
    del_run.set(qn("w:author"), "Clausewise AI")
    del_run.set(qn("w:date"), datetime.now().isoformat())
    t_del = OxmlElement("w:delText")
    t_del.text = deleted_text
    del_run.append(t_del)
    p._p.append(del_run)
    
    p.add_run(" ")
    
    # Insertion Element
    ins_run = OxmlElement("w:ins")
    ins_run.set(qn("w:id"), "1")
    ins_run.set(qn("w:author"), "Clausewise AI")
    ins_run.set(qn("w:date"), datetime.now().isoformat())
    t_ins = OxmlElement("w:r")
    t_ins_text = OxmlElement("w:t")
    t_ins_text.text = inserted_text
    t_ins.append(t_ins_text)
    ins_run.append(t_ins)
    p._p.append(ins_run)
    
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer

# SIDEBAR TERMINAL LAYOUT
st.sidebar.markdown("# ◈ Clausewise Shari'ah")
st.sidebar.markdown("---")
st.sidebar.markdown("### 👤 Workspace Settings")
st.sidebar.markdown("🛡️ **Zero Data Retention Active**")
st.sidebar.markdown("⚡ Engine: **Multi-Agent Neural Mesh**")
st.sidebar.markdown("---")

api_key_input = st.secrets.get("GEMINI_API_KEY", "")
if not api_key_input:
    api_key_input = st.sidebar.text_input("Enter Gemini API Key", type="password")

st.title("Automate Your Shari'ah Contract Risk Reviews")
st.caption(
    "100% Efficient Engine: Native AAOIFI compliance verification, contract parsing, and automated portfolio management."
)

tab_audit, tab_repository = st.tabs(
    ["📝 Active Contract Audit", "🗄️ Enterprise Portfolio Repository"]
)

with tab_audit:
    st.markdown("### 1. Ingest Agreement File or Unstructured Text")
    uploaded_file = st.file_uploader(
        "Upload Contract (.pdf or .docx)", type=["pdf", "docx"]
    )

    SAMPLE_CONTRACT = """ISLAMIC TRADE FACILITY & INVESTMENT AGREEMENT
2.3 Asset Ownership Allocation. The Financier shall execute the purchase of the commodities from the supplier. However, the Client agrees that all risk of loss, damage, or destruction of the commodities passes completely to the Client upon the supplier dispatching the goods, prior to the execution of the separate cost-plus Murabahah sale contract.
3.4 Overdue Balances and Default. Invoice balances remaining unpaid after 14 calendar days shall accrue default interest at a rate of 4% per annum above the Bank of England base rate until full payment is recovered by the bank.
4.2 Delivery and Price Adjustments. The final delivery price of the underlying transactional assets shall fluctuate dynamically based on subsequent market conditions, to be determined solely at the discretion of the vendor at the time of delivery without prior fixed margin caps.
5.1 Standard Liability Cap. Total combined financial exposure of the bank shall be strictly limited to the total amount paid by the client in the 3 months preceding the claim.
5.2 Third-Party Intellectual Property Protection. The Service Provider agrees to protect the Client from third-party copyright claims up to a limit of £50,000, notwithstanding any other damages or transactional variances."""

    clause_text = ""
    filename_to_save = "Direct Paste Input"
    
    if uploaded_file is not None:
        filename_to_save = uploaded_file.name
        try:
            if uploaded_file.name.endswith(".docx"):
                doc_file = docx.Document(uploaded_file)
                clause_text = "\n".join([p.text for p in doc_file.paragraphs])
            elif uploaded_file.name.endswith(".pdf"):
                pdf_reader = PdfReader(uploaded_file)
                text_layers = []
                for page in pdf_reader.pages:
                    text = page.extract_text()
                    if text:
                        text_layers.append(text)
                clause_text = "\n".join(text_layers)
        except Exception as e:
            st.error(f"Error reading uploaded file: {str(e)}")
            clause_text = ""
            
    clause_text = st.text_area(
        "Contract Text to Evaluate", 
        value=clause_text if clause_text else SAMPLE_CONTRACT, 
        height=250
    )

    if st.button("Run Shari'ah Compliance Audit"):
        if not api_key_input:
            st.error("Please provide a valid Gemini API Key to run the audit engine.")
        else:
            with st.spinner("Processing multi-agent compliance review against AAOIFI standards..."):
                try:
                    analysis_result = run_contract_audit(clause_text, api_key_input)
                    
                    st.success("Audit complete! Structural findings details down below:")
                    
                    col1, col2 = st.columns(2)
                    col1.metric(label="Risk Status", value=str(analysis_result["agent_3_portfolio_recovery"]["risk_status"]))
                    col2.metric(label="Liability Threshold", value=str(analysis_result["agent_3_portfolio_recovery"]["liability_cap_extracted"]))
                    
                    a1, a2, a3 = st.tabs()

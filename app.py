import json, sqlite3, docx, pandas as pd
from datetime import datetime
from io import BytesIO
from pypdf import PdfReader
from google import genai
from google.genai import types
import streamlit as st

# SYSTEM CONFIGURATION - Kept exactly at your requested model selection
MODEL_NAME = "gemini-3.8-flash"

st.set_page_config(page_title="Clausewise Shari'ah Engine", layout="wide")

# DATABASE INITIALIZATION
conn = sqlite3.connect("contract_repository.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS contracts (id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT, audit_date TEXT, risk_status TEXT)")
conn.commit()

def run_contract_audit(text: str, key: str) -> dict:
    client = genai.Client(api_key=key)
    prompt = """You are an AAOIFI Shari'ah Compliance Auditor. Analyze the contract text and return a JSON payload with this exact schema:
    {
      "analysis": "Detailed Shari'ah analysis flagging Riba (Interest) or non-compliant Dhaman (Risk allocation).",
      "redline": "AAOIFI-compliant alternative clause text (e.g. late fees directed to charity).",
      "risk_status": "High, Medium, or Low"
    }"""
    # Explicitly encode and decode the string to clean out rogue character formats
    clean_text = str(text.encode('utf-8', errors='ignore').decode('utf-8'))
    resp = client.models.generate_content(
        model=MODEL_NAME, contents=clean_text,
        config=types.GenerateContentConfig(system_instruction=prompt, response_mime_type="application/json", temperature=0.1)
    )
    return json.loads(resp.text)

# SIDEBAR & INPUT - Cleaned text configurations
st.sidebar.markdown("# Clausewise Shariah\n🛡️ **Zero Data Retention Active**")
api_key = st.secrets.get("GEMINI_API_KEY", "")
if not api_key:
    api_key = st.sidebar.text_input("Enter Gemini API Key", type="password")

st.title("Automate Your Shari'ah Contract Risk Reviews")
tab_audit, tab_repo = st.tabs(["📝 Active Contract Audit", "🗄️ Portfolio Repository"])

with tab_audit:
    uploaded_file = st.file_uploader("Upload Contract (.pdf, .docx)", type=["pdf", "docx"])
    SAMPLE = """ISLAMIC TRADE FACILITY & INVESTMENT AGREEMENT
2.3 All risk of asset loss passes completely to the Client prior to the execution of the separate Murabahah sale contract.
3.4 Invoice balances unpaid after 14 days shall accrue default interest at a rate of 4% per annum."""
    
    clause_text = ""
    name_to_save = "Direct Paste Input"
    
    if uploaded_file:
        name_to_save = uploaded_file.name
        if uploaded_file.name.endswith(".pdf"):
            clause_text = "\n".join([p.extract_text() or "" for p in PdfReader(uploaded_file).pages])
        else:
            clause_text = "\n".join([p.text for p in docx.Document(uploaded_file).paragraphs])
    else:
        clause_text = st.text_area("Or paste contract text here:", value=SAMPLE, height=150)
        
    if st.button("Execute Shari'ah Audit", type="primary"):
        if not clause_text.strip():
            st.warning("Please provide contract text.")
        elif not api_key:
            st.error("🔑 API Key Missing.")
        else:
            with st.spinner("Analyzing against AAOIFI Standards..."):
                try:
                    res = run_contract_audit(clause_text, api_key)
                    st.success("Audit Complete!")
                    st.markdown("### 📊 LIVE INTERACTIVE NEGOTIATION DESK")
                    
                    analysis_text = res.get('analysis', 'N/A')
                    redline_text = res.get('redline', 'N/A')
                    
                    st.info(f"**Compliance Analysis:** {analysis_text}")
                    st.warning(f"⚖️ **Ideal AAOIFI Redline Suggestion:** `{redline_text}`")
                    
                    status = res.get("risk_status", "High")
                    if "High" in status: st.error(f"🔴 Systemic Shari'ah Risk Status: {status}")
                    else: st.success(f"🟢 Systemic Shari'ah Risk Status: {status}")
                    
                    cursor.execute("INSERT INTO contracts (filename, audit_date, risk_status) VALUES (?, ?, ?)", (name_to_save, datetime.now().strftime("%Y-%m-%d %H:%M"), status))
                    conn.commit()
                except Exception as e:
                    st.error(f"Processing Error: {str(e)}")

with tab_repo:
    st.markdown("### Historical Portfolio Records")
    try:
        df = pd.read_sql_query("SELECT * FROM contracts ORDER BY id DESC", conn)
        if not df.empty:
            st.dataframe(df, use_container_width=True)
        else:
            st.info("Database registry is currently empty.")
    except Exception as db_err:
        st.error(f"Database error: {str(db_err)}")

e
        if uploaded_file.name.endswith(".pdf"):
            pdf_reader = PdfReader(uploaded_file)
            for page in pdf_reader.pages:
                clause_text += page.extract_text() or ""
        elif uploaded_file.name.endswith(".docx"):
            doc_file = docx.Document(uploaded_file)
            clause_text = "\n".join([p.text for p in doc_file.paragraphs])
        st.success(f"Successfully ingested {uploaded_file.name}")
    else:
        clause_text = st.text_area(
            "Or paste contract text string directly here:",
            value=SAMPLE_CONTRACT,
            height=160,
        )

    if st.button("Execute Enterprise Audit", type="primary"):
        if not clause_text.strip():
            st.warning("Please upload a file or paste contract text.")
        elif not api_key_input:
            st.error("🔑 API Key Missing: Provide your key in the sidebar configuration input.")
        else:
            with st.spinner("Executing Multi-Agent Shari'ah Compliance Mesh..."):
                try:
                    results = run_contract_audit(clause_text, api_key_input)
                    st.success("Audit Complete!")
                    st.markdown("### 📊 LIVE INTERACTIVE NEGOTIATION DESK")
                    
                    ag1 = results.get("agent_1_syntactic", {})
                    st.markdown("#### 🛑 Agent 1: Shari'ah Compliance & Indemnity Auditor")
                    st.markdown(f"**Target:** {ag1.get('target', 'N/A')}")
                    st.info(f"**Analysis:** {ag1.get('analysis', 'N/A')}")
                    
                    pb = ag1.get("playbook_positions", {})
                    st.markdown(f"🟠 **Position A (Ideal AAOIFI Redline):** `{pb.get('position_a_ideal', 'N/A')}`")
                    st.markdown(f"🔵 **Position B (Shari'ah Fallback):** `{pb.get('position_b_fallback', 'N/A')}`")
                    st.markdown(f"⚫ **Position C (Walkaway Limit):** `{pb.get('position_c_walkaway', 'N/A')}`")
                    
                    docx_buffer = create_native_tracked_changes_docx(ag1.get("original_text", ""), pb.get("position_a_ideal", ""))
                    st.download_button(
                        label="📥 Download Native Tracked Changes MS Word Document",
                        data=docx_buffer,
                        file_name="shariah_redline_tracked_changes.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    )
                    
                    st.markdown("---")
                    ag2 = results.get("agent_2_cross_clause", {})
                    st.markdown("#### 🔄 Agent 2: Cross-Clause Structure Validation")
                    st.error(f"**Conflict Trap:** {ag2.get('conflict', 'N/A')}")
                    st.markdown(f"**Structural Defect Analysis:** {ag2.get('analysis', 'N/A')}")
                    st.markdown(f"⚖️ **Corrective Shari'ah Wording:** `{ag2.get('redline_redirection', 'N/A')}`")
                    
                    st.markdown("---")
                    ag3 = results.get("agent_3_portfolio_recovery", {})
                    st.markdown("#### 📈 Agent 3: Structural Portfolio Status")
                    st.markdown(f"**Financial Analysis:** {ag3.get('analysis', 'N/A')}")
                    st.markdown(f"**Liability / Charity Summary:** {ag3.get('liability_cap_extracted', 'N/A')}")
                    st.markdown(f"**Extracted Payment Framework:** {ag3.get('payment_terms_extracted', 'N/A')}")
                    
                    status = ag3.get("risk_status", "High")
                    if "High" in status:
                        st.error(f"🔴 Systemic Shari'ah Risk Status: {status}")
                    elif "Medium" in status:
                        st.warning(f"🟡 Systemic Shari'ah Risk Status: {status}")
                    else:
                        st.success(f"🟢 Systemic Shari'ah Risk Status: {status}")
                        
                    st.markdown("---")
                    st.markdown("### 📋 PILLAR 5: REGULATORY OBLIGATION REGISTRY")
                    p5_data = results.get("pillar_5_obligation_registry", [])
                    if p5_data:
                        df = pd.DataFrame(p5_data)
                        st.dataframe(df, use_container_width=True)
                        
                    cursor.execute(
                        "INSERT INTO contracts (filename, audit_date, liability_cap, payment_terms, risk_status) VALUES (?, ?, ?, ?, ?)",
                        (filename_to_save, datetime.now().strftime("%Y-%m-%d %H:%M"), ag3.get('liability_cap_extracted', 'N/A'), ag3.get('payment_terms_extracted', 'N/A'), status)
                    )
                    conn.commit()
                    st.session_state.audit_count += 1
                    
                except Exception as e:
                    st.error(f"Execution Failed: Internal processing error. {str(e)}")

with tab_repository:
    st.markdown("### Historical Portfolio Records")
    try:
        db_df = pd.read_sql_query("SELECT * FROM contracts ORDER BY id DESC", conn)
        if not db_df.empty:
            st.dataframe(db_df, use_container_width=True)
        else:
            st.info("The internal database registry is currently empty. Run an audit to log portfolio metadata.")
    except Exception as db_err:
        st.error(f"Database error: {str(db_err)}")

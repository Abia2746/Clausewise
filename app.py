    if st.button("Execute Enterprise Audit", type="primary"):
        if not clause_text.strip():
            st.warning("Please upload a file or paste contract text.")
        elif not api_key_input:
            st.error("🔑 API Key Missing: Ensure GEMINI_API_KEY is configured in your Advanced Settings.")
        else:
            with st.spinner("Executing Multi-Agent Shari'ah Compliance Mesh..."):
                try:
                    results = run_contract_audit(clause_text, api_key_input)
                    st.success("Audit Complete!")
                    st.markdown("### 📊 LIVE INTERACTIVE NEGOTIATION DESK")
                    
                    ag1 = results.get("agent_1_syntactic", {})
                    st.markdown(f"#### 🛑 Agent 1: Shari'ah Compliance & Indemnity Auditor")
                    st.markdown(f"**Target:** {ag1.get('target')}")
                    st.info(f"**Analysis:** {ag1.get('analysis')}")
                    
                    pb = ag1.get("playbook_positions", {})
                    st.markdown(f"🟠 **Position A (Ideal AAOIFI Redline):** `{pb.get('position_a_ideal')}`")
                    st.markdown(f"🔵 **Position B (Shari'ah Fallback):** `{pb.get('position_b_fallback')}`")
                    st.markdown(f"⚫ **Position C (Walkaway Limit):** `{pb.get('position_c_walkaway')}`")
                    
                    # Generate docx download using the custom markup injector
                    docx_buffer = create_native_tracked_changes_docx(ag1.get("original_text", ""), pb.get("position_a_ideal", ""))
                    st.download_button(
                        label="📥 Download Native Tracked Changes MS Word Document",
                        data=docx_buffer,
                        file_name="shariah_redline_tracked_changes.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    )
                    
                    st.markdown("---")
                    ag2 = results.get("agent_2_cross_clause", {})
                    st.markdown(f"#### 🔄 Agent 2: Cross-Clause Structure Validation")
                    st.error(f"**Conflict Trap:** {ag2.get('conflict')}")
                    st.markdown(f"**Structural Defect Analysis:** {ag2.get('analysis')}")
                    st.markdown(f"⚖️ **Corrective Shari'ah Wording:** `{ag2.get('redline_redirection')}`")
                    
                    st.markdown("---")
                    ag3 = results.get("agent_3_portfolio_recovery", {})
                    st.markdown(f"#### 📈 Agent 3: Structural Portfolio Status")
                    st.markdown(f"**Financial Analysis:** {ag3.get('analysis')}")
                    st.markdown(f"**Liability / Charity Summary:** {ag3.get('liability_cap_extracted')}")
                    st.markdown(f"**Extracted Payment Framework:** {ag3.get('payment_terms_extracted')}")
                    
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
                        
                    # Save metrics securely to local state repository
                    cursor.execute(
                        "INSERT INTO contracts (filename, audit_date, liability_cap, payment_terms, risk_status) VALUES (?, ?, ?, ?, ?)",
                        (filename_to_save, datetime.now().strftime("%Y-%m-%d %H:%M"), ag3.get('liability_cap_extracted'), ag3.get('payment_terms_extracted'), status)
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

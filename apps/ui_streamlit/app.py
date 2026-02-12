import json
import os
import requests
import streamlit as st

API_URL = os.getenv("ANALYST_API_URL", "http://localhost:8010").rstrip("/")

st.set_page_config(page_title="AWOA Analyst Agent (Phase 3)", layout="wide")

st.title("AWOA Analyst Agent — Phase 3")
st.caption("Deterministic router + tool-calling + evidence-backed diagnosis (no external LLM required).")

with st.sidebar:
    st.header("Filters")
    domain = st.text_input("domain (optional)", value="")
    task = st.selectbox("task (optional)", options=["", "pricing", "refund", "contact"], index=0)
    tr_mode = st.selectbox("time_range", options=["relative", "start/end"], index=0)
    time_range = {}
    if tr_mode == "relative":
        rel = st.text_input("relative (e.g., 7d, 24h)", value="7d")
        time_range = {"relative": rel}
    else:
        start = st.text_input("start ISO (e.g., 2026-02-01T00:00:00Z)", value="")
        end = st.text_input("end ISO (e.g., 2026-02-10T00:00:00Z)", value="")
        time_range = {"start": start or None, "end": end or None}

question = st.text_area(
    "Ask a question",
    value="Show the top 5 failure hotspots for refund and explain why.",
    height=110,
)

col1, col2 = st.columns([1, 1])
with col1:
    if st.button("Ask Analyst", type="primary"):
        payload = {
            "question": question,
            "domain": domain or None,
            "task": task or None,
            "time_range": time_range or None,
        }
        try:
            r = requests.post(f"{API_URL}/ask", json=payload, timeout=60)
            r.raise_for_status()
            data = r.json()
            st.session_state["last"] = data
        except Exception as e:
            st.error(f"Request failed: {e}")

with col2:
    if st.button("Clear"):
        st.session_state.pop("last", None)

data = st.session_state.get("last")
if data:
    result = data.get("result", {})
    st.subheader("Markdown Report")
    st.markdown(data.get("markdown", ""), unsafe_allow_html=False)

    st.subheader("Structured JSON")
    st.json(result)

    st.subheader("Plan")
    st.write(result.get("plan", []))

    st.subheader("Evidence traces")
    ev = result.get("evidence", {}).get("example_traces", [])
    for t in ev:
        st.markdown(f"**run_id:** `{t.get('run_id')}`")
        st.json(t.get("trace", []))
        st.divider()

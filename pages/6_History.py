"""
pages/6_📦_Session.py
Current session summary — no database storage in testing mode.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import pandas as pd
import json

st.set_page_config(page_title="Session", page_icon="📦", layout="wide")
st.title("📦 Session Data")
st.caption("Testing mode — results live in memory only (no database)")

results = st.session_state.get("experiment_results", {})

if not results:
    st.info("No results in the current session. Run the experiment first.")
    st.stop()

st.info(
    f"**{len(results)} funders** processed in this session. "
    "Results are in-memory only — export CSVs from the **Results** page before closing."
)

# ─── Raw JSON dump for debugging ─────────────────────────────────────────────
st.subheader("🔍 Raw Session Data (Debug)")

ein_options = {r.get("org_name", ein): ein for ein, r in results.items()}
selected = st.selectbox("Inspect a funder's raw result", list(ein_options.keys()))
selected_ein = ein_options[selected]

raw = results[selected_ein].copy()
# Drop the full contacts list to keep it readable — show separately
contacts = raw.pop("contacts", [])

st.json(raw)

if contacts:
    st.subheader(f"Contacts ({len(contacts)})")
    st.dataframe(pd.DataFrame(contacts).drop(columns=["photo_url", "snippet"], errors="ignore"),
                 use_container_width=True)

# ─── Full session export ──────────────────────────────────────────────────────
st.divider()
all_contacts = []
for ein, r in results.items():
    for p in (r.get("contacts") or []):
        all_contacts.append({
            "ein": ein, "org_name": r.get("org_name"),
            **{k: v for k, v in p.items() if k not in ("photo_url", "snippet")},
        })

if all_contacts:
    st.download_button(
        "📥 Download full session contacts (JSON)",
        data=json.dumps(
            {ein: {**{k: v for k, v in r.items() if k != "contacts"},
                   "contacts": r.get("contacts", [])}
             for ein, r in results.items()},
            indent=2, default=str
        ),
        file_name="session_results.json",
        mime="application/json",
    )

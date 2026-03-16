"""
pages/6_🗂️_History.py
Browse all past experiment sessions from Supabase.
Click any session to see full funder results and contacts.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import pandas as pd

from utils.supabase_client import (
    get_or_create_client, load_all_sessions,
    load_funder_results, load_contacts,
)

st.set_page_config(page_title="History", page_icon="🗂️", layout="wide")
st.title("🗂️ Experiment History")
st.caption("All past experiment sessions saved to Supabase")

# ─── Connect ──────────────────────────────────────────────────────────────────
sb, err = get_or_create_client()
if not sb:
    st.error(f"Could not connect to Supabase: {err}")
    st.stop()

# ─── Load sessions ────────────────────────────────────────────────────────────
with st.spinner("Loading sessions..."):
    sessions = load_all_sessions(sb)

if not sessions:
    st.info("No experiment sessions found yet. Run an experiment first.")
    st.stop()

# ─── Session selector ─────────────────────────────────────────────────────────
st.subheader(f"📋 {len(sessions)} Past Sessions")

session_labels = []
for s in sessions:
    date  = (s.get("started_at") or "")[:16].replace("T", " ")
    done  = s.get("funders_done", 0)
    total = s.get("total_funders", 0)
    status = s.get("status", "")
    label = f"{date}  ·  {done}/{total} funders  ·  {status}"
    session_labels.append(label)

selected_label = st.selectbox("Select a session to inspect", session_labels)
selected_idx   = session_labels.index(selected_label)
selected_session = sessions[selected_idx]
session_id     = selected_session["id"]

st.divider()

# ─── Session summary ──────────────────────────────────────────────────────────
s1, s2, s3, s4 = st.columns(4)
s1.metric("Status",        selected_session.get("status", "").title())
s2.metric("Funders Done",  selected_session.get("funders_done", 0))
s3.metric("Total Funders", selected_session.get("total_funders", 0))
started = (selected_session.get("started_at") or "")[:19].replace("T", " ")
completed = (selected_session.get("completed_at") or "—")[:19].replace("T", " ")
s4.metric("Started", started)

if selected_session.get("notes"):
    st.caption(selected_session["notes"])

st.divider()

# ─── Funder results table ─────────────────────────────────────────────────────
with st.spinner("Loading funder results..."):
    funder_rows = load_funder_results(sb, session_id)

if not funder_rows:
    st.info("No funder results saved for this session.")
    st.stop()

st.subheader(f"Funders in this session ({len(funder_rows)})")

summary_df = pd.DataFrame([{
    "Organization":    r.get("org_name", "")[:50],
    "EIN":             r.get("ein", ""),
    "Segment":         r.get("segment", ""),
    "City/State":      f"{r.get('city','') or ''} {r.get('state','') or ''}".strip(),
    "Discovered":      r.get("discovered_count", 0),
    "🎯 Grant Rel":    r.get("grant_relevant_count", 0),
    "Queries":         r.get("serper_queries_run", 0),
    "Apollo":          r.get("apollo_profiles_found", 0),
    "Enriched":        r.get("enrichments_done", 0),
    "Errors":          "⚠️" if r.get("api_errors") else "",
} for r in funder_rows])

st.dataframe(summary_df, use_container_width=True, height=350)

# Export
st.download_button(
    "📥 Download session_funders.csv",
    data=summary_df.to_csv(index=False),
    file_name=f"session_{session_id[:8]}_funders.csv",
    mime="text/csv",
)

st.divider()

# ─── Funder drill-down ────────────────────────────────────────────────────────
st.subheader("🔍 Funder Drill-Down")

funder_options = {r.get("org_name", r.get("ein", "")): r for r in funder_rows}
selected_org   = st.selectbox("Select a funder", list(funder_options.keys()))
selected_funder = funder_options[selected_org]
selected_ein   = selected_funder.get("ein")

# Metrics row
h1, h2, h3, h4, h5 = st.columns(5)
h1.metric("Discovered",      selected_funder.get("discovered_count", 0))
h2.metric("🎯 Grant Rel",    selected_funder.get("grant_relevant_count", 0))
h3.metric("Serper Queries",  selected_funder.get("serper_queries_run", 0))
h4.metric("Apollo Found",    selected_funder.get("apollo_profiles_found", 0))
h5.metric("⚠️ Errors",       len(selected_funder.get("api_errors") or []))

st.caption(
    f"EIN: {selected_ein}  ·  "
    f"{selected_funder.get('city', '')} {selected_funder.get('state', '')}  ·  "
    f"Segment: {selected_funder.get('segment', '')}  ·  "
    f"Domain: {selected_funder.get('domain') or 'N/A'}"
)

# ─── Contacts ─────────────────────────────────────────────────────────────────
with st.spinner("Loading contacts..."):
    contacts = load_contacts(sb, session_id, selected_ein)

if contacts:
    st.subheader(f"👥 Contacts ({len(contacts)})")

    show_grant_only = st.checkbox("Grant-relevant only")
    display = [c for c in contacts if c.get("is_grant_relevant")] if show_grant_only else contacts

    for person in display:
        name        = person.get("person_name") or "Unknown"
        title       = person.get("current_title") or ""
        company     = person.get("current_company") or ""
        linkedin    = person.get("linkedin_url") or ""
        photo_url   = person.get("photo_url") or ""
        enriched    = person.get("enriched", False)
        grant_rel   = person.get("is_grant_relevant", False)
        source      = person.get("source", "")
        match_score = person.get("company_match_score", 0)

        with st.container():
            col_photo, col_a, col_b, col_c = st.columns([1, 3, 3, 2])
            with col_photo:
                if photo_url:
                    st.image(photo_url, width=56)
                else:
                    st.markdown("👤")
            with col_a:
                st.markdown(f"**{name}**")
                st.caption(f"Source: {source}")
            with col_b:
                if title:
                    st.markdown(f"*{title}*")
                if company:
                    st.caption(f"@ {company}")
                if grant_rel:
                    st.caption("🎯 Grant-relevant role")
            with col_c:
                if match_score >= 60:
                    st.caption(f"Match: {match_score}%")
                if enriched:
                    st.caption("✓ Enriched")
                if linkedin:
                    st.markdown(f"[LinkedIn]({linkedin})")
                else:
                    st.caption("No LinkedIn URL")
        st.markdown("---")

    # Export contacts
    export_cols = ["person_name", "current_title", "current_company",
                   "linkedin_url", "source", "enriched", "is_grant_relevant",
                   "company_match_score"]
    st.download_button(
        f"📥 Download {selected_org[:30]}_contacts.csv",
        data=pd.DataFrame([{c: p.get(c, "") for c in export_cols} for p in contacts]).to_csv(index=False),
        file_name=f"{selected_ein}_contacts.csv",
        mime="text/csv",
    )
else:
    st.info("No contacts saved for this funder.")

# ─── API errors ───────────────────────────────────────────────────────────────
api_errors = selected_funder.get("api_errors") or []
if api_errors:
    with st.expander(f"⚠️ API Errors ({len(api_errors)})"):
        for err in api_errors:
            st.error(f"**{err.get('step', '?')}**: {err.get('error', '')}")

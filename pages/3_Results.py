"""
pages/3_📋_Results.py
Discovered contacts explorer — no IRS cross-referencing.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import pandas as pd

st.set_page_config(page_title="Results", page_icon="📋", layout="wide")
st.title("📋 Results Explorer")
st.caption("Per-funder discovered contacts")

results = st.session_state.get("experiment_results", {})

if not results:
    st.info("No results yet. Run the experiment first.")
    st.stop()

# ─── Summary table ────────────────────────────────────────────────────────────
st.subheader("All Funders Summary")

summary_rows = []
for ein, r in results.items():
    summary_rows.append({
        "EIN":            ein,
        "Organization":   r.get("org_name", "")[:50],
        "Segment":        r.get("segment", ""),
        "City/State":     f"{r.get('city', '')} {r.get('state', '')}".strip(),
        "Discovered":     r.get("discovered_count", 0),
        "🎯 Grant Relevant": r.get("grant_relevant_count", 0),
        "Queries Run":    r.get("serper_queries_run", 0),
        "Apollo Found":   r.get("apollo_profiles_found", 0),
        "Enriched":       r.get("enrichments_done", 0),
        "Errors":         "⚠️" if r.get("api_errors") else "",
    })

summary_df = pd.DataFrame(summary_rows)

# Filters
f1, f2, f3 = st.columns(3)
with f1:
    seg_opts = summary_df["Segment"].dropna().unique().tolist()
    seg_filter = st.multiselect("Segment", seg_opts, default=seg_opts)
with f2:
    show_errors_only = st.checkbox("Only show funders with errors")
with f3:
    sort_col = st.selectbox("Sort by", ["Discovered", "🎯 Grant Relevant", "Organization"])

filtered = summary_df[summary_df["Segment"].isin(seg_filter)]
if show_errors_only:
    filtered = filtered[filtered["Errors"] != ""]
filtered = filtered.sort_values(sort_col, ascending=False)

st.dataframe(filtered, use_container_width=True, height=400)

# ─── Export ───────────────────────────────────────────────────────────────────
col1, col2 = st.columns(2)

with col1:
    st.download_button(
        "📥 Download funders_summary.csv",
        data=summary_df.to_csv(index=False),
        file_name="funders_summary.csv",
        mime="text/csv",
    )

with col2:
    all_contacts = []
    for ein, r in results.items():
        for p in (r.get("contacts") or []):
            all_contacts.append({
                "ein":      ein,
                "org_name": r.get("org_name", ""),
                **{k: v for k, v in p.items() if k != "photo_url"},
            })
    if all_contacts:
        st.download_button(
            "📥 Download all_contacts.csv",
            data=pd.DataFrame(all_contacts).to_csv(index=False),
            file_name="all_contacts.csv",
            mime="text/csv",
        )

st.divider()

# ─── Per-funder drill-down ────────────────────────────────────────────────────
st.subheader("🔍 Funder Drill-Down")

funder_options = {r.get("org_name", ein): ein for ein, r in results.items()}
selected_name  = st.selectbox("Select a funder", list(funder_options.keys()))
selected_ein   = funder_options.get(selected_name)

if selected_ein:
    r        = results[selected_ein]
    contacts = r.get("contacts") or []

    h1, h2, h3, h4, h5 = st.columns(5)
    h1.metric("Discovered",      r.get("discovered_count", 0))
    h2.metric("🎯 Grant Relevant", r.get("grant_relevant_count", 0))
    h3.metric("Serper Queries",  r.get("serper_queries_run", 0))
    h4.metric("Apollo Profiles", r.get("apollo_profiles_found", 0))
    h5.metric("⚠️ Errors",       len(r.get("api_errors") or []))

    st.caption(
        f"EIN: {selected_ein} · "
        f"{r.get('city', '')} {r.get('state', '')} · "
        f"Segment: {r.get('segment', '')} · "
        f"Domain: {r.get('domain') or 'N/A'}"
    )

    # ── Contacts ──────────────────────────────────────────────────────────
    if contacts:
        st.subheader(f"👥 Contacts ({len(contacts)})")

        # Filter by grant-relevant
        show_grant_only = st.checkbox("Show grant-relevant only")
        display_contacts = [p for p in contacts if p.get("is_grant_relevant")] \
            if show_grant_only else contacts

        for person in display_contacts:
            name      = person.get("person_name") or "Unknown"
            title     = person.get("current_title") or ""
            company   = person.get("current_company") or ""
            linkedin  = person.get("linkedin_url") or ""
            photo_url = person.get("photo_url") or ""
            enriched  = person.get("enriched", False)
            grant_rel = person.get("is_grant_relevant", False)
            source    = person.get("source", "")

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
                    if enriched:
                        st.caption("✓ Enriched")
                    if linkedin:
                        st.markdown(f"[LinkedIn]({linkedin})")
                    else:
                        st.caption("No LinkedIn URL")
            st.markdown("---")

        # Per-funder CSV
        export_cols = ["person_name", "current_title", "current_company",
                       "linkedin_url", "source", "enriched", "is_grant_relevant"]
        st.download_button(
            f"📥 Download {selected_name[:30]}_contacts.csv",
            data=pd.DataFrame([{c: p.get(c, "") for c in export_cols} for p in contacts]).to_csv(index=False),
            file_name=f"{selected_ein}_contacts.csv",
            mime="text/csv",
        )

    else:
        st.info("No contacts discovered for this funder.")

    # ── API errors ────────────────────────────────────────────────────────
    api_errors = r.get("api_errors") or []
    if api_errors:
        with st.expander(f"⚠️ API Errors ({len(api_errors)})", expanded=False):
            for err in api_errors:
                st.error(f"**{err.get('step', '?')}**: {err.get('error', '')}")

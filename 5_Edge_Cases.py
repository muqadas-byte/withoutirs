"""
pages/5_⚠️_Edge_Cases.py
Failure analysis for the discovery pipeline.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import pandas as pd

from utils.metrics_calc import compute_metrics

st.set_page_config(page_title="Edge Cases", page_icon="⚠️", layout="wide")
st.title("⚠️ Edge Cases & Failure Analysis")
st.caption("Failure categories and mitigations for the discovery pipeline")

results = st.session_state.get("experiment_results", {})
if not results:
    st.info("No results yet. Run the experiment first.")
    st.stop()

funder_stats = list(results.values())
metrics      = compute_metrics(funder_stats)

# ─── Categorize failures ──────────────────────────────────────────────────────
failures = {
    "no_results":        [],   # Zero contacts found
    "serper_auth":       [],
    "apollo_auth":       [],
    "credits_exhausted": [],
    "connection_errors": [],
    "common_name_risk":  [],
}

COMMON_NAME_FRAGMENTS = [
    "united way", "community foundation", "family foundation",
    "health foundation", "education foundation", "arts council",
]

for r in funder_stats:
    ein    = r.get("ein")
    org    = r.get("org_name", "")
    errors = r.get("api_errors") or []

    if r.get("discovered_count", 0) == 0:
        failures["no_results"].append({"ein": ein, "org": org,
                                       "domain": r.get("domain") or "—",
                                       "city_state": f"{r.get('city','')} {r.get('state','')}".strip()})

    for err in errors:
        err_str = err.get("error", "")
        step    = err.get("step", "")
        if "AUTH_ERROR" in err_str and step == "serper":
            failures["serper_auth"].append({"ein": ein, "org": org})
        elif "AUTH_ERROR" in err_str and "apollo" in step:
            failures["apollo_auth"].append({"ein": ein, "org": org})
        elif "CREDITS_EXHAUSTED" in err_str:
            failures["credits_exhausted"].append({"ein": ein, "org": org})
        elif "CONNECTION_ERROR" in err_str or "TIMEOUT" in err_str:
            failures["connection_errors"].append({"ein": ein, "org": org, "error": err_str})

    if any(frag in org.lower() for frag in COMMON_NAME_FRAGMENTS):
        failures["common_name_risk"].append({"ein": ein, "org": org})

# ─── Display ──────────────────────────────────────────────────────────────────
total = sum(len(v) for v in failures.values())
st.metric("Total Edge Cases Identified", total)
st.divider()

if failures["serper_auth"]:
    st.subheader("🔴 SerpApi Authentication Errors")
    st.error(f"{len(failures['serper_auth'])} auth failures — discovery stopped for these funders.")
    st.markdown("**Fix:** Check your SerpApi key at serpapi.com/manage-api-key")

if failures["apollo_auth"]:
    st.subheader("🔴 Apollo Authentication Errors")
    st.error(f"{len(failures['apollo_auth'])} Apollo auth failures.")
    st.markdown("**Fix:** Verify your Apollo key. Search and Match keys are separate — check both.")

if failures["credits_exhausted"]:
    st.subheader("🟡 Apollo Credits Exhausted")
    st.warning(f"Credits ran out — {len(failures['credits_exhausted'])} funders had no enrichment.")
    st.markdown("**Fix:** Lower **Max Enrichment Credits** in settings or upgrade your Apollo plan.")

if failures["connection_errors"]:
    st.subheader("🟡 Connection / Timeout Errors")
    st.warning(f"{len(failures['connection_errors'])} network errors.")
    with st.expander("See affected funders"):
        st.dataframe(pd.DataFrame(failures["connection_errors"]), use_container_width=True)
    st.markdown("**Fix:** Check network. These funders can be re-run individually.")

st.divider()

if failures["no_results"]:
    st.subheader("🔵 Zero Contacts Found")
    st.info(f"{len(failures['no_results'])} funders returned no contacts from either SerpApi or Apollo.")
    with st.expander("See affected funders"):
        st.dataframe(pd.DataFrame(failures["no_results"]), use_container_width=True)
    st.markdown("""
    **Possible causes:**
    - Small/local orgs with no LinkedIn presence
    - No domain available — reduces query specificity
    - Org name too generic or uncommon for Google indexing

    **Mitigations:**
    - Try scraping the org's own website for a staff page
    - Add EIN to query for disambiguation
    - Accept zero-result orgs as "no online footprint" — label them accordingly
    """)

if failures["common_name_risk"]:
    st.subheader("ℹ️ Common Name Risk")
    st.info(
        f"{len(failures['common_name_risk'])} funders have generic names "
        "(e.g. 'United Way', 'Community Foundation') that may surface unrelated profiles."
    )
    with st.expander("See affected funders"):
        st.dataframe(pd.DataFrame(failures["common_name_risk"]), use_container_width=True)
    st.markdown("""
    **Mitigation:**
    - Always include city/state in queries for these orgs (already done by `build_serp_queries`)
    - Prefer domain-based queries when a domain is available
    - Require `current_company` to contain the org name before showing a contact
    """)

# ─── Export ───────────────────────────────────────────────────────────────────
export_rows = []
for category, items in failures.items():
    for item in items:
        export_rows.append({"category": category, **item})

if export_rows:
    st.download_button(
        "📥 Download edge_cases.csv",
        data=pd.DataFrame(export_rows).to_csv(index=False),
        file_name="edge_cases.csv",
        mime="text/csv",
    )

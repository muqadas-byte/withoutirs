"""
pages/2_🔬_Run_Experiment.py
Org-signal discovery pipeline — SerpApi + Apollo People Search + Enrichment.
Results persisted to Supabase.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import time
import streamlit as st
import pandas as pd

from utils.serper_client import run_discovery, SerperAuthError
from utils.apollo_client import search_people_by_company, enrich_person
from utils.data_loader import build_serp_queries, build_apollo_params, is_excluded_title
from utils.metrics_calc import compute_metrics
from utils.supabase_client import (
    get_or_create_client, create_session, complete_session,
    save_funder_result, save_contacts,
)

st.set_page_config(page_title="Run Experiment", page_icon="🔬", layout="wide")
st.title("🔬 Run Experiment")
st.caption("SerpApi + Apollo discovery · Results saved to Supabase")

# ─── Prerequisites ────────────────────────────────────────────────────────────
errors = []
if not st.session_state.get("funders_loaded"):
    errors.append("No funders loaded — upload 100randomFunders.json on the Home page")
if not st.session_state.get("serpapi_key"):
    errors.append("SerpApi key missing — configure on Home page")

if errors:
    for e in errors:
        st.error(f"⛔ {e}")
    st.stop()

funders           = st.session_state["funders"]
serpapi_key       = st.session_state["serpapi_key"]
apollo_search_key = st.session_state.get("apollo_search_key", "")
apollo_match_key  = st.session_state.get("apollo_match_key", "")
enrich_enabled    = st.session_state.get("enrich_enabled", True)
max_funders       = st.session_state.get("max_funders", 100)
enrich_budget     = st.session_state.get("enrich_budget", 100)
max_contacts      = st.session_state.get("max_contacts_per_funder", 10)

# ─── Settings summary ─────────────────────────────────────────────────────────
with st.expander("⚙️ Current Settings", expanded=False):
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Funders to Process", min(max_funders, len(funders)))
    s2.metric("Max Contacts / Funder", max_contacts)
    s3.metric("Enrichment", "Enabled" if enrich_enabled else "Disabled")
    s4.metric("Enrichment Budget", enrich_budget if enrich_enabled else "—")

# ─── Resume / re-run ──────────────────────────────────────────────────────────
already_done    = st.session_state.get("experiment_done", False)
already_running = st.session_state.get("experiment_running", False)
results_so_far  = st.session_state.get("experiment_results", {})

if already_done and results_so_far:
    st.success(f"Experiment completed — {len(results_so_far)} funders processed.")
    if st.button("🔄 Re-run Experiment (clears previous results)"):
        st.session_state["experiment_results"] = {}
        st.session_state["experiment_done"] = False
        st.rerun()
    st.info("Go to **📋 Results** or **📈 Metrics** to explore the results.")
    st.stop()

# ─── Funder selection ─────────────────────────────────────────────────────────
st.subheader("🎯 Funder Selection")
selection_mode = st.radio(
    "How do you want to select funders?",
    ["Run first N funders", "Pick specific funders by name"],
    horizontal=True,
)
if selection_mode == "Pick specific funders by name":
    all_names = [f["name"] for f in funders]
    selected_names = st.multiselect(
        "Search and select funders to run",
        options=all_names,
        placeholder="Type a foundation name...",
    )
    funders_to_run = [f for f in funders if f["name"] in selected_names]
    if not funders_to_run:
        st.info("Select at least one funder above to continue.")
        st.stop()
else:
    funders_to_run = funders[:max_funders]

# ─── Pre-flight summary ───────────────────────────────────────────────────────
total_queries_estimate = len(funders_to_run) * 5
cost_estimate = total_queries_estimate * 0.001
has_domain  = sum(1 for f in funders_to_run if f.get("domain"))
has_location = sum(1 for f in funders_to_run if f.get("city") and f.get("state"))

st.subheader("📋 Pre-flight Summary")
pf1, pf2, pf3, pf4, pf5 = st.columns(5)
pf1.metric("Funders",              len(funders_to_run))
pf2.metric("With Domain",          has_domain)
pf3.metric("With City/State",      has_location)
pf4.metric("Est. SerpApi Queries", f"~{total_queries_estimate:,}")
pf5.metric("Est. Cost",            f"~${cost_estimate:.2f}")

st.divider()

# ─── Start button ─────────────────────────────────────────────────────────────
if st.button("🚀 Start Experiment", type="primary", use_container_width=True,
             disabled=already_running):
    st.session_state["experiment_running"] = True
    st.session_state["experiment_done"]    = False
    st.session_state["experiment_results"] = {}

    overall_start    = time.time()
    credits_used     = 0
    all_funder_stats = []

    # ── Create Supabase session ────────────────────────────────────────────
    sb, _ = get_or_create_client()
    session_id = None
    if sb:
        from datetime import datetime, timezone
        session_id = create_session(
            sb,
            total_funders=len(funders_to_run),
            notes=f"Run at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        )
        if session_id:
            st.session_state["active_session_id"] = session_id

    progress_bar           = st.progress(0, text="Starting experiment...")
    status_placeholder     = st.empty()
    live_table_placeholder = st.empty()
    error_log_placeholder  = st.empty()

    serper_auth_failed = False

    for idx, funder in enumerate(funders_to_run):
        ein      = funder["ein"]
        org_name = funder["name"]

        progress = (idx + 1) / len(funders_to_run)
        progress_bar.progress(progress, text=f"[{idx+1}/{len(funders_to_run)}] {org_name[:50]}...")

        funder_start = time.time()
        api_errors   = []
        all_profiles = []
        seen_urls    = set()

        # ── SerpApi Discovery ──────────────────────────────────────────────
        serper_profiles = []
        queries = build_serp_queries(funder)

        if not serper_auth_failed:
            with status_placeholder.container():
                st.caption(f"🔍 [{idx+1}/{len(funders_to_run)}] SerpApi discovery: {org_name}")
            try:
                serper_result = run_discovery(
                    api_key=serpapi_key,
                    funder=funder,
                    queries=queries,
                )
                serper_profiles = serper_result.get("profiles", [])
                if serper_result.get("error"):
                    err = serper_result["error"]
                    api_errors.append({"step": "serper", "error": err})
                    if "AUTH_ERROR" in err:
                        serper_auth_failed = True
                        error_log_placeholder.error(
                            "⛔ SerpApi authentication failed — check your API key."
                        )
            except SerperAuthError as e:
                serper_auth_failed = True
                api_errors.append({"step": "serper", "error": str(e)})
                error_log_placeholder.error(f"⛔ SerpApi auth failed: {e}")
            except Exception as e:
                api_errors.append({"step": "serper", "error": f"UNEXPECTED: {str(e)}"})

        for p in serper_profiles:
            if is_excluded_title(p.get("current_title", "")):
                continue
            url = p.get("linkedin_url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_profiles.append(p)

        # ── Apollo People Search ───────────────────────────────────────────
        apollo_profiles = []
        if apollo_search_key:
            with status_placeholder.container():
                st.caption(f"👥 [{idx+1}/{len(funders_to_run)}] Apollo search: {org_name}")
            try:
                apollo_params = build_apollo_params(funder)
                apollo_result = search_people_by_company(
                    search_key=apollo_search_key,
                    apollo_params=apollo_params,
                    size=max(max_contacts * 3, 30),
                )
                apollo_profiles = apollo_result.get("profiles", [])
                if apollo_result.get("error"):
                    api_errors.append({"step": "apollo_search", "error": apollo_result["error"]})
            except Exception as e:
                api_errors.append({"step": "apollo_search", "error": f"UNEXPECTED: {str(e)}"})

        for p in apollo_profiles:
            if is_excluded_title(p.get("current_title", "")):
                continue
            url = p.get("linkedin_url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_profiles.append(p)
            elif not url:
                all_profiles.append(p)

        # ── Apollo Enrichment ──────────────────────────────────────────────
        enrichments_done = 0
        if enrich_enabled and apollo_match_key and credits_used < enrich_budget:
            enrich_candidates = [
                p for p in all_profiles if p.get("linkedin_url") and not p.get("enriched")
            ]
            for p in enrich_candidates[:max_contacts]:
                if credits_used >= enrich_budget:
                    break
                with status_placeholder.container():
                    st.caption(f"⚡ [{idx+1}/{len(funders_to_run)}] Enriching: {p.get('person_name', '')}")

                enrich_res = enrich_person(apollo_match_key, p["linkedin_url"])
                if enrich_res.get("error"):
                    err_msg = enrich_res["error"]
                    api_errors.append({"step": "apollo_enrich", "error": err_msg})
                    if "AUTH_ERROR" in err_msg or "CREDITS_EXHAUSTED" in err_msg:
                        break
                elif enrich_res.get("found") and enrich_res.get("profile"):
                    enriched_profile = enrich_res["profile"]
                    url = p["linkedin_url"]
                    all_profiles = [enriched_profile if q.get("linkedin_url") == url else q
                                    for q in all_profiles]
                    enrichments_done += 1
                    credits_used += 1

                remaining = enrich_res.get("credits_remaining")
                if remaining is not None and remaining < 10:
                    st.warning(f"⚠️ Apollo credits low: {remaining} remaining")

        # ── Cap contacts ───────────────────────────────────────────────────
        all_profiles = all_profiles[:max_contacts]

        # ── Build result ───────────────────────────────────────────────────
        discovered_count = len(all_profiles)
        grant_rel_count  = sum(1 for p in all_profiles if p.get("is_grant_relevant"))
        processing_ms    = int((time.time() - funder_start) * 1000)

        funder_stat = {
            "ein":                   ein,
            "org_name":              org_name,
            "segment":               funder.get("segment"),
            "city":                  funder.get("city"),
            "state":                 funder.get("state"),
            "domain":                funder.get("domain"),
            "discovered_count":      discovered_count,
            "grant_relevant_count":  grant_rel_count,
            "serper_queries_run":    len(queries),
            "serper_urls_found":     len(serper_profiles),
            "apollo_profiles_found": len(apollo_profiles),
            "enrichments_done":      enrichments_done,
            "api_errors":            api_errors,
            "contacts":              all_profiles,
            "processing_ms":         processing_ms,
        }

        st.session_state["experiment_results"][ein] = funder_stat
        all_funder_stats.append(funder_stat)

        # ── Save to Supabase ───────────────────────────────────────────────
        if sb and session_id:
            save_funder_result(sb, session_id, funder_stat)
            save_contacts(sb, session_id, ein, org_name, all_profiles)

        # ── Live table ─────────────────────────────────────────────────────
        if all_funder_stats:
            preview_df = pd.DataFrame([
                {
                    "Org":          r["org_name"][:40],
                    "Segment":      r["segment"],
                    "Discovered":   r["discovered_count"],
                    "🎯 Grant Rel": r["grant_relevant_count"],
                    "Serper":       r["serper_urls_found"],
                    "Apollo":       r["apollo_profiles_found"],
                    "Enriched":     r["enrichments_done"],
                    "Errors":       len(r["api_errors"]),
                }
                for r in all_funder_stats[-15:]
            ])
            live_table_placeholder.dataframe(preview_df, use_container_width=True, height=350)

    # ── Done ──────────────────────────────────────────────────────────────
    progress_bar.progress(1.0, text="✅ Experiment complete!")
    st.session_state["experiment_running"] = False
    st.session_state["experiment_done"]    = True

    if sb and session_id:
        complete_session(sb, session_id, len(all_funder_stats))

    total_elapsed = time.time() - overall_start
    status_placeholder.empty()

    metrics = compute_metrics(all_funder_stats)
    st.divider()
    st.subheader("🏁 Experiment Complete")

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Funders Processed",   len(all_funder_stats))
    m2.metric("Total Discovered",    metrics["totals"]["discovered"])
    m3.metric("Grant-Relevant",      metrics["totals"]["grant_relevant"])
    m4.metric("Discovery Rate",      f"{metrics['discovery_rate']:.1f}%")
    m5.metric("Time",                f"{total_elapsed:.0f}s")

    st.info("Go to **📋 Results** to explore per-funder contacts, or **📈 Metrics** for the dashboard.")

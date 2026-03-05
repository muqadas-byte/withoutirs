"""
app.py — Staff Intelligence R&D Experiment
Home page + configuration + Supabase setup
"""
import streamlit as st
import json
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from utils.supabase_client import try_connect, get_schema_sql, get_or_create_client

st.set_page_config(
    page_title="Staff Intel R&D Experiment",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Session state defaults ───────────────────────────────────────────────────
def _init_state():
    defaults = {
        "funders": [],            # parsed funder list
        "funders_loaded": False,
        "serpapi_key": "",
        "apollo_search_key": "",  # People Search key  (api/v1/mixed_people/api_search)
        "apollo_match_key": "",   # People Match + Enrichment key
        "supabase_url": "https://iukogdcsckxfpxwswiny.supabase.co",
        "supabase_key": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Iml1a29nZGNzY2t4ZnB4d3N3aW55Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzI2ODE3MzUsImV4cCI6MjA4ODI1NzczNX0.G501jm-whAvjqrK6K5R59pPBTLfNKtFUsz34HQRh_6A",
        "supabase_client": None,
        "supabase_ok": False,
        "active_session_id": None,
        "experiment_results": {},  # ein -> result dict
        "experiment_running": False,
        "experiment_done": False,
        "max_funders": 100,
        "enrich_enabled": True,
        "enrich_budget": 100,
        "max_contacts_per_funder": 10,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()

# ─── Load API keys from secrets if available ─────────────────────────────────
def _load_from_secrets():
    try:
        if st.secrets.get("SERPAPI_KEY") and not st.session_state["serpapi_key"]:
            st.session_state["serpapi_key"] = st.secrets["SERPAPI_KEY"]
        if st.secrets.get("APOLLO_SEARCH_KEY") and not st.session_state["apollo_search_key"]:
            st.session_state["apollo_search_key"] = st.secrets["APOLLO_SEARCH_KEY"]
        if st.secrets.get("APOLLO_MATCH_KEY") and not st.session_state["apollo_match_key"]:
            st.session_state["apollo_match_key"] = st.secrets["APOLLO_MATCH_KEY"]
        if st.secrets.get("SUPABASE_URL") and not st.session_state["supabase_url"]:
            st.session_state["supabase_url"] = st.secrets["SUPABASE_URL"]
        if st.secrets.get("SUPABASE_ANON_KEY") and not st.session_state["supabase_key"]:
            st.session_state["supabase_key"] = st.secrets["SUPABASE_ANON_KEY"]
    except Exception:
        pass

_load_from_secrets()

# ─── Auto-connect to Supabase from secrets or session state ──────────────────
# Auto-connect to Supabase on every page load
_sb, _sb_err = get_or_create_client()
if _sb:
    st.session_state["supabase_client"] = _sb
    st.session_state["supabase_ok"] = True

# ─── Page header ─────────────────────────────────────────────────────────────
st.title("🔬 Staff Intelligence R&D Experiment")
st.caption("100-Funder Validation · SerpApi Discovery + Apollo Match & Enrichment")

# ─── Status banner ───────────────────────────────────────────────────────────
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    if st.session_state["funders_loaded"]:
        n = len(st.session_state["funders"])
        st.success(f"📁 {n} funders loaded")
    else:
        st.warning("📁 No funders loaded")

with col2:
    if st.session_state["serpapi_key"]:
        st.success("🔍 SerpApi key set")
    else:
        st.error("🔍 SerpApi key missing")

with col3:
    if st.session_state["apollo_search_key"]:
        st.success("🔎 Apollo Search key set")
    else:
        st.warning("🔎 Apollo Search key missing")

with col4:
    if st.session_state["apollo_match_key"]:
        st.success("👥 Apollo Match key set")
    else:
        st.error("👥 Apollo Match key missing")

with col5:
    if st.session_state["supabase_ok"]:
        st.success("🗄️ Supabase connected")
    elif st.session_state["supabase_url"]:
        st.warning("🗄️ Supabase not verified")
    else:
        st.info("🗄️ Supabase not configured")

st.divider()

# ─── Two-column layout ────────────────────────────────────────────────────────
left, right = st.columns([1, 1])

# ── Left: Load Funders JSON ───────────────────────────────────────────────────
with left:
    st.subheader("📁 Load Funders Data")
    uploaded = st.file_uploader(
        "Upload 100randomFunders.json",
        type=["json"],
        help="The 100-funder sample JSON from your Grant Assistant dataset",
    )

    if uploaded:
        try:
            raw = json.load(uploaded)
            from utils.data_loader import extract_all_funders
            funders = extract_all_funders(raw)
            st.session_state["funders"] = funders
            st.session_state["funders_loaded"] = True
            st.success(f"Loaded {len(funders)} funders successfully")

            # Show quick breakdown
            has_website  = sum(1 for f in funders if f.get("website"))
            has_domain   = sum(1 for f in funders if f.get("domain"))
            has_location = sum(1 for f in funders if f.get("city") and f.get("state"))

            st.caption(
                f"With website: {has_website} | "
                f"Domain extractable: {has_domain} | "
                f"Has city+state: {has_location}"
            )
        except Exception as e:
            st.error(f"Failed to parse JSON: {e}")

# ── Right: API Configuration ──────────────────────────────────────────────────
with right:
    st.subheader("🔑 API Keys")

    serpapi_input = st.text_input(
        "SerpApi Key",
        value=st.session_state["serpapi_key"],
        type="password",
        placeholder="your-serpapi-key-here",
    )
    if serpapi_input:
        st.session_state["serpapi_key"] = serpapi_input

    st.caption("Apollo.io — two keys required for the full pipeline")

    search_input = st.text_input(
        "Apollo People Search Key",
        value=st.session_state["apollo_search_key"],
        type="password",
        placeholder="uXfyGdlN... (mixed_people/api_search)",
    )
    if search_input:
        st.session_state["apollo_search_key"] = search_input

    match_input = st.text_input(
        "Apollo Match + Enrich Key",
        value=st.session_state["apollo_match_key"],
        type="password",
        placeholder="LYtIrKl3... (people/match + enrichment)",
    )
    if match_input:
        st.session_state["apollo_match_key"] = match_input

    st.divider()
    st.subheader("🗄️ Supabase")

    sb_url = st.text_input(
        "Supabase Project URL",
        value=st.session_state["supabase_url"],
        placeholder="https://xxxx.supabase.co",
    )
    if sb_url:
        st.session_state["supabase_url"] = sb_url

    sb_key = st.text_input(
        "Supabase Anon Key",
        value=st.session_state["supabase_key"],
        type="password",
        placeholder="eyJhbGciOi...",
    )
    if sb_key:
        st.session_state["supabase_key"] = sb_key

    if st.button("🔌 Test Supabase Connection", use_container_width=True):
        with st.spinner("Connecting..."):
            client, error = try_connect(
                st.session_state["supabase_url"],
                st.session_state["supabase_key"],
            )
        if client:
            st.session_state["supabase_client"] = client
            st.session_state["supabase_ok"] = True
            st.success("Connected to Supabase!")
        else:
            st.session_state["supabase_ok"] = False
            st.error(f"Connection failed: {error}")

st.divider()

# ─── Supabase Schema Setup ────────────────────────────────────────────────────
with st.expander("📋 Supabase Schema Setup — Run this SQL in your Supabase SQL editor"):
    st.caption("Copy and run this in your Supabase project > SQL Editor to create the required tables.")
    st.code(get_schema_sql(), language="sql")

# ─── Experiment Settings ─────────────────────────────────────────────────────
st.subheader("⚙️ Experiment Settings")

s1, s2, s3 = st.columns(3)
with s1:
    max_funders = st.number_input(
        "Max Funders to Process",
        min_value=1, max_value=100,
        value=st.session_state["max_funders"],
        help="Set < 100 for a quick test run",
    )
    st.session_state["max_funders"] = int(max_funders)

with s2:
    max_contacts = st.number_input(
        "Max Contacts per Funder",
        min_value=1, max_value=50,
        value=st.session_state["max_contacts_per_funder"],
        help="Cap on LinkedIn profiles to collect per org",
    )
    st.session_state["max_contacts_per_funder"] = int(max_contacts)

with s3:
    enrich = st.toggle(
        "Enable Apollo Enrichment",
        value=st.session_state["enrich_enabled"],
        help="Uses 1 Apollo credit per discovered profile. Disable to test discovery only.",
    )
    st.session_state["enrich_enabled"] = enrich
    if enrich:
        budget = st.number_input(
            "Max Enrichment Credits",
            min_value=1, max_value=500,
            value=st.session_state["enrich_budget"],
            help="Hard cap on Apollo credits consumed this run",
        )
        st.session_state["enrich_budget"] = int(budget)

st.divider()
st.info(
    "**Next step:** Go to **🔬 Run Experiment** in the sidebar to start the pipeline. "
    "Check **📊 Overview** first to explore your funder sample."
)

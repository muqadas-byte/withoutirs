"""
utils/supabase_client.py
Supabase client with helpers for experiment persistence.
"""
import streamlit as st

SUPABASE_URL = "https://iukogdcsckxfpxwswiny.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Iml1a29nZGNzY2t4ZnB4d3N3aW55Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzI2ODE3MzUsImV4cCI6MjA4ODI1NzczNX0.G501jm-whAvjqrK6K5R59pPBTLfNKtFUsz34HQRh_6A"


def try_connect(url=None, key=None):
    try:
        from supabase import create_client
        client = create_client(url or SUPABASE_URL, key or SUPABASE_KEY)
        client.table("experiment_sessions").select("id").limit(1).execute()
        return client, None
    except Exception as e:
        return None, str(e)


def get_or_create_client():
    if st.session_state.get("supabase_client") and st.session_state.get("supabase_ok"):
        return st.session_state["supabase_client"], None
    client, error = try_connect()
    if client:
        st.session_state["supabase_client"] = client
        st.session_state["supabase_ok"] = True
    return client, error


def get_schema_sql():
    return """
CREATE TABLE IF NOT EXISTS experiment_sessions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  started_at      TIMESTAMPTZ DEFAULT NOW(),
  completed_at    TIMESTAMPTZ,
  status          TEXT DEFAULT 'running',
  total_funders   INTEGER DEFAULT 0,
  funders_done    INTEGER DEFAULT 0,
  notes           TEXT,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS funder_results (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id            UUID REFERENCES experiment_sessions(id) ON DELETE CASCADE,
  ein                   TEXT NOT NULL,
  org_name              TEXT,
  segment               TEXT,
  city                  TEXT,
  state                 TEXT,
  domain                TEXT,
  discovered_count      INTEGER DEFAULT 0,
  grant_relevant_count  INTEGER DEFAULT 0,
  serper_queries_run    INTEGER DEFAULT 0,
  serper_urls_found     INTEGER DEFAULT 0,
  apollo_profiles_found INTEGER DEFAULT 0,
  enrichments_done      INTEGER DEFAULT 0,
  api_errors            JSONB DEFAULT '[]',
  processing_ms         INTEGER,
  created_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS contacts (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id        UUID REFERENCES experiment_sessions(id) ON DELETE CASCADE,
  ein               TEXT NOT NULL,
  org_name          TEXT,
  person_name       TEXT,
  current_title     TEXT,
  current_company   TEXT,
  linkedin_url      TEXT,
  photo_url         TEXT,
  source            TEXT,
  enriched          BOOLEAN DEFAULT FALSE,
  is_grant_relevant BOOLEAN DEFAULT FALSE,
  created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_funder_results_session ON funder_results(session_id);
CREATE INDEX IF NOT EXISTS idx_contacts_session ON contacts(session_id);
CREATE INDEX IF NOT EXISTS idx_contacts_ein ON contacts(ein);
"""


def create_session(sb, total_funders: int, notes: str = ""):
    try:
        res = sb.table("experiment_sessions").insert({
            "status": "running",
            "total_funders": total_funders,
            "funders_done": 0,
            "notes": notes,
        }).execute()
        return res.data[0]["id"]
    except Exception as e:
        print(f"create_session error: {e}")
        return None


def complete_session(sb, session_id: str, funders_done: int):
    try:
        from datetime import datetime, timezone
        sb.table("experiment_sessions").update({
            "status": "completed",
            "funders_done": funders_done,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", session_id).execute()
    except Exception as e:
        print(f"complete_session error: {e}")


def save_funder_result(sb, session_id: str, funder_stat: dict):
    try:
        sb.table("funder_results").insert({
            "session_id":            session_id,
            "ein":                   funder_stat.get("ein"),
            "org_name":              funder_stat.get("org_name"),
            "segment":               funder_stat.get("segment"),
            "city":                  funder_stat.get("city"),
            "state":                 funder_stat.get("state"),
            "domain":                funder_stat.get("domain"),
            "discovered_count":      funder_stat.get("discovered_count", 0),
            "grant_relevant_count":  funder_stat.get("grant_relevant_count", 0),
            "serper_queries_run":    funder_stat.get("serper_queries_run", 0),
            "serper_urls_found":     funder_stat.get("serper_urls_found", 0),
            "apollo_profiles_found": funder_stat.get("apollo_profiles_found", 0),
            "enrichments_done":      funder_stat.get("enrichments_done", 0),
            "api_errors":            funder_stat.get("api_errors", []),
            "processing_ms":         funder_stat.get("processing_ms"),
        }).execute()
    except Exception as e:
        print(f"save_funder_result error: {e}")


def save_contacts(sb, session_id: str, ein: str, org_name: str, contacts: list):
    if not contacts:
        return
    try:
        rows = [{
            "session_id":        session_id,
            "ein":               ein,
            "org_name":          org_name,
            "person_name":       p.get("person_name"),
            "current_title":     p.get("current_title"),
            "current_company":   p.get("current_company"),
            "linkedin_url":      p.get("linkedin_url"),
            "photo_url":         p.get("photo_url"),
            "source":            p.get("source"),
            "enriched":          p.get("enriched", False),
            "is_grant_relevant": p.get("is_grant_relevant", False),
        } for p in contacts]
        sb.table("contacts").insert(rows).execute()
    except Exception as e:
        print(f"save_contacts error: {e}")


def load_all_sessions(sb) -> list:
    try:
        res = sb.table("experiment_sessions") \
            .select("*").order("started_at", desc=True).execute()
        return res.data or []
    except Exception as e:
        print(f"load_all_sessions error: {e}")
        return []


def load_funder_results(sb, session_id: str) -> list:
    try:
        res = sb.table("funder_results") \
            .select("*").eq("session_id", session_id).order("created_at").execute()
        return res.data or []
    except Exception as e:
        print(f"load_funder_results error: {e}")
        return []


def load_contacts(sb, session_id: str, ein: str = None) -> list:
    try:
        q = sb.table("contacts").select("*").eq("session_id", session_id)
        if ein:
            q = q.eq("ein", ein)
        return q.execute().data or []
    except Exception as e:
        print(f"load_contacts error: {e}")
        return []


def auto_restore_session(sb):
    return None, {}

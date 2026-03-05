"""
pages/4_📈_Metrics.py
Discovery experiment metrics dashboard.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import pandas as pd
import plotly.express as px

from utils.metrics_calc import compute_metrics

st.set_page_config(page_title="Metrics Dashboard", page_icon="📈", layout="wide")
st.title("📈 Metrics Dashboard")
st.caption("Discovery experiment results")

results = st.session_state.get("experiment_results", {})
if not results:
    st.info("No results yet. Run the experiment first.")
    st.stop()

funder_stats = list(results.values())
metrics      = compute_metrics(funder_stats)
totals       = metrics["totals"]

# ─── Top metrics ─────────────────────────────────────────────────────────────
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Funders Processed",    totals["funders"])
m2.metric("Total Discovered",     totals["discovered"])
m3.metric("Grant-Relevant",       totals["grant_relevant"])
m4.metric("Discovery Rate",       f"{metrics['discovery_rate']:.1f}%",
          help="% of funders where ≥1 contact was found")
m5.metric("Avg Contacts / Funder", metrics["avg_discovered_per_funder"])

st.divider()

m6, m7, m8 = st.columns(3)
m6.metric("Grant-Relevant Rate",  f"{metrics['grant_relevant_rate']:.1f}%",
          help="% of discovered contacts in grant-relevant roles")
m7.metric("SerpApi Cost",         f"${metrics['total_serper_cost']:.3f}")
m8.metric("Cost / Funder",        f"${metrics['cost_per_funder']:.4f}")

st.divider()

# ─── Charts ───────────────────────────────────────────────────────────────────
chart1, chart2 = st.columns(2)

with chart1:
    st.subheader("Avg Contacts per Funder by Segment")
    seg = metrics["segment_breakdown"]
    if seg:
        seg_df = pd.DataFrame([
            {"Segment": k.title(), "Avg Contacts": v["avg_discovered"], "Funders": v["count"]}
            for k, v in seg.items()
        ])
        fig = px.bar(
            seg_df, x="Segment", y="Avg Contacts",
            text="Avg Contacts",
            color="Segment",
            color_discrete_sequence=["#4F46E5", "#7C3AED", "#A78BFA", "#6B7280"],
        )
        fig.update_traces(texttemplate="%{text:.1f}", textposition="outside")
        fig.update_layout(showlegend=False, paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor="rgba(0,0,0,0)", height=320)
        st.plotly_chart(fig, use_container_width=True)

with chart2:
    st.subheader("Contacts per Funder Distribution")
    discovered_vals = [r.get("discovered_count", 0) for r in funder_stats]
    fig2 = px.histogram(
        x=discovered_vals, nbins=15,
        labels={"x": "Contacts Discovered"},
        color_discrete_sequence=["#4F46E5"],
    )
    fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)",
                       plot_bgcolor="rgba(0,0,0,0)", height=320)
    st.plotly_chart(fig2, use_container_width=True)

# ─── Per-funder bar chart ─────────────────────────────────────────────────────
st.subheader("Contacts Discovered per Funder")
scatter_data = pd.DataFrame([
    {
        "Organization": r.get("org_name", "")[:40],
        "Contacts":     r.get("discovered_count", 0),
        "Grant Rel":    r.get("grant_relevant_count", 0),
        "Segment":      r.get("segment", "unknown"),
    }
    for r in funder_stats
]).sort_values("Contacts", ascending=True)

fig3 = px.bar(
    scatter_data, x="Contacts", y="Organization",
    color="Segment", orientation="h",
    hover_data=["Grant Rel"],
    color_discrete_map={
        "large": "#4F46E5", "mid": "#7C3AED",
        "small": "#A78BFA", "unknown": "#6B7280",
    },
    height=max(400, len(scatter_data) * 22),
)
fig3.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                   yaxis=dict(tickfont=dict(size=10)))
st.plotly_chart(fig3, use_container_width=True)

# ─── Zero-result funders ──────────────────────────────────────────────────────
zero = metrics["funders_with_zero_results"]
if zero:
    st.warning(f"⚠️ {zero} funders returned zero contacts. See **Edge Cases** for details.")

# ─── CSV export ───────────────────────────────────────────────────────────────
export = pd.DataFrame([
    {
        "org_name": r.get("org_name"), "ein": r.get("ein"),
        "segment": r.get("segment"), "discovered": r.get("discovered_count"),
        "grant_relevant": r.get("grant_relevant_count"),
        "serper_queries": r.get("serper_queries_run"),
        "apollo_found": r.get("apollo_profiles_found"),
        "enriched": r.get("enrichments_done"),
        "errors": len(r.get("api_errors") or []),
    }
    for r in funder_stats
])
st.download_button(
    "📥 Download experiment_metrics.csv",
    data=export.to_csv(index=False),
    file_name="experiment_metrics.csv",
    mime="text/csv",
)

"""
pages/1_📊_Overview.py
Explore the 100 funder sample before running the experiment.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Sample Overview", page_icon="📊", layout="wide")
st.title("📊 Sample Overview")
st.caption("Explore the 100 funders before running the experiment")

if not st.session_state.get("funders_loaded"):
    st.warning("No funders loaded. Go to the **Home** page and upload 100randomFunders.json first.")
    st.stop()

funders = st.session_state["funders"]
df = pd.DataFrame(funders)

# ─── Summary cards ────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total Funders",   len(df))
c2.metric("With Domain",     int(df["domain"].notna().sum()))
c3.metric("With Location",   int((df["city"].notna() & df["state"].notna()).sum()))
c4.metric("With Website",    int(df["website"].notna().sum()))
c5.metric("Large Funders",   int((df["segment"] == "large").sum()))

st.divider()

# ─── Charts ───────────────────────────────────────────────────────────────────
chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    st.subheader("Asset Segment Distribution")
    seg_counts = df["segment"].value_counts().reset_index()
    seg_counts.columns = ["Segment", "Count"]
    fig = px.bar(
        seg_counts, x="Segment", y="Count",
        color="Segment",
        color_discrete_map={
            "large": "#4F46E5", "mid": "#7C3AED",
            "small": "#A78BFA", "unknown": "#6B7280",
        },
        text="Count",
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(showlegend=False, plot_bgcolor="rgba(0,0,0,0)",
                      paper_bgcolor="rgba(0,0,0,0)", height=300)
    st.plotly_chart(fig, use_container_width=True)

with chart_col2:
    st.subheader("Total Assets Distribution")
    assets = df[df["financials"].apply(lambda x: bool(x.get("total_assets") if isinstance(x, dict) else False))]
    if not assets.empty:
        asset_vals = assets["financials"].apply(lambda x: x.get("total_assets", 0) if isinstance(x, dict) else 0)
        fig2 = px.histogram(
            x=asset_vals, nbins=20,
            labels={"x": "Total Assets ($)"},
            color_discrete_sequence=["#4F46E5"],
        )
        fig2.update_layout(plot_bgcolor="rgba(0,0,0,0)",
                           paper_bgcolor="rgba(0,0,0,0)", height=300)
        st.plotly_chart(fig2, use_container_width=True)

# ─── State coverage ───────────────────────────────────────────────────────────
st.subheader("Geographic Coverage")
state_counts = df[df["state"].notna()]["state"].value_counts().reset_index()
state_counts.columns = ["state", "count"]
if not state_counts.empty:
    fig3 = px.choropleth(
        state_counts,
        locations="state",
        locationmode="USA-states",
        color="count",
        scope="usa",
        color_continuous_scale="Purples",
        labels={"count": "Funders"},
    )
    fig3.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        geo_bgcolor="rgba(0,0,0,0)",
        height=380,
        margin=dict(t=0, b=0, l=0, r=0),
    )
    st.plotly_chart(fig3, use_container_width=True)

# ─── Funder table ─────────────────────────────────────────────────────────────
st.subheader("Funder Details")

f1, f2, f3 = st.columns(3)
with f1:
    seg_filter = st.multiselect(
        "Filter by Segment",
        options=["large", "mid", "small", "unknown"],
        default=["large", "mid", "small", "unknown"],
    )
with f2:
    domain_only = st.checkbox("Only funders with domain")
with f3:
    search_term = st.text_input("Search by name or EIN", placeholder="Maine Education...")

filtered = df[df["segment"].isin(seg_filter)]
if domain_only:
    filtered = filtered[filtered["domain"].notna()]
if search_term:
    mask = (
        filtered["name"].str.contains(search_term, case=False, na=False) |
        filtered["ein"].str.contains(search_term, case=False, na=False)
    )
    filtered = filtered[mask]

display_df = filtered[["ein", "name", "city", "state", "segment", "domain", "website"]].copy()
display_df["total_assets"] = filtered["financials"].apply(
    lambda x: f"${x.get('total_assets', 0):,.0f}" if isinstance(x, dict) and x.get("total_assets") else "—"
)
display_df.columns = ["EIN", "Organization", "City", "State", "Segment", "Domain", "Website", "Total Assets"]
st.dataframe(display_df, use_container_width=True, height=450)
st.caption(f"Showing {len(filtered)} of {len(df)} funders")

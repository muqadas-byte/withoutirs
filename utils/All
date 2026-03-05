"""
utils/metrics_calc.py
Simplified metrics for org-discovery mode (no IRS cross-referencing).
"""


def compute_metrics(funder_stats: list[dict]) -> dict:
    """
    Compute summary metrics from a list of per-funder result dicts.
    All metrics are discovery-focused — no IRS match rates.
    """
    if not funder_stats:
        return _empty_metrics()

    total_funders     = len(funder_stats)
    total_discovered  = sum(r.get("discovered_count", 0) for r in funder_stats)
    total_grant_rel   = sum(r.get("grant_relevant_count", 0) for r in funder_stats)
    total_queries     = sum(r.get("serper_queries_run", 0) for r in funder_stats)
    total_enrichments = sum(r.get("enrichments_done", 0) for r in funder_stats)
    total_errors      = sum(len(r.get("api_errors") or []) for r in funder_stats)
    funders_with_any  = sum(1 for r in funder_stats if r.get("discovered_count", 0) > 0)
    funders_with_zero = total_funders - funders_with_any

    avg_discovered = total_discovered / total_funders if total_funders else 0
    discovery_rate = (funders_with_any / total_funders * 100) if total_funders else 0
    grant_rel_rate = (total_grant_rel / total_discovered * 100) if total_discovered else 0

    # Cost estimate: SerpApi ~$0.001 per query (default plan)
    serper_cost   = total_queries * 0.001
    cost_per_funder = serper_cost / total_funders if total_funders else 0

    # Segment breakdown
    segment_breakdown = {}
    for r in funder_stats:
        seg = r.get("segment", "unknown") or "unknown"
        if seg not in segment_breakdown:
            segment_breakdown[seg] = {"count": 0, "discovered": 0, "grant_relevant": 0}
        segment_breakdown[seg]["count"] += 1
        segment_breakdown[seg]["discovered"] += r.get("discovered_count", 0)
        segment_breakdown[seg]["grant_relevant"] += r.get("grant_relevant_count", 0)

    for seg, v in segment_breakdown.items():
        v["avg_discovered"] = round(v["discovered"] / v["count"], 1) if v["count"] else 0

    return {
        "totals": {
            "funders":      total_funders,
            "discovered":   total_discovered,
            "grant_relevant": total_grant_rel,
            "queries_run":  total_queries,
            "enrichments":  total_enrichments,
            "errors":       total_errors,
        },
        "avg_discovered_per_funder":  round(avg_discovered, 1),
        "discovery_rate":             round(discovery_rate, 1),   # % funders with ≥1 contact
        "grant_relevant_rate":        round(grant_rel_rate, 1),   # % of discovered who are grant-relevant
        "total_serper_cost":          round(serper_cost, 4),
        "cost_per_funder":            round(cost_per_funder, 4),
        "funders_with_zero_results":  funders_with_zero,
        "segment_breakdown":          segment_breakdown,
    }


def _empty_metrics() -> dict:
    return {
        "totals": {
            "funders": 0, "discovered": 0, "grant_relevant": 0,
            "queries_run": 0, "enrichments": 0, "errors": 0,
        },
        "avg_discovered_per_funder": 0,
        "discovery_rate": 0,
        "grant_relevant_rate": 0,
        "total_serper_cost": 0,
        "cost_per_funder": 0,
        "funders_with_zero_results": 0,
        "segment_breakdown": {},
    }

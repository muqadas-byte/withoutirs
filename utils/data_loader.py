"""
utils/data_loader.py
Extract org-level information from the funders JSON for use in
SerpApi/Apollo discovery queries.

No IRS leadership data is used — contacts are discovered entirely
from org signals: name, domain, location, financials.
"""
import re
from urllib.parse import urlparse


def _extract_domain(website: str) -> str | None:
    """Pull a clean domain from a raw website string, or return None."""
    if not website or website.strip().upper() in ("N/A", "NONE", ""):
        return None
    url = website.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower().lstrip("www.")
        return domain if "." in domain else None
    except Exception:
        return None


def _parse_location(hq_address: str) -> tuple[str | None, str | None]:
    """
    Parse city and state from an IRS-style address string.
    Format is typically: "STREET, CITY, STATE, ZIP"
    Returns (city, state) or (None, None).
    """
    if not hq_address:
        return None, None
    parts = [p.strip() for p in hq_address.split(",")]
    # We need at least CITY, STATE, ZIP at the end
    if len(parts) >= 3:
        city  = parts[-3].title()
        state = parts[-2].strip().upper()
        # Sanity check: state should be a 2-letter code
        if re.match(r"^[A-Z]{2}$", state):
            return city, state
    return None, None


def _latest_financials(financial_breakdown: dict) -> dict:
    """
    Return the most recent year's financials from the financialBreakdown dict.
    Keys are year strings ("2020", "2021", etc.).
    """
    if not financial_breakdown or not isinstance(financial_breakdown, dict):
        return {}
    years = sorted(financial_breakdown.keys(), reverse=True)
    for year in years:
        fb = financial_breakdown[year]
        if isinstance(fb, dict) and fb.get("totalAssets"):
            return {
                "year":        fb.get("taxYear", year),
                "total_assets": _to_int(fb.get("totalAssets")),
                "total_giving": _to_int(fb.get("totalGiving")),
                "revenue":      _to_int(fb.get("revenue")),
                "expenses":     _to_int(fb.get("expenses")),
                "net_assets":   _to_int(fb.get("netAssets")),
            }
    return {}


def _to_int(val) -> int | None:
    try:
        return int(float(str(val).replace(",", "")))
    except (ValueError, TypeError):
        return None


def _segment_from_assets(total_assets: int | None) -> str:
    """Bucket funders by asset size."""
    if total_assets is None:
        return "unknown"
    if total_assets >= 10_000_000:
        return "large"
    if total_assets >= 1_000_000:
        return "mid"
    return "small"


def extract_funder(raw: dict) -> dict:
    """
    Convert a single raw funder document into a clean dict for the pipeline.

    Returned fields (no leadership):
      ein, name, slug, website, domain, hq_address, city, state,
      ntee_code, financials (latest year), segment, status, type
    """
    fo = raw.get("funderOverviewN8NOutput") or {}

    website    = fo.get("website") or raw.get("website") or ""
    hq_address = fo.get("hqAddress") or ""
    city, state = _parse_location(hq_address)
    domain      = _extract_domain(website)
    financials  = _latest_financials(raw.get("financialBreakdown") or {})
    segment     = _segment_from_assets(financials.get("total_assets"))

    return {
        "ein":        fo.get("ein") or raw.get("ein", ""),
        "name":       raw.get("name", "").strip(),
        "slug":       raw.get("slug", ""),
        "website":    website if website.upper() not in ("N/A", "") else None,
        "domain":     domain,
        "hq_address": hq_address,
        "city":       city,
        "state":      state,
        "ntee_code":  fo.get("nteeCode"),
        "financials": financials,
        "segment":    segment,
        "status":     raw.get("status"),
        "type":       raw.get("type"),
        # Grantee snapshots kept for context (useful for Apollo company matching)
        "grantee_snapshots": fo.get("granteeSnapshots") or [],
    }


def extract_all_funders(raw_list: list) -> list[dict]:
    """
    Parse the full 100randomFunders.json list.
    Returns a list of clean funder dicts ready for the pipeline.
    """
    funders = []
    for raw in raw_list:
        try:
            funders.append(extract_funder(raw))
        except Exception:
            pass  # skip malformed records silently
    return funders


# ─── Search query builders ────────────────────────────────────────────────────

def build_serp_queries(funder: dict) -> list[dict]:
    """
    Build SerpApi search queries from org-level data only.
    No individual names used — pure org-signal discovery.

    Returns a list of {"query": str, "type": str} dicts.
    """
    name    = funder.get("name", "")
    domain  = funder.get("domain")
    city    = funder.get("city")
    state   = funder.get("state")
    queries = []

    # 1. Broad LinkedIn people search by org name
    queries.append({
        "type":  "org_broad",
        "query": f'site:linkedin.com/in "{name}"',
    })

    # 2. Org name + location
    if city and state:
        queries.append({
            "type":  "org_location",
            "query": f'site:linkedin.com/in "{name}" "{city}" "{state}"',
        })

    # 3. Domain-based (catches staff who list org website on profile)
    if domain:
        queries.append({
            "type":  "domain",
            "query": f'site:linkedin.com/in "{domain}"',
        })

    # 4. Foundation + key roles
    queries.append({
        "type":  "org_roles",
        "query": f'site:linkedin.com/in "{name}" (director OR president OR "program officer" OR trustee OR executive)',
    })

    # 5. Google People search — surfaces LinkedIn cards in SERPs
    if city and state:
        queries.append({
            "type":  "people_serp",
            "query": f'"{name}" staff {city} {state} linkedin',
        })

    return queries


def build_apollo_params(funder: dict) -> dict:
    """
    Build Apollo People Search API parameters from org data.
    Uses company domain when available, falls back to org name.
    """
    params = {}

    if funder.get("domain"):
        params["organization_domains[]"] = funder["domain"]
    elif funder.get("name"):
        params["q_organization_name"] = funder["name"]

    if funder.get("city"):
        params["person_locations[]"] = (
            f"{funder['city']}, {funder['state']}"
            if funder.get("state")
            else funder["city"]
        )

    # Roles relevant to grant-making foundations
    params["person_titles[]"] = [
        "Executive Director",
        "President",
        "Director",
        "Program Officer",
        "Grants Manager",
        "Trustee",
        "Board Member",
        "Chief Executive Officer",
        "Vice President",
        "Program Manager",
    ]

    return params

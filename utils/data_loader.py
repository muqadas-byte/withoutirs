"""
utils/data_loader.py
Extract org-level information from the funders JSON for use in
SerpApi/Apollo discovery queries.

No IRS leadership data is used — contacts are discovered entirely
from org signals: name, domain, location, financials.
"""
import re
from urllib.parse import urlparse
from rapidfuzz import fuzz


_BLANK_WEBSITE = {"N/A", "NONE", ""}


def _coalesce_website(*candidates) -> str:
    """Return the first candidate that is not empty / N/A / NONE."""
    for v in candidates:
        if v and str(v).strip().upper() not in _BLANK_WEBSITE:
            return str(v).strip()
    return ""


def _extract_domain(website: str) -> str | None:
    """Pull a clean domain from a raw website string, or return None."""
    if not website or website.strip().upper() in _BLANK_WEBSITE:
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

    website    = _coalesce_website(
                     fo.get("website"),
                     raw.get("website"),
                     raw.get("sourceLink"),
                 )
    hq_address = fo.get("hqAddress") or ""
    city, state = _parse_location(hq_address)
    domain      = _extract_domain(website)
    financials  = _latest_financials(raw.get("financialBreakdown") or {})
    segment     = _segment_from_assets(financials.get("total_assets"))

    return {
        "ein":        fo.get("ein") or raw.get("ein", ""),
        "name":       raw.get("name", "").strip(),
        "slug":       raw.get("slug", ""),
        "website":    website or None,
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

    When domain is available the search is already scoped to that company,
    so no title or location filters are applied — we want every employee.
    When falling back to org name the search is fuzzier, so location is
    added to narrow results down.
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

    return params


# ─── Profile validation ───────────────────────────────────────────────────────

EXCLUDED_TITLE_KEYWORDS = {
    "intern", "internship", "volunteer", "volunteering",
    "fellow", "fellowship", "student", "apprentice",
}

_ORG_NOISE_WORDS = {
    "the", "of", "for", "and", "a", "an", "in", "at", "on",
    "inc", "incorporated", "llc", "ltd", "co", "corp", "corporation",
    "foundation", "fund", "trust", "charitable", "charity",
    "organization", "organisation", "society", "association",
    "institute", "center", "centre",
}


def _significant_words(name: str) -> set[str]:
    """Extract meaningful words from an org or person name, ignoring noise."""
    if not name:
        return set()
    words = re.findall(r"[a-z]+", name.lower())
    return {w for w in words if w not in _ORG_NOISE_WORDS and len(w) > 1}


def is_excluded_title(title: str) -> str | None:
    """Returns the exclusion reason if title should be excluded, else None."""
    if not title:
        return None
    t = title.lower()
    for kw in EXCLUDED_TITLE_KEYWORDS:
        if kw in t:
            return f"excluded_title:{kw}"
    return None


def company_matches_funder(
    profile_company: str, funder: dict, threshold: int = 60
) -> tuple[bool, int]:
    """
    Fuzzy-match a profile's current_company against the funder's name/domain.
    Returns (is_match, confidence_score).
    """
    if not profile_company:
        return False, 0

    funder_name = funder.get("name", "")
    if not funder_name:
        return False, 0

    score = fuzz.token_set_ratio(profile_company.lower(), funder_name.lower())
    if score >= threshold:
        return True, int(score)

    domain = funder.get("domain", "")
    if domain:
        company_squished = profile_company.lower().replace(" ", "").replace(".", "")
        domain_base = domain.split(".")[0].lower()
        if domain_base and len(domain_base) > 2 and domain_base in company_squished:
            return True, 75

    return False, int(score)


def is_name_collision(
    person_name: str, funder_name: str, company_matched: bool
) -> bool:
    """
    Detect when a person appears in results because their personal name
    overlaps with the funder name, not because they work there.
    e.g. searching "Smith Foundation" finds "John Smith" at "Acme Corp".
    """
    if company_matched:
        return False
    if not person_name or not funder_name:
        return False

    funder_words = _significant_words(funder_name)
    person_words = _significant_words(person_name)

    if not funder_words or not person_words:
        return False

    overlap = funder_words & person_words
    return len(overlap) > 0


def validate_profile(profile: dict, funder: dict) -> dict:
    """
    Run all validation checks on a single profile against a funder.
    Adds fields: company_match, company_match_score, excluded_reason, is_valid.

    Apollo-sourced profiles are trusted for company association (Apollo already
    searched by domain/org-name), so only title exclusion is applied.
    SerpApi-sourced profiles get full validation: company match, name collision,
    and title exclusion.
    """
    result = {**profile}
    source = profile.get("source", "")

    title = profile.get("current_title", "")
    title_exclusion = is_excluded_title(title)
    if title_exclusion:
        result["company_match"] = False
        result["company_match_score"] = 0
        result["excluded_reason"] = title_exclusion
        result["is_valid"] = False
        return result

    is_apollo = source in ("apollo_search", "apollo_enrich")

    company = profile.get("current_company", "")
    matched, score = company_matches_funder(company, funder)
    result["company_match"] = matched
    result["company_match_score"] = score

    if is_apollo:
        result["excluded_reason"] = None
        result["is_valid"] = True
        if not matched:
            result["company_match_score"] = max(score, 50)
        return result

    if not matched:
        person_name = profile.get("person_name", "")
        funder_name = funder.get("name", "")
        if is_name_collision(person_name, funder_name, matched):
            result["excluded_reason"] = "name_collision"
            result["is_valid"] = False
            return result

        result["excluded_reason"] = "company_mismatch"
        result["is_valid"] = False
        return result

    result["excluded_reason"] = None
    result["is_valid"] = True
    return result

"""
utils/serper_client.py
SerpApi discovery using org-level signals only (no IRS names).
Queries are built by data_loader.build_serp_queries().
"""
import requests
import re

SERP_ENDPOINT = "https://serpapi.com/search"

GRANT_RELEVANT_TITLES = {
    "executive director", "president", "ceo", "chief executive",
    "program officer", "grants manager", "grants director",
    "program director", "program manager", "trustee",
    "board member", "board chair", "vice president", "director of programs",
}


class SerperAuthError(Exception):
    pass


def _is_grant_relevant(title: str) -> bool:
    if not title:
        return False
    t = title.lower()
    return any(kw in t for kw in GRANT_RELEVANT_TITLES)


def _extract_linkedin_profiles_from_results(organic: list) -> list[dict]:
    """Parse SerpApi organic results for LinkedIn /in/ profile links."""
    profiles = []
    seen = set()
    for item in organic:
        link = item.get("link", "")
        if "linkedin.com/in/" not in link:
            continue
        # Normalise URL — strip query params
        clean_url = link.split("?")[0].rstrip("/")
        if clean_url in seen:
            continue
        seen.add(clean_url)

        # Try to pull name + title from the snippet / title
        title_text = item.get("title", "")
        snippet = item.get("snippet", "")

        # LinkedIn titles look like: "John Smith - Executive Director - Acme Foundation"
        parts = [p.strip() for p in title_text.split(" - ")]
        person_name = parts[0] if parts else ""
        current_title = parts[1] if len(parts) > 1 else ""
        current_company = parts[2] if len(parts) > 2 else ""

        profiles.append({
            "person_name": person_name,
            "current_title": current_title,
            "current_company": current_company,
            "linkedin_url": clean_url,
            "photo_url": None,
            "source": "serper",
            "enriched": False,
            "is_grant_relevant": _is_grant_relevant(current_title),
            "snippet": snippet,
        })
    return profiles


def run_discovery(
    api_key: str,
    funder: dict,
    queries: list[dict],
) -> dict:
    """
    Run all SerpApi queries for a funder and return discovered LinkedIn profiles.

    Args:
        api_key:  SerpApi key
        funder:   clean funder dict from data_loader.extract_funder()
        queries:  list of {"type": str, "query": str} from build_serp_queries()

    Returns:
        {
            "profiles": [...],
            "queries_run": int,
            "error": str | None,
        }
    """
    all_profiles = []
    seen_urls = set()
    queries_run = 0
    last_error = None

    for q in queries:
        try:
            resp = requests.get(
                SERP_ENDPOINT,
                params={
                    "api_key": api_key,
                    "q": q["query"],
                    "engine": "google",
                    "num": 10,
                    "hl": "en",
                    "gl": "us",
                },
                timeout=15,
            )
            queries_run += 1

            if resp.status_code == 401:
                raise SerperAuthError("AUTH_ERROR: Invalid SerpApi key")
            if resp.status_code == 429:
                last_error = "RATE_LIMIT: SerpApi rate limit hit"
                continue
            if resp.status_code != 200:
                last_error = f"HTTP_{resp.status_code}"
                continue

            data = resp.json()

            # Auth check in response body
            if data.get("error"):
                err = data["error"]
                if "Invalid API key" in err or "authentication" in err.lower():
                    raise SerperAuthError(f"AUTH_ERROR: {err}")
                last_error = err
                continue

            organic = data.get("organic_results", [])
            profiles = _extract_linkedin_profiles_from_results(organic)

            for p in profiles:
                url = p["linkedin_url"]
                if url not in seen_urls:
                    seen_urls.add(url)
                    p["query_type"] = q["type"]
                    all_profiles.append(p)

        except SerperAuthError:
            raise
        except requests.exceptions.Timeout:
            last_error = "TIMEOUT"
            continue
        except requests.exceptions.ConnectionError:
            last_error = "CONNECTION_ERROR"
            continue
        except Exception as e:
            last_error = f"UNEXPECTED: {str(e)}"
            continue

    return {
        "profiles": all_profiles,
        "queries_run": queries_run,
        "error": last_error,
    }

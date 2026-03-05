"""
utils/apollo_client.py
Apollo.io People Search (company-level) + People Match + Enrichment.
No IRS cross-referencing — pure org-signal discovery.
"""
import requests

APOLLO_SEARCH_URL  = "https://api.apollo.io/api/v1/mixed_people/api_search"
APOLLO_MATCH_URL   = "https://api.apollo.io/api/v1/people/match"

GRANT_RELEVANT_TITLES = {
    "executive director", "president", "ceo", "chief executive",
    "program officer", "grants manager", "grants director",
    "program director", "program manager", "trustee",
    "board member", "board chair", "vice president", "director of programs",
}


def _is_grant_relevant(title: str) -> bool:
    if not title:
        return False
    return any(kw in title.lower() for kw in GRANT_RELEVANT_TITLES)


def _parse_apollo_person(person: dict, source: str = "apollo_search") -> dict:
    linkedin = person.get("linkedin_url") or ""
    if linkedin and not linkedin.startswith("http"):
        linkedin = "https://www." + linkedin.lstrip("/")

    title = (
        person.get("title")
        or (person.get("employment_history") or [{}])[0].get("title", "")
    )
    company = (
        person.get("organization", {}).get("name")
        or person.get("organization_name")
        or ""
    )

    return {
        "person_name":      f"{person.get('first_name', '')} {person.get('last_name', '')}".strip(),
        "current_title":    title,
        "current_company":  company,
        "linkedin_url":     linkedin,
        "photo_url":        person.get("photo_url"),
        "apollo_person_id": person.get("id"),
        "source":           source,
        "enriched":         source == "apollo_enrich",
        "is_grant_relevant": _is_grant_relevant(title),
        "city":             person.get("city"),
        "state":            person.get("state"),
        "email":            person.get("email"),
    }


def search_people_by_company(
    search_key: str,
    apollo_params: dict,
    size: int = 10,
) -> dict:
    """
    Apollo People Search — org-level company search.
    apollo_params comes from data_loader.build_apollo_params().

    Returns:
        {"profiles": [...], "total_found": int, "error": str | None}
    """
    payload = {**apollo_params, "page": 1, "per_page": size}

    try:
        resp = requests.post(
            APOLLO_SEARCH_URL,
            headers={
                "x-api-key": search_key,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=20,
        )

        if resp.status_code == 401:
            return {"profiles": [], "total_found": 0, "error": "AUTH_ERROR: Invalid Apollo Search key"}
        if resp.status_code == 422:
            return {"profiles": [], "total_found": 0, "error": f"VALIDATION_ERROR: {resp.text[:200]}"}
        if resp.status_code != 200:
            return {"profiles": [], "total_found": 0, "error": f"HTTP_{resp.status_code}"}

        data = resp.json()
        people = data.get("people") or []
        total  = data.get("pagination", {}).get("total_entries", len(people))

        profiles = [_parse_apollo_person(p, source="apollo_search") for p in people]
        # Filter out profiles without a LinkedIn URL (less useful for discovery)
        profiles = [p for p in profiles if p["linkedin_url"]]

        return {"profiles": profiles, "total_found": total, "error": None}

    except requests.exceptions.Timeout:
        return {"profiles": [], "total_found": 0, "error": "TIMEOUT"}
    except requests.exceptions.ConnectionError:
        return {"profiles": [], "total_found": 0, "error": "CONNECTION_ERROR"}
    except Exception as e:
        return {"profiles": [], "total_found": 0, "error": f"UNEXPECTED: {str(e)}"}


def enrich_person(match_key: str, linkedin_url: str) -> dict:
    """
    Apollo People Match + implicit enrichment.
    Looks up a LinkedIn URL and returns full profile data.

    Returns:
        {"found": bool, "profile": dict | None, "credits_remaining": int | None, "error": str | None}
    """
    try:
        resp = requests.post(
            APOLLO_MATCH_URL,
            headers={
                "x-api-key": match_key,
                "Content-Type": "application/json",
            },
            json={
                "linkedin_url": linkedin_url,
                "reveal_personal_emails": False,
                "reveal_phone_number": False,
            },
            timeout=20,
        )

        if resp.status_code == 401:
            return {"found": False, "profile": None, "credits_remaining": None,
                    "error": "AUTH_ERROR: Invalid Apollo Match key"}
        if resp.status_code == 429:
            return {"found": False, "profile": None, "credits_remaining": 0,
                    "error": "CREDITS_EXHAUSTED"}
        if resp.status_code != 200:
            return {"found": False, "profile": None, "credits_remaining": None,
                    "error": f"HTTP_{resp.status_code}"}

        data = resp.json()
        person = data.get("person")
        credits_remaining = data.get("credits_remaining")

        if not person:
            return {"found": False, "profile": None,
                    "credits_remaining": credits_remaining, "error": None}

        profile = _parse_apollo_person(person, source="apollo_enrich")
        profile["enriched"] = True

        return {"found": True, "profile": profile,
                "credits_remaining": credits_remaining, "error": None}

    except requests.exceptions.Timeout:
        return {"found": False, "profile": None, "credits_remaining": None, "error": "TIMEOUT"}
    except requests.exceptions.ConnectionError:
        return {"found": False, "profile": None, "credits_remaining": None, "error": "CONNECTION_ERROR"}
    except Exception as e:
        return {"found": False, "profile": None, "credits_remaining": None,
                "error": f"UNEXPECTED: {str(e)}"}

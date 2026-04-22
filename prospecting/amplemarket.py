import requests

API_URL = "https://api.amplemarket.com/v1/leads/search"
COMPANIES_URL = "https://api.amplemarket.com/v1/companies/search"
PEOPLE_URL = "https://api.amplemarket.com/v1/people/search"

_SIZE_BUCKETS = [
    (1, 10, "1-10 employees"),
    (11, 50, "11-50 employees"),
    (51, 200, "51-200 employees"),
    (201, 500, "201-500 employees"),
    (501, 1000, "501-1000 employees"),
    (1001, 5000, "1001-5000 employees"),
    (5001, 10000, "5001-10000 employees"),
    (10001, 10_000_000, "10001+ employees"),
]


def _size_buckets(size_min: int, size_max: int) -> list[str]:
    return [label for lo, hi, label in _SIZE_BUCKETS if lo <= size_max and hi >= size_min]


def _post(api_key: str, url: str, payload: dict) -> dict:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    resp = requests.post(url, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def search_leads(api_key: str, icp: dict) -> list[dict]:
    """Search Amplemarket for leads matching the given ICP criteria."""
    payload = {
        "job_titles": icp["job_titles"],
        "industries": icp["industries"],
        "company_size": {
            "min": icp["company_size_min"],
            "max": icp["company_size_max"],
        },
        "locations": icp["locations"],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    resp = requests.post(API_URL, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data.get("leads", [])


def search_hiring_signal(api_key: str, location: str, size_min: int, size_max: int, limit: int = 50) -> list[dict]:
    """Companies actively hiring HR/People/Payroll roles."""
    return _post(api_key, COMPANIES_URL, {
        "job_openings": {"titles": [
            "HR Manager", "Head of People", "Payroll Manager", "HR Generalist",
            "VP of People", "Chief People Officer", "People Operations", "Benefits Administrator",
        ]},
        "company_sizes": _size_buckets(size_min, size_max),
        "company_locations": [location],
        "page_size": limit,
    }).get("companies", [])


def search_funding_signal(api_key: str, location: str, size_min: int, size_max: int, days_funding: int = 6, limit: int = 50) -> list[dict]:
    """Recently funded companies."""
    return _post(api_key, COMPANIES_URL, {
        "company_last_funding": {
            "round_type": ["seed", "series_a", "series_b", "series_c"],
            "range_months": days_funding,
        },
        "company_sizes": _size_buckets(size_min, size_max),
        "company_locations": [location],
        "page_size": limit,
    }).get("companies", [])


def search_growth_signal(api_key: str, location: str, size_min: int, size_max: int, growth_pct: int = 15, limit: int = 50) -> list[dict]:
    """Companies with headcount growth above threshold."""
    return _post(api_key, COMPANIES_URL, {
        "headcount_growth": {
            "growth_rates": [{"min": growth_pct}],
            "time_frame_in_months": 6,
        },
        "company_sizes": _size_buckets(size_min, size_max),
        "company_locations": [location],
        "page_size": limit,
    }).get("companies", [])


def search_news_signal(api_key: str, location: str, size_min: int, size_max: int, limit: int = 50) -> list[dict]:
    """Companies in the news for hiring/expansion."""
    return _post(api_key, COMPANIES_URL, {
        "news": {
            "categories": ["hires", "expands", "launches"],
            "range_months": 3,
        },
        "company_sizes": _size_buckets(size_min, size_max),
        "company_locations": [location],
        "page_size": limit,
    }).get("companies", [])


def find_decision_maker(api_key: str, company_domain: str) -> dict | None:
    """Find best HR/Finance/Leadership contact at a company."""
    people = _post(api_key, PEOPLE_URL, {
        "person_seniorities": ["C-Suite", "VP", "Head", "Director", "Founder"],
        "person_departments": ["Human Resources", "Finance", "Senior Leadership"],
        "company_domains": [company_domain],
        "page_size": 1,
    }).get("people", [])
    return people[0] if people else None

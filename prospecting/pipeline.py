from datetime import datetime, timezone

from .sheets import (
    append_leads,
    ensure_leads_header,
    get_client,
    get_existing_leads,
    read_icp_config,
)
from .amplemarket import search_leads
from .scorer import score_lead


def run_pipeline(
    google_credentials_path: str,
    amplemarket_api_key: str,
    anthropic_api_key: str,
    dry_run: bool = False,
    limit: int | None = None,
) -> list[dict]:
    """Run the full prospecting pipeline. Returns processed leads."""
    # 1. Read ICP configs from Google Sheets
    gs_client = get_client(google_credentials_path)
    icp_configs = read_icp_config(gs_client)
    print(f"Loaded {len(icp_configs)} ICP config(s) from Google Sheets")

    # 2. Get existing leads for dedup
    if not dry_run:
        existing = get_existing_leads(gs_client)
        ensure_leads_header(gs_client)
    else:
        existing = set()

    # 3. Search Amplemarket for each ICP config
    all_leads = []
    for i, icp in enumerate(icp_configs):
        print(f"Searching Amplemarket for ICP config #{i + 1}...")
        leads = search_leads(amplemarket_api_key, icp)
        print(f"  Found {len(leads)} leads")
        all_leads.extend(leads)

    # 4. Dedupe
    unique_leads = []
    for lead in all_leads:
        email = lead.get("email", "").strip().lower()
        linkedin = lead.get("linkedin_url", "").strip().lower()
        if email in existing or linkedin in existing:
            continue
        if email:
            existing.add(email)
        if linkedin:
            existing.add(linkedin)
        unique_leads.append(lead)

    print(f"{len(unique_leads)} new leads after deduplication")

    # 5. Apply limit
    if limit is not None:
        unique_leads = unique_leads[:limit]
        print(f"Capped to {limit} leads")

    # 6. Score each lead with Claude
    results = []
    for i, lead in enumerate(unique_leads):
        print(f"Scoring lead {i + 1}/{len(unique_leads)}: {lead.get('first_name', '')} {lead.get('last_name', '')}...")
        scoring = score_lead(anthropic_api_key, lead)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        row = {
            "timestamp": now,
            "first_name": lead.get("first_name", ""),
            "last_name": lead.get("last_name", ""),
            "title": lead.get("title", ""),
            "company": lead.get("company", ""),
            "industry": lead.get("industry", ""),
            "size": str(lead.get("company_size", "")),
            "email": lead.get("email", ""),
            "linkedin": lead.get("linkedin_url", ""),
            "score": scoring.get("score", ""),
            "reason": scoring.get("reason", ""),
            "recommended_outreach": scoring.get("recommended_outreach", ""),
            "status": "New",
        }
        results.append(row)

    # 7. Write to Google Sheets
    if dry_run:
        print("\n--- DRY RUN: would write these leads ---")
        for r in results:
            print(f"  {r['first_name']} {r['last_name']} | {r['title']} @ {r['company']} | Score: {r['score']} | {r['reason']}")
    else:
        sheet_rows = [
            [
                r["timestamp"],
                r["first_name"],
                r["last_name"],
                r["title"],
                r["company"],
                r["industry"],
                r["size"],
                r["email"],
                r["linkedin"],
                str(r["score"]),
                r["reason"],
                r["recommended_outreach"],
                r["status"],
            ]
            for r in results
        ]
        written = append_leads(gs_client, sheet_rows)
        print(f"Wrote {written} leads to Google Sheets")

    return results

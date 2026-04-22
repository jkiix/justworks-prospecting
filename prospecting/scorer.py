import json
from typing import Any

import anthropic

SYSTEM_PROMPT = (
    "You are a sales lead scoring assistant. "
    "Given a lead's details, return a JSON object with exactly three keys: "
    '"score" (integer 1-10, where 10 is best fit), '
    '"reason" (one sentence explaining the score), '
    '"recommended_outreach" (one of "LinkedIn", "Email", or "Phone"). '
    "Return ONLY valid JSON, no markdown or extra text."
)


def score_lead(api_key: str, lead: dict) -> dict:
    """Score a single lead using Claude. Returns dict with score, reason, recommended_outreach."""
    client = anthropic.Anthropic(api_key=api_key)

    user_msg = (
        f"Name: {lead.get('first_name', '')} {lead.get('last_name', '')}\n"
        f"Title: {lead.get('title', '')}\n"
        f"Company: {lead.get('company', '')}\n"
        f"Industry: {lead.get('industry', '')}\n"
        f"Company Size: {lead.get('company_size', '')}"
    )

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=256,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )

    text = response.content[0].text.strip()
    return json.loads(text)


def score_intent_signals(company: dict, fired_signals: set) -> tuple[int, list[str], str]:
    """Score a company based on which intent signals fired."""
    score = 0
    reasons: list[str] = []

    if "hiring" in fired_signals:
        score += 40
        reasons.append("🎯 Actively hiring HR/People roles")
    if "funding" in fired_signals:
        score += 30
        reasons.append("💰 Recently funded")
    if "growth" in fired_signals:
        score += 20
        reasons.append("📈 Headcount growing")
    if "news" in fired_signals:
        score += 10
        reasons.append("📰 In the news")

    emp = company.get("estimated_number_of_employees") or 0
    if 11 <= emp <= 200:
        score += 15
        reasons.append("✅ ICP size match")

    if len(fired_signals) >= 3:
        score += 20
        reasons.append("🔥 Multiple signals firing")

    tier = "Tier 1" if score >= 80 else "Tier 2" if score >= 50 else "Tier 3"
    return score, reasons, tier


def generate_why_now(api_key: str, companies_with_signals: list[dict[str, Any]]) -> dict[str, str]:
    """Single Claude call for all companies. Returns {domain: why_now_string}."""
    if not companies_with_signals:
        return {}

    client = anthropic.Anthropic(api_key=api_key)
    payload = [
        {"domain": c["domain"], "signals": list(c.get("signals", []))}
        for c in companies_with_signals
    ]

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        system=(
            "You are a Justworks sales intelligence assistant. Justworks is a PEO "
            "for SMBs (10-500 employees) handling payroll, benefits, HR compliance. Ideal "
            "buyers: HR leaders, CFOs, COOs, founders at growing US companies. Common "
            "triggers: recent funding, headcount growth, new HR hire, compliance pain."
        ),
        messages=[{
            "role": "user",
            "content": (
                "Given these companies and their intent signals, write a 1-sentence "
                '"why now" for each explaining why they should hear from Justworks today. '
                'Return only JSON: [{"domain": "...", "why_now": "..."}]\n\n'
                + json.dumps(payload)
            ),
        }],
    )

    items = json.loads(response.content[0].text.strip())
    return {item["domain"]: item["why_now"] for item in items}

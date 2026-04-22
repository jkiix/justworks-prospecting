import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from .amplemarket import (
    find_decision_maker,
    search_funding_signal,
    search_growth_signal,
    search_hiring_signal,
    search_news_signal,
)
from .scorer import generate_why_now, score_intent_signals
from .sheets import (
    append_intent_leads,
    ensure_intent_leads_header,
    get_client,
    read_intent_config,
)

log = logging.getLogger(__name__)

_SIGNAL_FNS = {
    "hiring": search_hiring_signal,
    "funding": search_funding_signal,
    "growth": search_growth_signal,
    "news": search_news_signal,
}


def run_intent_pipeline(
    google_credentials_path: str,
    amplemarket_api_key: str,
    anthropic_api_key: str,
    dry_run: bool = False,
    limit: int = 50,
    output_file: str = "prospects.md",
    html_file: str = "index.html",
) -> list[dict]:
    # 1. Read Intent Config
    gs_client = get_client(google_credentials_path)
    intent_configs = read_intent_config(gs_client)
    enabled = [c for c in intent_configs if c["enabled"]]
    print(f"Loaded {len(intent_configs)} intent config(s), {len(enabled)} enabled")

    # 2. Run signal searches (max 3 concurrent)
    def _run_signal(config: dict) -> tuple[str, list[dict]]:
        sig = config["signal"]
        fn = _SIGNAL_FNS.get(sig)
        if fn is None:
            log.warning(f"Unknown signal type '{sig}', skipping")
            return sig, []
        kwargs: dict = {
            "location": config["location"],
            "size_min": config["size_min"],
            "size_max": config["size_max"],
        }
        if sig == "funding":
            kwargs["days_funding"] = config.get("days_funding", 6)
        elif sig == "growth":
            kwargs["growth_pct"] = config.get("growth_pct", 15)
        try:
            results = fn(amplemarket_api_key, **kwargs)
            print(f"  [{sig}] {len(results)} companies found")
            return sig, results
        except Exception as exc:
            log.warning(f"Signal search '{sig}' failed: {exc}")
            return sig, []

    companies_by_signal: dict[str, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(_run_signal, config): config["signal"] for config in enabled}
        for future in as_completed(futures):
            sig, results = future.result()
            companies_by_signal[sig] = results

    # 3. Deduplicate by domain
    company_map: dict[str, dict] = {}
    for sig, companies in companies_by_signal.items():
        for co in companies:
            domain = (co.get("domain") or "").strip().lower()
            if not domain:
                continue
            if domain not in company_map:
                company_map[domain] = {"company": co, "signals": set()}
            company_map[domain]["signals"].add(sig)
    print(f"{len(company_map)} unique companies after deduplication")

    # 4. Score and sort
    scored: list[dict] = []
    for domain, data in company_map.items():
        score, reasons, tier = score_intent_signals(data["company"], data["signals"])
        scored.append({
            "domain": domain,
            "company": data["company"],
            "signals": data["signals"],
            "score": score,
            "reasons": reasons,
            "tier": tier,
            "contact": None,
            "why_now": "",
        })
    scored.sort(key=lambda x: x["score"], reverse=True)
    if limit:
        scored = scored[:limit]
        print(f"Capped to {limit} companies")

    # 5. Contact lookup for Tier 1+2 (score >= 50)
    needs_contact = [s for s in scored if s["score"] >= 50]
    print(f"Looking up contacts for {len(needs_contact)} Tier 1/2 companies...")

    def _lookup(item: dict) -> tuple[str, dict | None]:
        try:
            contact = find_decision_maker(amplemarket_api_key, item["domain"])
            if contact:
                name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()
                print(f"  {item['domain']}: {name} — {contact.get('title', '')}")
            else:
                print(f"  {item['domain']}: no contact found")
            return item["domain"], contact
        except Exception as exc:
            log.warning(f"Contact lookup failed for {item['domain']}: {exc}")
            return item["domain"], None

    contact_map: dict[str, dict | None] = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(_lookup, item): item["domain"] for item in needs_contact}
        for future in as_completed(futures):
            domain, contact = future.result()
            contact_map[domain] = contact

    for item in scored:
        item["contact"] = contact_map.get(item["domain"])

    # 6. Batch why_now via single Claude call
    why_now_input = [
        {"domain": s["domain"], "company": s["company"], "signals": list(s["signals"])}
        for s in scored
    ]
    print(f"Generating why-now copy for {len(why_now_input)} companies...")
    why_now_map = generate_why_now(anthropic_api_key, why_now_input)
    for item in scored:
        item["why_now"] = why_now_map.get(item["domain"], "")

    # 7. Write markdown + HTML dashboard
    _write_markdown(scored, output_file)
    print(f"Wrote {output_file}")
    _write_html(scored, html_file)
    print(f"Wrote {html_file}")

    # 8. Write Tier 1+2 to Sheets
    tier_1_2 = [s for s in scored if s["score"] >= 50]
    if dry_run:
        print(f"\n--- DRY RUN: would write {len(tier_1_2)} Tier 1/2 companies to Intent Leads ---")
        for s in scored[:10]:
            print(f"  [{s['tier']}] {s['company'].get('name', s['domain'])} | Score: {s['score']} | {s['why_now']}")
    else:
        ensure_intent_leads_header(gs_client)
        rows = _to_sheet_rows(tier_1_2)
        written = append_intent_leads(gs_client, rows)
        print(f"Wrote {written} leads to 'Intent Leads' tab")

    return scored


def _fmt_contact(contact: dict | None) -> str:
    if not contact:
        return "[TBD]"
    name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip() or "[TBD]"
    parts = [name]
    if contact.get("title"):
        parts.append(contact["title"])
    if contact.get("email"):
        parts.append(contact["email"])
    return " | ".join(parts)


def _write_markdown(scored: list[dict], output_file: str) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    all_signals = sorted({s for item in scored for s in item["signals"]})
    tier1 = [s for s in scored if s["tier"] == "Tier 1"]
    tier2 = [s for s in scored if s["tier"] == "Tier 2"]
    tier3 = [s for s in scored if s["tier"] == "Tier 3"]

    lines = [
        "# Justworks Intent Signal Report",
        f"Generated: {now} | Signals: {', '.join(all_signals)} | Total: {len(scored)}",
        "",
    ]

    def _section(header: str, items: list[dict]) -> None:
        lines.append(f"## {header}")
        lines.append("")
        for item in items:
            co = item["company"]
            name = co.get("name") or item["domain"]
            emp = co.get("estimated_number_of_employees", "")
            industry = co.get("industry", "")
            signals_str = " · ".join(item["reasons"])
            lines.append(f"### {name} — score: {item['score']}")
            lines.append(f"**Domain:** {item['domain']} | **Size:** {emp} employees | **Industry:** {industry}  ")
            lines.append(f"**Signals:** {signals_str}  ")
            lines.append(f"**Why now:** {item['why_now']}  ")
            lines.append(f"**Contact:** {_fmt_contact(item['contact'])}  ")
            lines.append("")
            lines.append("---")
            lines.append("")

    if tier1:
        _section("🔥 Tier 1 — Score 80+ (Immediate outreach)", tier1)
    if tier2:
        _section("⚡ Tier 2 — Score 50–79 (High priority)", tier2)
    if tier3:
        _section("📋 Tier 3 — Score 20–49 (Watch list, no contact lookup)", tier3)

    with open(output_file, "w") as f:
        f.write("\n".join(lines))


def _write_html(scored: list[dict], html_file: str) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    data = {
        "generated": now,
        "prospects": [
            {
                "domain": s["domain"],
                "tier": s["tier"],
                "score": s["score"],
                "reasons": s["reasons"],
                "why_now": s["why_now"],
                "company": {
                    "name": s["company"].get("name", ""),
                    "industry": s["company"].get("industry", ""),
                    "estimated_number_of_employees": s["company"].get("estimated_number_of_employees", ""),
                },
                "contact": {
                    "first_name": (s["contact"] or {}).get("first_name", ""),
                    "last_name": (s["contact"] or {}).get("last_name", ""),
                    "title": (s["contact"] or {}).get("title", ""),
                    "email": (s["contact"] or {}).get("email", ""),
                } if s["contact"] else None,
            }
            for s in scored
        ],
    }
    # Escape </script> to prevent early tag close
    json_str = json.dumps(data, ensure_ascii=False).replace("</script>", "<\\/script>")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Justworks Prospect Dashboard</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f1f5f9;color:#1e293b}}
header{{background:#1e293b;color:#fff;padding:20px 32px;display:flex;justify-content:space-between;align-items:center}}
header h1{{font-size:1.1rem;font-weight:700;letter-spacing:-.01em}}
.meta{{font-size:.8rem;opacity:.6}}
main{{max-width:1200px;margin:0 auto;padding:28px 32px}}
.tier-section{{margin-bottom:36px}}
.tier-header{{font-size:1rem;font-weight:700;margin-bottom:14px;display:flex;align-items:center;gap:8px}}
.count{{color:#94a3b8;font-weight:400;font-size:.85rem}}
.cards{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px}}
.card{{background:#fff;border-radius:10px;padding:18px;box-shadow:0 1px 3px rgba(0,0,0,.07);border-left:4px solid var(--c)}}
.t1{{--c:#ef4444}}.t2{{--c:#f59e0b}}.t3{{--c:#3b82f6}}
.card-top{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px}}
.co-name{{font-weight:700;font-size:.95rem;line-height:1.3}}
.co-sub{{font-size:.75rem;color:#64748b;margin-top:2px}}
.badge{{background:var(--c);color:#fff;padding:3px 9px;border-radius:20px;font-size:.78rem;font-weight:700;white-space:nowrap;margin-left:10px}}
.signals{{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:10px}}
.sig{{background:#f1f5f9;padding:2px 8px;border-radius:5px;font-size:.75rem}}
.why{{font-size:.83rem;color:#475569;line-height:1.5;margin-bottom:10px}}
.contact{{font-size:.78rem;color:#64748b;border-top:1px solid #f1f5f9;padding-top:9px}}
.contact b{{color:#1e293b}}
.empty{{color:#94a3b8;font-style:italic;font-size:.85rem}}
</style>
</head>
<body>
<header>
  <h1>Justworks Prospect Dashboard</h1>
  <div class="meta" id="meta"></div>
</header>
<main id="main"></main>
<script>
const D={json_str};
document.getElementById('meta').textContent='Updated '+D.generated+' · '+D.prospects.length+' companies';
const main=document.getElementById('main');
[['Tier 1','🔥 Tier 1 — Immediate Outreach','t1'],['Tier 2','⚡ Tier 2 — High Priority','t2'],['Tier 3','📋 Tier 3 — Watch List','t3']].forEach(([key,label,cls])=>{{
  const items=D.prospects.filter(p=>p.tier===key);
  if(!items.length)return;
  const sec=document.createElement('div');
  sec.className='tier-section';
  sec.innerHTML='<div class="tier-header">'+label+' <span class="count">('+items.length+')</span></div><div class="cards">'+items.map(p=>card(p,cls)).join('')+'</div>';
  main.appendChild(sec);
}});
function card(p,cls){{
  const co=p.company;
  const name=co.name||p.domain;
  const sub=[p.domain,co.industry,co.estimated_number_of_employees?(co.estimated_number_of_employees+' employees'):''].filter(Boolean).join(' · ');
  const c=p.contact;
  const contactHtml=c?('<b>'+(c.first_name+' '+c.last_name).trim()+'</b>'+(c.title?', '+c.title:'')+(c.email?' &middot; <a href="mailto:'+c.email+'">'+c.email+'</a>':'')):('<span class="empty">[TBD]</span>');
  return '<div class="card '+cls+'"><div class="card-top"><div><div class="co-name">'+name+'</div><div class="co-sub">'+sub+'</div></div><div class="badge">'+p.score+'</div></div><div class="signals">'+p.reasons.map(r=>'<span class="sig">'+r+'</span>').join('')+'</div>'+(p.why_now?'<div class="why">'+p.why_now+'</div>':'')+'<div class="contact">'+contactHtml+'</div></div>';
}}
</script>
</body>
</html>"""

    with open(html_file, "w") as f:
        f.write(html)


def _to_sheet_rows(scored: list[dict]) -> list[list]:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    for item in scored:
        co = item["company"]
        contact = item["contact"] or {}
        rows.append([
            now,
            contact.get("first_name", ""),
            contact.get("last_name", ""),
            contact.get("title", ""),
            co.get("name", item["domain"]),
            co.get("industry", ""),
            str(co.get("estimated_number_of_employees", "")),
            contact.get("email", ""),
            contact.get("linkedin_url", ""),
            str(item["score"]),
            " | ".join(item["reasons"]),
            "New",
            "|".join(sorted(item["signals"])),
            item["why_now"],
        ])
    return rows

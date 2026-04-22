import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

LEADS_COLUMNS = [
    "Timestamp",
    "First Name",
    "Last Name",
    "Title",
    "Company",
    "Industry",
    "Size",
    "Email",
    "LinkedIn",
    "Score",
    "Reason",
    "Recommended Outreach",
    "Status",
]

INTENT_LEADS_COLUMNS = [
    "Timestamp",
    "First Name",
    "Last Name",
    "Title",
    "Company",
    "Industry",
    "Size",
    "Email",
    "LinkedIn",
    "Score",
    "Reason",
    "Status",
    "Signals",
    "Why Now",
]


def get_client(credentials_path: str) -> gspread.Client:
    creds = Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
    return gspread.authorize(creds)


def read_icp_config(client: gspread.Client) -> list[dict]:
    sheet = client.open("Prospecting")
    ws = sheet.worksheet("ICP Config")
    records = ws.get_all_records()
    configs = []
    for row in records:
        configs.append({
            "job_titles": [t.strip() for t in str(row.get("job_titles", "")).split(",") if t.strip()],
            "industries": [i.strip() for i in str(row.get("industries", "")).split(",") if i.strip()],
            "company_size_min": int(row.get("company_size_min", 0)),
            "company_size_max": int(row.get("company_size_max", 10000)),
            "locations": [l.strip() for l in str(row.get("locations", "")).split(",") if l.strip()],
        })
    return configs


def get_existing_leads(client: gspread.Client) -> set[str]:
    """Return a set of emails and LinkedIn URLs already in the Leads tab for deduplication."""
    sheet = client.open("Prospecting")
    ws = sheet.worksheet("Leads")
    rows = ws.get_all_records()
    existing = set()
    for row in rows:
        email = str(row.get("Email", "")).strip().lower()
        linkedin = str(row.get("LinkedIn", "")).strip().lower()
        if email:
            existing.add(email)
        if linkedin:
            existing.add(linkedin)
    return existing


def ensure_leads_header(client: gspread.Client) -> None:
    sheet = client.open("Prospecting")
    ws = sheet.worksheet("Leads")
    first_row = ws.row_values(1)
    if first_row != LEADS_COLUMNS:
        ws.update("A1", [LEADS_COLUMNS])


def append_leads(client: gspread.Client, leads: list[list[str]]) -> int:
    """Append lead rows to the Leads tab. Returns number of rows written."""
    if not leads:
        return 0
    sheet = client.open("Prospecting")
    ws = sheet.worksheet("Leads")
    ws.append_rows(leads, value_input_option="USER_ENTERED")
    return len(leads)


def read_intent_config(client: gspread.Client) -> list[dict]:
    sheet = client.open("Prospecting")
    ws = sheet.worksheet("Intent Config")
    records = ws.get_all_records()
    configs = []
    for row in records:
        enabled_raw = str(row.get("enabled", "")).strip().upper()
        configs.append({
            "signal": str(row.get("signal", "")).strip().lower(),
            "enabled": enabled_raw in ("TRUE", "YES", "1"),
            "location": str(row.get("location", "United States")).strip(),
            "size_min": int(row.get("size_min", 1)),
            "size_max": int(row.get("size_max", 500)),
            "days_funding": int(row["days_funding"]) if row.get("days_funding") else 6,
            "growth_pct": int(row["growth_pct"]) if row.get("growth_pct") else 15,
        })
    return configs


def ensure_intent_leads_header(client: gspread.Client) -> None:
    sheet = client.open("Prospecting")
    ws = sheet.worksheet("Intent Leads")
    if ws.row_values(1) != INTENT_LEADS_COLUMNS:
        ws.update("A1", [INTENT_LEADS_COLUMNS])


def append_intent_leads(client: gspread.Client, leads: list[list]) -> int:
    if not leads:
        return 0
    sheet = client.open("Prospecting")
    ws = sheet.worksheet("Intent Leads")
    ws.append_rows(leads, value_input_option="USER_ENTERED")
    return len(leads)

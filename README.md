# Claude Prospecting Automation

Google Sheets + Amplemarket prospecting pipeline scored by Claude.

## How it works

1. Reads ICP (Ideal Customer Profile) criteria from a Google Sheet's **ICP Config** tab
2. Searches Amplemarket for matching leads
3. Scores each lead with Claude (1-10 fit score + outreach recommendation)
4. Deduplicates by email/LinkedIn and writes results to the **Leads** tab

## Setup

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure credentials

```bash
cp .env.example .env
```

Fill in `.env`:

- **ANTHROPIC_API_KEY** — from [console.anthropic.com](https://console.anthropic.com/)
- **AMPLEMARKET_API_KEY** — your Amplemarket API bearer token
- **GOOGLE_CREDENTIALS_PATH** — path to your Google service account JSON file (default: `credentials.json`)

### 3. Set up Google Sheets

Create a Google Sheet named **Prospecting** with two tabs:

**ICP Config** tab columns:

| job_titles | industries | company_size_min | company_size_max | locations |
|---|---|---|---|---|
| VP Sales, Director Sales | SaaS, FinTech | 50 | 500 | United States |

- `job_titles`, `industries`, and `locations` are comma-separated lists
- Each row is a separate search query

**Leads** tab: leave empty — headers are created automatically on first run.

Share the sheet with your service account email (the `client_email` in your credentials JSON).

## Usage

```bash
# Full run — search, score, and write to Sheets
python run.py

# Preview without writing
python run.py --dry-run

# Limit to 10 leads per run
python run.py --limit 10

# Combine flags
python run.py --dry-run --limit 5
```

### Intent Signal Engine

Finds companies showing buying signals (hiring HR roles, recent funding, headcount growth, news) and scores + ranks them.

```bash
# Run intent signal pipeline
python run.py --mode intent

# Dry run — prints top 10 companies, writes prospects.md but skips Sheets
python run.py --mode intent --dry-run

# Limit companies and set output file
python run.py --mode intent --limit 50 --output prospects.md
```

Output:
- **prospects.md** — ranked report with Tier 1/2/3 companies, why-now copy, and contact details
- **Intent Leads tab** — Tier 1 + Tier 2 companies written to Google Sheets (skipped on `--dry-run`)

#### Intent Config tab setup

Add a tab named **Intent Config** to your Prospecting Google Sheet with these columns:

| signal | enabled | location | size_min | size_max | days_funding | growth_pct |
|---|---|---|---|---|---|---|
| hiring | TRUE | United States | 1 | 1500 | | |
| funding | TRUE | United States | 1 | 1500 | 6 | |
| growth | TRUE | United States | 1 | 1500 | | 15 |
| news | FALSE | United States | 1 | 1500 | | |

- `signal`: one of `hiring`, `funding`, `growth`, `news`
- `enabled`: `TRUE` to include this signal in the run, `FALSE` to skip
- `days_funding`: months to look back for funding rounds (funding signal only)
- `growth_pct`: minimum headcount growth % over 6 months (growth signal only)

#### Intent Leads tab setup

Add a tab named **Intent Leads** to your Prospecting Google Sheet — leave it empty. Headers are created automatically on first run. Columns written: Timestamp, First Name, Last Name, Title, Company, Industry, Size, Email, LinkedIn, Score, Reason, Status, Signals, Why Now.

## Project structure

```
run.py                  # CLI entrypoint
prospecting/
  __init__.py
  sheets.py             # Google Sheets read/write via gspread
  amplemarket.py        # Amplemarket lead search + intent signal searches
  scorer.py             # Claude lead scoring + intent signal scoring
  pipeline.py           # Prospect pipeline orchestration
  intent_pipeline.py    # Intent signal pipeline orchestration
```

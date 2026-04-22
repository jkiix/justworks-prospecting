#!/usr/bin/env python3
"""Entrypoint for the prospecting pipeline."""

import argparse
import os
import sys

from dotenv import load_dotenv

from prospecting.intent_pipeline import run_intent_pipeline
from prospecting.pipeline import run_pipeline


def main():
    parser = argparse.ArgumentParser(description="Google Sheets + Amplemarket prospecting pipeline")
    parser.add_argument("--mode", choices=["prospect", "intent"], default="prospect",
                        help="Pipeline mode: 'prospect' (default) or 'intent'")
    parser.add_argument("--dry-run", action="store_true", help="Print results without writing to Google Sheets")
    parser.add_argument("--limit", type=int, default=None, help="Max number of leads/companies to process per run")
    parser.add_argument("--output", default="prospects.md", help="Output markdown file (intent mode only)")
    parser.add_argument("--html", default="index.html", help="Output HTML dashboard file (intent mode only)")
    args = parser.parse_args()

    load_dotenv()

    anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")
    amplemarket_api_key = os.environ.get("AMPLEMARKET_API_KEY")
    google_credentials_path = os.environ.get("GOOGLE_CREDENTIALS_PATH")

    missing = []
    if not anthropic_api_key:
        missing.append("ANTHROPIC_API_KEY")
    if not amplemarket_api_key:
        missing.append("AMPLEMARKET_API_KEY")
    if args.mode == "prospect" and not google_credentials_path:
        missing.append("GOOGLE_CREDENTIALS_PATH")

    if missing:
        print(f"Error: missing environment variables: {', '.join(missing)}", file=sys.stderr)
        print("Copy .env.example to .env and fill in your credentials.", file=sys.stderr)
        sys.exit(1)

    if args.mode == "intent":
        results = run_intent_pipeline(
            amplemarket_api_key=amplemarket_api_key,
            anthropic_api_key=anthropic_api_key,
            dry_run=args.dry_run,
            limit=args.limit or 50,
            output_file=args.output,
            html_file=args.html,
        )
        print(f"\nDone. Processed {len(results)} companies.")
    else:
        results = run_pipeline(
            google_credentials_path=google_credentials_path,
            amplemarket_api_key=amplemarket_api_key,
            anthropic_api_key=anthropic_api_key,
            dry_run=args.dry_run,
            limit=args.limit,
        )
        print(f"\nDone. Processed {len(results)} leads.")


if __name__ == "__main__":
    main()

#!/bin/bash
cd "/Users/josephkim/Desktop/claude prospecting automation"
source .venv/bin/activate
python3 run.py --mode intent --output prospects.md --html index.html >> cron.log 2>&1

# Push updated dashboard to GitHub Pages
git add index.html prospects.md
git commit -m "Update dashboard $(date +%Y-%m-%d)" >> cron.log 2>&1
git push origin main >> cron.log 2>&1

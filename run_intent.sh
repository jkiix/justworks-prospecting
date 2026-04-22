#!/bin/bash
cd "/Users/josephkim/Desktop/claude prospecting automation"
source .venv/bin/activate
python3 run.py --mode intent --output prospects.md --html index.html >> cron.log 2>&1

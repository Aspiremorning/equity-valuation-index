#!/usr/bin/env bash
# Manual rebuild + publish. Normal daily flow needs only the Google Sheet —
# this is for local testing or forcing an immediate refresh.
set -euo pipefail
cd "$(dirname "$0")"

# If SHEET_CSV_URL is exported, build.py pulls the live Google Sheet;
# otherwise it uses data/evi_data.csv.
python3 scripts/build.py

git add -A
git commit -m "EVI manual build $(date +'%d-%b-%Y %H:%M')" || echo "Nothing to commit."
git push
echo "Done → https://<your-username>.github.io/equity-valuation-index/"

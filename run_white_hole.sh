#!/bin/bash
set -euo pipefail

# Determine base directory (where this script lives)
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BASE_DIR"

# Use venv python if available, otherwise system python
if [[ -f "$BASE_DIR/.venv/bin/python" ]]; then
    PYTHON="$BASE_DIR/.venv/bin/python"
else
    PYTHON="python3"
fi

# Where the page is served from: an ssh alias on this host whose key the web
# server restricts (rrsync) to the site's web root, so "/" here IS that root.
SITE_HOST="${WHITERIVER_HOST:-whiteriver}"

# Pull code. --autostash carries the uncommitted prediction-log rows and cache
# across the pull (they are only committed on the hour, below); --rebase rather
# than --ff-only so a stranded local commit from a rejected push rides on top
# of origin and is pushed next time instead of blocking every later pull.
echo "Pulling latest changes..."
git pull --rebase --autostash

# Run the Python program
echo "Running main.py..."
$PYTHON "$BASE_DIR/main.py"

# The published page. These are NOT committed (gitignored): the chart alone put
# 570 MB into .git before 2026-10-16. They go straight to the web server.
SITE_FILES=(
    "white_hole_conditions.html"
    "vertical_flow_chart.png"
    "index.html"
)
for filename in "${SITE_FILES[@]}"; do
    if [[ ! -f "$BASE_DIR/$filename" ]]; then
        echo "Error: Output file not found: $BASE_DIR/$filename"
        exit 1
    fi
done

# Publish every run — the page is current to the quarter hour. A failed push
# to the server leaves the previous page in place and must not stop the log
# below from being kept.
echo "Publishing to $SITE_HOST..."
if rsync -az --chmod=F644 "${SITE_FILES[@]}" "$SITE_HOST:/"; then
    echo "Publish complete."
else
    echo "WARNING: publish to $SITE_HOST failed (rsync exit $?); the site keeps the previous page."
fi

# The prediction log (one row per run, for validating the travel model) and
# the outage-fallback cache are committed on the hour — four runs' worth at a
# time — so the repo gains a day's history in 24 small commits, not 96.
if [[ "$(date '+%M')" != "00" && "${FORCE_COMMIT:-0}" != "1" ]]; then
    echo "Not on the hour; the log and cache ride to the next hourly commit."
    exit 0
fi

[[ -f "$BASE_DIR/last_good_data.json" ]] && git add "$BASE_DIR/last_good_data.json"
[[ -f "$BASE_DIR/predictions.csv" ]] && git add "$BASE_DIR/predictions.csv"

if git diff --cached --quiet; then
    echo "No changes to commit."
else
    git commit -m "Update prediction log $(date '+%Y-%m-%d %H:%M')"
    # A push can lose the race against a code push from the workstation;
    # integrate and retry once before giving up (the next run rebases anyway)
    if ! git push; then
        echo "Push rejected; rebasing onto origin and retrying..."
        git pull --rebase
        git push
    fi
    echo "Push complete."
fi

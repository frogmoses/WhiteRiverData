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

# Stash any uncommitted changes (from interrupted/failed runs) and pull.
# --rebase rather than --ff-only: a run whose push was rejected (a code push
# landed between its pull and its push, 2026-09-21) leaves a local output
# commit that would block every later fast-forward; rebasing it onto origin
# keeps that run's predictions.csv row and heals the branch on the next run.
echo "Pulling latest changes..."
git stash push -u -q || true
git pull --rebase

# Run the Python program
echo "Running main.py..."
$PYTHON "$BASE_DIR/main.py"

# Output files that should be committed
OUTPUT_FILES=(
    "white_hole_conditions.html"
    "vertical_flow_chart.png"
)

# Verify files exist
for filename in "${OUTPUT_FILES[@]}"; do
    if [[ ! -f "$BASE_DIR/$filename" ]]; then
        echo "Error: Output file not found: $BASE_DIR/$filename"
        exit 1
    fi
done

# The job runs every quarter hour so a dam row (posted ~10 min past the hour)
# is read minutes after it lands, not an hour later — the 2026-10-07 rise was
# flagged 12 min AFTER it reached the ramp because the :00 run missed the row.
# But the chart is 130 KB and the repo is already 450 MB, so the page and
# chart are only committed when the dam has published a new reading (the
# cache changed) or on the hour (the "now" row, the schedule and the gauges
# move between readings too). The cache and the prediction log are small and
# always committed; a skipped page is discarded so no stash piles up.
# FORCE_PUBLISH=1 ./run_white_hole.sh publishes regardless (after a code change
# the page should not wait for the hour).
PUBLISH_PAGE=1
if [[ -f "$BASE_DIR/last_good_data.json" ]] \
   && git diff --quiet -- "$BASE_DIR/last_good_data.json" \
   && [[ "$(date '+%M')" != "00" ]] \
   && [[ "${FORCE_PUBLISH:-0}" != "1" ]]; then
    PUBLISH_PAGE=0
fi

# Commit and push to GitHub (served via GitHub Pages)
if [[ "$PUBLISH_PAGE" == "1" ]]; then
    echo "Committing updated output files..."
    git add "${OUTPUT_FILES[@]}"
else
    echo "No new dam reading and not on the hour; keeping the published page."
    git checkout -q -- "${OUTPUT_FILES[@]}"
fi

# Outage-fallback cache: must be committed (the stash -u above would discard
# an untracked copy), but is absent when no run has succeeded yet
if [[ -f "$BASE_DIR/last_good_data.json" ]]; then
    git add "$BASE_DIR/last_good_data.json"
fi

# Prediction log: one row per run, committed for later validation of the
# travel model (same stash caveat as the cache above)
if [[ -f "$BASE_DIR/predictions.csv" ]]; then
    git add "$BASE_DIR/predictions.csv"
fi

# Only commit if there are changes
if git diff --cached --quiet; then
    echo "No changes to commit."
else
    git commit -m "Update water conditions $(date '+%Y-%m-%d %H:%M')"
    # A push can lose the race against a code push from the workstation;
    # integrate and retry once before giving up (the next run rebases anyway)
    if ! git push; then
        echo "Push rejected; rebasing onto origin and retrying..."
        git pull --rebase
        git push
    fi
    echo "Push complete."
fi

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

# Commit and push to GitHub (served via GitHub Pages)
echo "Committing updated output files..."
git add "${OUTPUT_FILES[@]}"

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

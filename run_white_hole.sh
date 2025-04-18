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

# Pull any code changes before running
echo "Pulling latest changes..."
git pull --ff-only

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

# Only commit if there are changes
if git diff --cached --quiet; then
    echo "No changes to commit."
else
    git commit -m "Update water conditions $(date '+%Y-%m-%d %H:%M')"
    git push
    echo "Push complete."
fi

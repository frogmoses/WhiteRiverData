# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Real-time water condition monitoring for White Hole on the White River near Bull Shoals Dam (Arkansas). Serves fishermen and boaters by tracking flow conditions for wading and boating safety.

## Commands

```bash
# Run main application (generates white_hole_conditions.html + vertical_flow_chart.png)
python main.py

# Generate test HTML files with various water scenarios for visual inspection
python generate_test_html.py

# Run test suite
pytest

# Run tests with coverage report
pytest --cov

# Install dependencies (using uv package manager)
uv sync

# Install test dependencies
uv sync --extra test

# Install Playwright browser for web scraping
playwright install chromium
```

## Repository Structure

```
WhiteRiverData/
├── main.py                  # Entry point: orchestrates data fetch → calculate → format → save
├── data_fetcher.py          # Scrapes USACE Bull Shoals Dam page via Playwright + BeautifulSoup
├── water_calculator.py      # Travel time, water state, fishing conditions, timeline calculations
├── formatters.py            # HTML and text output generation, chart embedding
├── chart_generator.py       # Matplotlib vertical river flow progression chart
├── generate_test_html.py    # Generates HTML for 8 water scenarios (visual inspection)
├── run_white_hole.sh        # Production script: pulls code, runs main.py, commits and pushes output
├── index.html               # Redirect to white_hole_conditions.html for GitHub Pages root
├── pyproject.toml           # Project config, dependencies (uv)
├── pytest.ini               # Pytest configuration
├── tests/
│   ├── conftest.py          # Shared fixtures: 10 water condition datasets
│   ├── test_water_calculator.py  # Unit tests for flow calculations and condition logic
│   ├── test_formatters.py        # Unit tests for HTML/text output generation
│   └── test_integration.py       # End-to-end tests with various water scenarios
```

## Architecture

### Data Flow

```
main.py: generate_white_hole_summary(output_format, data, dataset_name, current_time)
    ↓
data_fetcher.py: get_bull_shoals_data() → scrapes USACE page → list[dict]
    ↓
water_calculator.py:
    calculate_travel_time(cfs) → hours (float)
    determine_water_state(data, current_time, cfs) → "rising"/"falling"/"stable"
    get_fishing_condition(cfs) → (wading_str, boating_str)
    get_recent_trend(data, current_time) → trend description string
    forecast_conditions(data, current_time) → forecast description string
    calculate_timeline(data, current_time) → list[dict] for timeline display
    format_generators(cfs) → "2-3 generators" style string
    ↓
formatters.py:
    generate_html_summary(...) → HTML string (headline banner + timeline)
    generate_text_summary(...) → plain text string
    include_chart_in_html(html, chart_path) → HTML with embedded chart
    save_html_summary(html, filename) → writes file
chart_generator.py:
    generate_vertical_river_chart(data, current_time, filename) → PNG
```

### Core Data Structure

Water data entries are dicts with: `date_time`, `elevation`, `tailwater`, `generation`, `turbine_release`, `spillway_release`, `total_release`, and optional `error` flag.

### Key Calculations

- **Travel Time** (`water_calculator.py:calculate_travel_time`): Maps CFS to river speed using 9 generator bands (0-8+ generators at 3300 CFS each), interpolates between bands, calculates time to travel 7 miles from dam to White Hole. Returns hours as float.
- **Water State** (`water_calculator.py:determine_water_state`): Compares last 3 arrival-adjusted entries. Rising/falling threshold: >20% change AND >500 CFS difference.
- **Fishing Conditions** (`water_calculator.py:get_fishing_condition`): CFS thresholds at 2000, 5000, 10000 determine wading/boating suitability.
- **Timeline** (`water_calculator.py:calculate_timeline`): Returns up to 4 entries showing current/incoming water with arrival ETAs.

### Data Source

- USACE Bull Shoals Dam tabular data: `https://www.swl-wc.usace.army.mil/pages/data/tabular/htm/bulsdam.htm`
- Travel time model based on: https://www.hisplaceresort.net/white-river-info

## Output Files

- `white_hole_conditions.html` — HTML report with headline banner, timeline, condition pills, and embedded chart
- `vertical_flow_chart.png` — Chart showing dam→White Hole flow progression with color gradient and generator labels
- Test variants: `white_hole_conditions_{scenario}.html` and `vertical_flow_chart_{scenario}.png`

## Testing

Uses pytest with fixtures in `tests/conftest.py` providing 10 water condition datasets (normal, rising, falling, high, low, flood, fluctuating, sudden_jump, sudden_drop, bug_scenario).

```bash
pytest                                  # Run all tests
pytest --cov                            # With coverage
pytest tests/test_water_calculator.py   # Specific file
pytest -k "test_forecast"              # Pattern match
pytest -m unit                          # Only unit tests
pytest -m integration                   # Only integration tests
```

## Deployment

### Production Environment

- **Host**: Raspberry Pi (local network)
- **Project Path**: `/home/frogmoses/WhiteRiverData`
- **Log Path**: `/home/frogmoses/log/white_hole.log`
- **Serving**: GitHub Pages from the repo's master branch

### Production URL

https://briancarroll.cool/WhiteRiverData/white_hole_conditions.html

### Automated Execution

**Cron Schedule**: Runs hourly on the hour
```bash
0 * * * * cd /home/frogmoses/WhiteRiverData && /home/frogmoses/WhiteRiverData/run_white_hole.sh >> /home/frogmoses/log/white_hole.log 2>&1
```

### Deployment Script (`run_white_hole.sh`)

1. Uses venv Python if available, falls back to system Python
2. Pulls latest code changes from GitHub (`git pull --ff-only`)
3. Runs `main.py` to generate HTML and chart files
4. Commits the 2 output files and pushes to GitHub (served via GitHub Pages)

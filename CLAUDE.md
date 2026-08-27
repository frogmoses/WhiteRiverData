# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Real-time water condition monitoring for White Hole on the White River near Bull Shoals Dam (Arkansas). Serves fishermen and boaters by tracking flow conditions for wading and boating safety.

## Commands

```bash
# Run main application (generates white_hole_conditions.html + vertical_flow_chart.png)
uv run python main.py

# Generate test HTML files with various water scenarios for visual inspection
uv run python generate_test_html.py

# Run test suite
uv run pytest

# Run tests with coverage report
uv run pytest --cov

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
├── main.py                  # Entry point: orchestrates fetch → calculate → format → save
├── data_fetcher.py          # Scrapes USACE Bull Shoals page (Playwright); parse_table_content() is the testable parser
├── forecast_fetcher.py      # Fetches/parses SWPA generation schedule; MW→CFS conversion
├── water_calculator.py      # get_flow, travel time, water state, conditions, timelines
├── fishing_report.py        # Flow-driven fishing report (Gaston's→Cranor's Island); standalone runner
├── formatters.py            # HTML and text output generation, chart embedding
├── chart_generator.py       # Matplotlib vertical dam→White Hole flow chart
├── landmarks.py             # Pinned GPS coordinates → river miles for reach landmarks
├── generate_test_html.py    # Generates HTML for 8 water scenarios (visual inspection)
├── run_white_hole.sh        # Production script: pulls code, runs main.py, commits and pushes output
├── index.html               # Redirect to white_hole_conditions.html for GitHub Pages root
├── pyproject.toml           # Project config, dependencies (uv)
├── pytest.ini               # Pytest configuration
├── tests/
│   ├── conftest.py                # Shared fixtures: 10 water condition datasets (naive datetimes)
│   ├── test_data_fetcher.py       # USACE parsing: timezone stamping, 2400 midnight rows, spillway columns
│   ├── test_forecast_fetcher.py   # SWPA schedule parsing and MW→CFS conversion
│   ├── test_water_calculator.py   # Flow calculations, trend/state logic, timelines
│   ├── test_fishing_report.py     # Bands, seasons, ETA math, spin/fly separation
│   ├── test_landmarks.py          # GPS-derived river miles, haversine, ordering
│   ├── test_formatters.py         # HTML/text output generation
│   └── test_integration.py        # End-to-end scenarios, incl. timezone-aware data
```

## Architecture

### Timezone Model (important)

Both data sources report **Central time** (`America/Chicago`):

- USACE tabular page: header says "Time CS/CDT"
- SWPA generation schedules: published in Central

Production datetimes are therefore **timezone-aware Central** end to end: `data_fetcher.DAM_TIMEZONE` and `forecast_fetcher.SWPA_TIMEZONE` stamp parsed timestamps, and `main.py` computes `current_time = datetime.now(DAM_TIMEZONE)`. The report displays Central times. Never compare these against a naive `datetime.now()` — the production host runs Eastern, and the pre-fix skew reported every arrival an hour early.

Test fixtures use naive datetimes throughout, which is fine as long as `data` and `current_time` passed into any function are both naive or both aware — never mixed within one call.

### Data Flow

```
main.py: generate_white_hole_summary(output_format, data, dataset_name, current_time)
    ↓
data_fetcher.py: get_bull_shoals_data() → Playwright fetch → parse_table_content(html) → list[dict]
    parse_dam_datetime() handles USACE's "2400" midnight encoding (rolls to next day)
    ↓
forecast_fetcher.py: get_swpa_forecast(current_time) → scrapes energy.gov/swpa/{day}.htm
    → hourly scheduled MW → mw_to_cfs() → future hours only
    ↓
water_calculator.py:
    get_flow(entry) → total_release (turbine + spillway), falls back to turbine_release
    calculate_travel_time(cfs) → hours (float)
    determine_water_state(data, current_time) → "rising"/"falling"/"stable"
    get_fishing_condition(cfs) → (wading_str, boating_str)
    get_recent_trend(data, current_time) → first-vs-last trend description
    forecast_conditions(data, current_time) → forecast description string
    calculate_timeline(data, current_time) → list[dict] for actual-water timeline
    calculate_forecast_timeline(swpa_data, current_time) → list[dict] for scheduled water
    ↓
formatters.py:
    generate_html_summary(...) → HTML string (banner + unified actual/forecast timeline)
    generate_text_summary(...) → plain text string
    include_chart_in_html(html, chart_path) → HTML with embedded chart
    save_html_summary(html, filename) → writes file
chart_generator.py:
    generate_vertical_river_chart(data, current_time, filename) → PNG
```

### Core Data Structure

Water data entries are dicts with: `date_time` (aware Central in production, naive in test fixtures), `elevation`, `tailwater`, `generation` (MWh), `turbine_release`, `spillway_release`, `total_release` (all CFS), and optional `error` flag. **Always read flow through `water_calculator.get_flow(entry)`**, never `entry['turbine_release']` directly — spillway/non-power releases must count toward downstream flow.

### Key Calculations and Parameter Locations

- **Flow selection** (`water_calculator.get_flow`): total_release with turbine_release fallback.
- **Travel time** (`water_calculator.calculate_travel_time`): 7-mile distance (`landmarks.WHITE_HOLE_MILE`), speed piecewise-linear between `SPEED_ANCHORS` — (band-midpoint CFS, mph) pairs at 3300 CFS per generator, 1.875–4.75 mph, clamped outside the anchored range. Sourced from His Place Resort's observational table; each band's average anchors at the band midpoint. Known modeling simplification: releases are treated as plugs that arrive whole — the source describes falling water as a gradual recession (~distance/2 hours for 85% fall-out), so partial cuts in generation actually recede more gradually than the step the model shows. A recession model is a candidate future enhancement.
- **Water state** (`water_calculator.determine_water_state`): compares first vs last of the 3 most recent arrival-adjusted entries; significant = >20% change AND >500 CFS.
- **Recent trend** (`water_calculator.get_recent_trend`): sorts the 6-hour window by time, compares earliest vs latest reading; 1.5×/1.2× + 500 CFS thresholds. Must stay direction-based — a previous spread-vs-average version reported steady declines as increases.
- **Fishing conditions** (`water_calculator.get_fishing_condition`): CFS thresholds 2000 / 5000 / 10000.
- **Timeline** (`water_calculator.calculate_timeline`): up to 4 entries, statuses current/incoming/arrived.
- **MW→CFS** (`forecast_fetcher.mw_to_cfs`): linear via `BSD_FULL_MW = 391`, `BSD_FULL_CFS = 26400` (validated ±5% against actuals), plus `BSD_MIN_FLOW_CFS = 250` base flow, floored at `BSD_MIN_TOTAL_CFS = 750` — the dam never runs below its minimum-flow release (~750 observed, ~850 per His Place). Entry `min_flow_cfs` is `cfs - generation_cfs` so the displayed breakdown always sums.
- **Forecast validity** (`forecast_fetcher.get_swpa_forecast`): rejects the day-of-week page (returns `[]`) if its `<title>` date doesn't match today — a stale page must not be re-anchored to the current date.
- **Staleness guard** (`main.py:STALE_DATA_HOURS = 3`): when the newest USACE reading is older than this, `stale_hours` flows into both formatters and renders a "DAM DATA DELAYED" warning.
- **Outage fallback** (`main.py:MAX_CACHE_AGE_HOURS = 24`): each successful production run saves the fetched data to `last_good_data.json` (`data_fetcher.save_last_good_data`, called only from `main.py.__main__`). When the live fetch fails (empty data or the error sentinel), `generate_white_hole_summary` falls back to `load_last_good_data` and renders the normal report with a red "LIVE DAM FEED UNAVAILABLE" banner (`feed_failed` flag through both formatters) — plus the stale banner once the cached data ages past `STALE_DATA_HOURS`. Cache older than 24 h, missing, corrupt, or error-flagged → the original error page. The cache file is **committed** by `run_white_hole.sh` (its `git stash -u` would destroy an untracked copy). Motivated by the Aug 27 2026 army.mil DNS outage, which blanked the page for hours despite the USACE web server being up.
- **Landmarks** (`landmarks.py`): pinned GPS coordinates (Brian's in-river points beside each landmark) for the 8 dam→White Hole locations; river miles are cumulative haversine chord distances along the chain, scaled so The White Hole lands exactly on `WHITE_HOLE_MILE = 7.0` (the raw chord sum ~6.73 mi undercuts the meanders; scaling preserves the His Place calibration). `LANDMARK_MILES` drives the chart's `points`/`point_labels` and the fishing report's `REACH_SPOTS`/`SPOT_COORDS` (Gaston's ≈ mile 4.09). Cranor's Island stays at an estimated 9.5 — no GPS chain below White Hole.

### Fishing Report (`fishing_report.py`)

A flow-driven fishing report for the Gaston's (mile 4) → Cranor's Island (mile 9.5) reach,
appended to the bottom of the HTML page. Design rules:

- **The repo's flow model is the driver.** All arrival ETAs come from
  `calculate_travel_time` scaled by river mile (`spot_arrival_times`); flow bands
  (`FLOW_BANDS`) align with `get_fishing_condition` thresholds (2000/5000/10000)
  plus a 16,500 split. The research brief's surge-front arrival table was
  deliberately discarded as conflicting.
- **Content source**: a Claude Cowork research brief (now deleted; its
  field-reference artifact is linked in Brian's memory) — fishing knowledge only:
  spots, rigs, baits, presentations, regulations.
- **Gear doctrine (strict)**: `~/CodeProjects/new-croton-fishing/reference/
  tackle-inventory.md` is the single inventory of record — **read it fresh each
  session and do not restate its contents here**: a stale snapshot of it in this
  file ("specs pending", stale rod count) caused real cross-repo drift, caught
  2026-08-26. Every item the report names must either trace to an inventory row
  or appear in `GEAR_CHECK` as an explicit buy/verify item — never present
  unowned gear as owned. Governance split (the rod rack's **Water column**):
  this repo prescribes from **AR**-designated rods plus whatever row the
  inventory marks as the AR travel rod; NY rods are the Croton fleet and
  off-limits. In exchange, the AR rows' *duty and respool cells* are THIS
  repo's to govern — when the species-program doctrine here changes a gear
  prescription, edit those inventory cells in the same session (the inventory's
  own header says AR prescriptions come from here); and when the inventory
  changes, re-audit `GEAR_CHECK`. Two standing facts by Brian's word: ALL fly gear is
  uninventoried (Recon 5-wt etc. — a future inventory section), and soft
  craw/hellgrammite plastics are NOT owned (the inventory's mis-ID'd
  utility-plastics row was corrected to match, 2026-08-26).
  Brian maintains the inventory file manually. Fresh bait is bought in
  Arkansas, not packed.
- **Year-round, collapsed by default**: the whole report is a `<details>`
  block (no `open` attribute; band + CFS shown in the summary line). During
  trip windows (`SEASON_MONTHS`: Mar–Apr spring, Sep–Oct fall) it shows that
  window's playbook; other months `get_effective_season` previews the
  upcoming window's playbook against current flow, labeled "Off-season
  preview". The standalone runner renders it expanded.
- **Spin and fly sections are strictly separate** — never merge their content;
  a test enforces vocabulary separation.
- **Within each section, advice splits into two species programs** (Brian's
  requested grouping, behaviorally validated): **browns** (trophy, all released,
  big baits near structure, 6–10 lb fluoro leaders) vs **rainbows & others**
  (numbers, keep 2 under 14 in, small baits in open drifts, 2–4 lb leaders;
  cutthroat/brook/tiger fish like rainbows here). Every band's first bullet in
  each program is its leader spec — keep it that way; tests assert it.
- **Cranor's Island** (Brian's name for the island below Cranor's White River
  Lodge, his downstream turnaround) is pinned at 36.333492497534266,
  -92.56191314472997 in `SPOT_COORDS`, rendered as a map link. The research
  brief called it "the Narrows" — that name found no corroboration and was
  dropped.
- **`RIGGING_REFERENCE`**: static how-to content (White River rig build incl.
  the tippet-ring cartridge system, bait prep, boat strategy — tie/drift/anchor,
  tied-boat presentations, fly-from-boat, etiquette) rendered
  as collapsible blocks after the gear check. Unchanged by flow/season; spin
  and fly blocks tagged and kept separate; boat handling and etiquette shared.
- **Standalone generation**: `uv run python fishing_report.py [--season fall|spring]
  [--cfs N] [--out file.html]` previews any band/season without live data.
- Regulations (Feb 2026): 2 rainbows under 14 in only, single hooking point with
  bait, one attended rod. Verified against AGFC Aug 2026; re-verify before edits.

### Data Sources

- USACE Bull Shoals tabular data: `https://www.swl-wc.usace.army.mil/pages/data/tabular/htm/bulsdam.htm`
  - Central time; midnight encoded as `2400` on the previous day's date; partial rows use `----`/`---` dashes
- SWPA generation schedule: `https://www.energy.gov/swpa/{mon..sun}.htm`
  - Hour-ending format (hour 1 = 00:00–01:00 Central); next-day schedules post ~5 p.m.; Friday posts Sat/Sun/Mon
- Travel time model: https://www.hisplaceresort.net/white-river-info

## Output Files

- `white_hole_conditions.html` — HTML report with headline banner, unified timeline (SWPA scheduled + actual dam readings), condition pills, and embedded chart
- `vertical_flow_chart.png` — Chart showing dam→White Hole flow progression with color gradient and generator labels
- Test variants: `white_hole_conditions_{scenario}.html` and `vertical_flow_chart_{scenario}.png`

## Testing

Uses pytest with fixtures in `tests/conftest.py` providing 10 water condition datasets (normal, rising, falling, high, low, flood, fluctuating, sudden_jump, sudden_drop, falling_water_scenario).

```bash
uv run pytest                                  # Run all tests
uv run pytest --cov                            # With coverage
uv run pytest tests/test_water_calculator.py   # Specific file
uv run pytest -k "test_forecast"               # Pattern match
uv run pytest -m unit                          # Only unit tests
uv run pytest -m integration                   # Only integration tests
```

### Pitfalls

- Tests run from a temporary directory (autouse `run_in_tmp_path` fixture in `conftest.py`), so generated charts/HTML stay out of the repo root. Running `main.py` or `generate_test_html.py` directly, however, does write into the repo root — restore `vertical_flow_chart.png`, `white_hole_conditions.html`, and (for `main.py`) `last_good_data.json` with `git checkout` if the run wasn't meant to be committed.
- Never mix naive and aware datetimes in one dataset/call (comparison raises `TypeError`).
- The remote `master` advances hourly (Pi output commits) — use `git pull --rebase` before pushing.
- `data_fetcher.get_error_data()` returns an error sentinel (single entry with `error: True`) used when scraping fails.
- The chart x-axis scales to the data (floor 5,000 CFS), so bar lengths are not comparable across different days' charts — the CFS labels carry the magnitude.

## Deployment

### Production Environment

- **Host**: Raspberry Pi (local network), runs **Eastern time** — safe only because all pipeline datetimes are timezone-aware Central
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
2. Stashes any leftover changes, pulls latest code from GitHub (`git pull --ff-only`)
3. Runs `main.py` to generate HTML and chart files
4. Commits the 2 output files (plus `last_good_data.json` when present) and pushes to GitHub (served via GitHub Pages)

Commit-message timestamps from the Pi are Eastern; the report content itself is Central.

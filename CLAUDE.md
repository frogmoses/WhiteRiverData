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
├── water_quality.py         # USGS tailwater temperature / dissolved oxygen (gauges 07054527, 07054502)
├── prediction_log.py        # Per-run CSV of model predictions (predictions.csv) for later validation
├── generate_test_html.py    # Generates HTML for 8 water scenarios (visual inspection)
├── suncalc.py               # NOAA sunrise/sunset (copied from new-croton-fishing) — the one copy the page, report and journal share
├── scripts/
│   └── build_journal.py         # journal/entries/*.md → journal/build/{digest.md,index.json,catches.csv,catches_report.md}
├── journal/                 # Trip notes + catch tables (see "The journal" below); build/ is gitignored
│   ├── README.md, TEMPLATE.md, entries/
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
│   ├── test_water_quality.py      # USGS JSON parsing, gauge preference, thresholds
│   ├── test_prediction_log.py     # Prediction row contents, CSV append, opt-in from main
│   ├── test_build_journal.py      # Journal parsing, catch vocabulary, model-row matching, crosswalk
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
forecast_fetcher.py: get_swpa_forecast(current_time) → scrapes energy.gov/swpa/{day}.htm for today AND tomorrow
    → validates the <pre> header date → hourly scheduled MW → mw_to_cfs() → future hours only
    ↓
water_calculator.py:
    get_flow(entry) → total_release (turbine + spillway), falls back to turbine_release
    calculate_travel_time(cfs) → hours (float)
    determine_water_state(data, current_time) → "rising"/"falling"/"stable"
    get_fishing_condition(cfs) → (wading_str, boating_str)
    get_recent_trend(data, current_time) → first-vs-last trend description
    forecast_conditions(data, current_time) → forecast description string
    calculate_timeline(data, current_time) → list[dict] for actual-water timeline
    calculate_forecast_timeline(swpa_data, current_time, previous_cfs) → list[dict] for scheduled water
    significant_change / recession_window / find_incoming_change → shared change + falling-water helpers
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
- **Travel time** (`water_calculator.calculate_travel_time`): 7-mile distance (`landmarks.WHITE_HOLE_MILE`), speed piecewise-linear between `SPEED_ANCHORS` — (band-midpoint CFS, mph) pairs at 3300 CFS per generator, 1.875–4.75 mph, clamped outside the anchored range. Sourced from His Place Resort's observational table; each band's average anchors at the band midpoint. Rising water is treated as a plug that arrives whole.
- **Falling water** (`water_calculator.recession_window`): a cut is a window, not a step — it starts when the front of the cut arrives at the speed of the *higher* flow it replaces and is fully down when the slower low-flow water has made the trip (`start = cut + tt(from_cfs)·mile/7`, `end = cut + tt(to_cfs)·mile/7`). The bracket contains His Place's rule of thumb (distance ÷ 2 ≈ hours to ~85% fall-out; their 15-mile/25,000 CFS example → 7.5 h sits inside the model's 3.3–8 h). `annotate_changes` tags every timeline/forecast item with `change` ('rising'/'falling'/None vs the item before it, seeded by `previous_cfs`) and `recession_start`; the page and the fishing report render drops as "falling ~start, down ~end" (windows under 10 min collapse to one time — `formatters.MIN_RECESSION_WINDOW`). The current-flow determination and the chart still use plug arrival.
- **Significant change** (`water_calculator.significant_change`): >20% AND >500 CFS, shared by water state, forecast wording, timeline tags, and the banner. `find_incoming_change` returns the first *incoming* timeline item that meets it — the banner's "RISING WATER arriving in ~N minutes" and the fishing report's RISE/DROP EN ROUTE must use that, never the nearest incoming plug (a same-level reading often sits ahead of the real change; live regression 2026-09-20).
- **Water state** (`water_calculator.determine_water_state`): compares first vs last of the 3 most recent arrival-adjusted entries; significant = >20% change AND >500 CFS.
- **Recent trend** (`water_calculator.get_recent_trend`): sorts the 6-hour window by time, compares earliest vs latest reading; 1.5×/1.2× + 500 CFS thresholds. Must stay direction-based — a previous spread-vs-average version reported steady declines as increases.
- **Fishing conditions** (`water_calculator.get_fishing_condition`): CFS thresholds 2000 / 5000 / 10000.
- **Timeline** (`water_calculator.calculate_timeline`): up to 4 actual entries, statuses current/incoming/arrived, plus `change`/`recession_start`. The page's unified table is chronological top to bottom (passed → at White Hole now → incoming → scheduled today → scheduled tomorrow under a weekday divider); the scheduled block shows the **whole** remaining schedule with consecutive same-CFS hours collapsed into runs (`formatters.group_forecast_runs`) — a 4-row cap once hid a 19,500 CFS afternoon behind four rows of morning min-flow. The banner's scheduled alert names the day's peak. Times on another day carry a weekday prefix (`water_calculator.clock`).
- **MW→CFS** (`forecast_fetcher.mw_to_cfs`): linear via `BSD_FULL_MW = 391`, `BSD_FULL_CFS = 26400` (validated ±5% against actuals), plus `BSD_MIN_FLOW_CFS = 250` base flow, floored at `BSD_MIN_TOTAL_CFS = 750` — the dam never runs below its minimum-flow release (~750 observed, ~850 per His Place). Entry `min_flow_cfs` is `cfs - generation_cfs` so the displayed breakdown always sums.
- **Forecast validity and horizon** (`forecast_fetcher.get_swpa_forecast`): fetches today's day-of-week page **and tomorrow's** (posted by ~5 p.m.; Friday covers the weekend), validating each against the date in the `<pre>` header line (`PROJECTED LOADING SCHEDULE <DAY> <MONTH> <DD>, <YYYY>`, `SCHEDULE_DATE_RE`). A page that is undated or dated for another day is dropped — the day pages persist for a week, so a missed post would otherwise serve last week's schedule. **Never validate against the `<title>`**: its date is the CMS render date and every one of the seven pages carries *today's* date there (verified 2026-09-20). Returns remaining today + all of tomorrow, chronological.
- **Staleness guard** (`main.py:STALE_DATA_HOURS = 3`): when the newest USACE reading is older than this, `stale_hours` flows into both formatters and renders a "DAM DATA DELAYED" warning.
- **Outage fallback** (`main.py:MAX_CACHE_AGE_HOURS = 24`): each successful production run saves the fetched data to `last_good_data.json` (`data_fetcher.save_last_good_data`, called only from `main.py.__main__`). When the live fetch fails (empty data or the error sentinel), `generate_white_hole_summary` falls back to `load_last_good_data` and renders the normal report with a red "LIVE DAM FEED UNAVAILABLE" banner (`feed_failed` flag through both formatters) — plus the stale banner once the cached data ages past `STALE_DATA_HOURS`. Cache older than 24 h, missing, corrupt, or error-flagged → the original error page. The cache file is **committed** by `run_white_hole.sh` (its `git stash -u` would destroy an untracked copy). Motivated by the Aug 27 2026 army.mil DNS outage, which blanked the page for hours despite the USACE web server being up.
- **Water quality** (`water_quality.get_water_quality`): one call to the USGS instantaneous-values service for gauges 07054527 (near Fairview, beside the Cane Island pin — preferred) and 07054502 (0.7 mi below the dam — fallback): water temperature and dissolved oxygen, 15-minute, **no discharge** (no downstream flow gauge exists for validating the travel model). Thresholds: DO <5 mg/L low / <6 marginal; temp <50°F cold / 50–62 prime / 62–68 warm / ≥68 hot (commonly cited trout ranges — verify before tightening). Rendered as pills under Current Conditions (`formatters.generate_water_quality_html`, age shown past `STALE_READING_HOURS`), in the text summary, and as the first lines of the fishing report's season notes (`fishing_report.water_notes`; a per-season fallback sentence when the fetch fails — the old fixed "~53–56°F" note contradicted the live gauge). Fetch failure never blanks the page.
- **Prediction log** (`prediction_log.py`): `main.__main__` passes `prediction_log_file=PREDICTION_LOG_FILE` for the HTML run only, appending one row per production run to `predictions.csv` (run time, latest reading, predicted White Hole CFS and its source reading, next significant actual change with its arrival or recession window, first significant scheduled change, water temp/DO, feed_failed). Committed by `run_white_hole.sh` (same `git stash -u` caveat as the cache). Purpose: the first validation dataset for the travel model — compare against timestamped on-site observations and later dam readings.
- **Landmarks** (`landmarks.py`): pinned GPS coordinates (Brian's in-river points beside each landmark) for the 8 dam→White Hole locations; river miles are cumulative haversine chord distances along the chain, scaled so The White Hole lands exactly on `WHITE_HOLE_MILE = 7.0` (the raw chord sum ~6.73 mi undercuts the meanders; scaling preserves the His Place calibration). `LANDMARK_MILES` drives the chart's `points`/`point_labels` and the fishing report's `REACH_SPOTS`/`SPOT_COORDS` (Gaston's ≈ mile 4.09). Cranor's Island stays at an estimated 9.5 — no GPS chain below White Hole.

### Fishing Report (`fishing_report.py`)

A flow-driven fishing report for the Gaston's (mile 4) → Cranor's Island (mile 9.5) reach,
appended to the bottom of the HTML page. Design rules:

- **The repo's flow model is the driver.** All arrival ETAs come from
  `calculate_travel_time` scaled by river mile (`spot_arrival_times`); flow bands
  (`FLOW_BANDS`) align with `get_fishing_condition` thresholds (2000/5000/10000)
  plus a 16,500 split. The research brief's surge-front arrival table was
  deliberately discarded as conflicting.
- **Content source**: the Aug 2026 research brief, `research/WHITE_RIVER_RESEARCH_BRIEF.md`
  (deleted 2026-08-25, restored 2026-09-21) — fishing knowledge only: spots, rigs, baits,
  presentations, regulations. Every claim in it carries a `[CONFIRMED]` / `[REPORTED]` /
  `[INFERRED]` / `[CONFLICT]` tag and §12 lists its sources; trace a report bullet to a
  tagged claim before changing it, and keep the tags when quoting. Its travel-time table
  (§3.3) and "the Narrows" name remain superseded by this repo's model and Cranor's Island.
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
- **Provenance (`SOURCES`, per-block `sources`, `EVIDENCE`)**: every band and season block
  names its sources and the page renders a "Sources:" line under it (`brief` links the
  restored research brief, whose claims are confidence-tagged; a REPORTED or INFERRED claim
  stays that until a journal row or a primary source confirms it — never present it as a
  named local source's statement). `EVIDENCE` maps
  `(band key, program)` → `{fish, dates, note}` and renders a "Journal: N fish on record"
  line under each program block, defaulting to "no fish on record yet". **After each trip**:
  run the journal builder, read `journal/build/catches_report.md`'s "Bands and programs
  with a fish behind them" table, and update `EVIDENCE` by hand in the same commit as any
  doctrine change it justifies. The builder never writes `EVIDENCE`.
- **Schedule outline (`fishing_report.schedule_outline`)**: one Timing bullet per scheduled
  day ("Rest of today at White Hole: …", "Tomorrow (Mon) at White Hole: …") listing every
  significant change with its White Hole ETA (falls as "falling ~start"), peak marked — the
  night-before read. Built on `water_calculator.group_forecast_runs`, which the page's
  timeline shares.
- **`RIGGING_REFERENCE`**: static how-to content (White River rig build incl.
  the tippet-ring cartridge system, bait prep, boat strategy — tie/drift/anchor,
  tied-boat presentations, fly-from-boat, etiquette) rendered
  as collapsible blocks after the gear check. Unchanged by flow/season; spin
  and fly blocks tagged and kept separate; boat handling and etiquette shared.
- **Standalone generation**: `uv run python fishing_report.py [--season fall|spring]
  [--cfs N] [--out file.html]` previews any band/season without live data.
- Regulations (Feb 2026): 2 rainbows under 14 in only, single hooking point with
  bait, one attended rod. Verified against AGFC Aug 2026; re-verify before edits.

### The journal — the feedback loop (`journal/`)

Same model as `new-croton-fishing/journal/` (its README and `build_journal.py` are the
reference; do not diverge from it without reason): one Markdown file per note in
`journal/entries/`, optional `---` front matter (date, title, tags, species, party, spot,
cfs_reported, water_temp_f, coords, sky, wind — any invented key is kept), a free body that
is never parsed, and a `## Catches` table in **this report's vocabulary**: species · size ·
time (Central HH:MM) · spot · water (your read: rising/falling/steady/dead low) · boat
(tie/drift/anchor/wade) · rig (WR rig/split-shot/float/direct/indicator/tightline/swing/dry) ·
bait · lost. `uv run python scripts/build_journal.py` rebuilds `journal/build/` (gitignored)
from scratch: the digest, `catches.csv`, and `catches_report.md`, which crosses every landed
row against `FLOW_BANDS × {browns, rainbows}` so each block of `BAND_CONTENT` shows the fish
behind it, and sets Brian's `water` read beside the model's `water_state` for that hour.

Rules that matter:
- **Not coupled to `predictions.csv`.** The builder attaches `model_*` columns by looking up
  the run at or before the catch time (≤ `MODEL_MATCH_HOURS` = 2 h); the log has no journal
  columns and never will. The model's flow is for White Hole; Gaston's/Cranor's are ±1 h.
- Species → program is derived (`brown` → browns, everything else → rainbows & others), the
  same split as the report. Rig and bait are classed by `RIG_CLASSES` / `BAIT_CLASSES`
  (order matters: "San Juan worm" is a nymph, "dry-dropper" is not a dropper loop); an
  unknown word warns, never fails. Malformed date/time/coords or an unterminated front
  matter block refuses the build.
- **The builder never edits the report.** Doctrine changes come from the rows, made by hand
  in `fishing_report.py` with the row count in the commit message (and the inventory's AR
  cells per the gear doctrine). Read `journal/build/digest.md` before any content change.
- Sunset for the windows (dawn/midday/dusk/night) is computed at the White Hole pin from
  `landmarks.py` via `suncalc.py` (repo root). `suncalc.light_windows` defines dawn as sunrise−1 h..+2 h and dusk as sunset−2 h..+1 h; the page's Current Conditions line and the report's "Low light today" Timing bullet use the same function (`fishing_report.light_windows_for`), so the three never disagree.
- Voice intake (Croton's ssh + local-model path) is not wired here; entries are hand-written.

### Data Sources

- USACE Bull Shoals tabular data: `https://www.swl-wc.usace.army.mil/pages/data/tabular/htm/bulsdam.htm`
  - Central time; midnight encoded as `2400` on the previous day's date; partial rows use `----`/`---` dashes
- SWPA generation schedule: `https://www.energy.gov/swpa/{mon..sun}.htm`
  - Hour-ending format (hour 1 = 00:00–01:00 Central); next-day schedules post ~5 p.m.; Friday posts Sat/Sun/Mon
- Travel time model: https://www.hisplaceresort.net/white-river-info

## Output Files

- `white_hole_conditions.html` — HTML report with headline banner, unified timeline (SWPA scheduled + actual dam readings), condition pills, and embedded chart
- `predictions.csv` — production-only prediction log (see Key Calculations)
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

- Tests run from a temporary directory (autouse `run_in_tmp_path` fixture in `conftest.py`), so generated charts/HTML stay out of the repo root, and **offline** (autouse `no_network` makes `requests.get` raise; tests that need a response monkeypatch it themselves). CI runs `uv run pytest` on every push/PR (`.github/workflows/tests.yml`) — the suite sat red for three weeks before that existed. Running `main.py` or `generate_test_html.py` directly, however, does write into the repo root — restore `vertical_flow_chart.png`, `white_hole_conditions.html`, and (for `main.py`) `last_good_data.json` with `git checkout` if the run wasn't meant to be committed.
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
4. Commits the 2 output files (plus `last_good_data.json` and `predictions.csv` when present) and pushes to GitHub (served via GitHub Pages)

Commit-message timestamps from the Pi are Eastern; the report content itself is Central.

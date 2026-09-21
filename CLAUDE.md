# CLAUDE.md

Guidance for Claude Code when working in this repository. The user-facing description of
the page and its workflows is in README.md; this file is about finding and changing code.

## Project Overview

Real-time water conditions for the White Hole on the White River below Bull Shoals Dam
(Arkansas), plus a flow-driven fishing report for the Gaston's → Cranor's Island reach. A
Raspberry Pi rebuilds the page hourly and commits it; GitHub Pages serves it. Two goals, in
Brian's words: predict the water at White Hole, and help him catch more and bigger trout on
this stretch. The 2026-09-20 adversarial review against those goals and its fixes are
summarised in the "Key Calculations" entries below.

## Entry points

| Command | Runs | Writes |
|---|---|---|
| `uv run python main.py` | `main.generate_white_hole_summary` twice (text, then html); `__main__` also saves the outage cache and appends the prediction log | `white_hole_conditions.html`, `vertical_flow_chart.png`, `last_good_data.json`, `predictions.csv` (repo root) |
| `uv run python fishing_report.py [--season fall\|spring] [--cfs N] [--out f]` | `fishing_report.main` → `generate_fishing_report` + `render_fishing_report_html`, expanded | `fishing_report.html` (gitignored) |
| `uv run python scripts/build_journal.py [--check]` | `build_journal.build` | `journal/build/{digest.md,index.json,catches.csv,catches_report.md}` (gitignored) |
| `uv run python scripts/audit_gear_inventory.py [inventory.md]` | `inventory_audit.audit` | stdout; exit 1 on drift, 2 when the inventory file is absent |
| `uv run python generate_test_html.py` | `generate_white_hole_summary` over 8 fixture scenarios | `white_hole_conditions_{scenario}.html` + charts (gitignored) |
| `uv run pytest` | the suite, offline, from a tmp dir | — |
| `./run_white_hole.sh` | production: pull, `main.py`, commit, push | see Deployment |

Setup: `uv sync --extra test` and `playwright install chromium` (only `main.py` and the
standalone fishing report without `--cfs` launch a browser).

## Repository Structure

```
WhiteRiverData/
├── main.py                  # Orchestrates fetch → calculate → format → save; staleness + outage fallback; prediction-log opt-in
├── data_fetcher.py          # USACE page via Playwright (+ DoH/host-resolver fallback); parse_table_content(); last-good cache
├── forecast_fetcher.py      # SWPA day pages (today + tomorrow), <pre>-header date validation, MW→CFS
├── water_calculator.py      # get_flow, travel time, recession window, significant_change, timelines, run grouping, clock()
├── water_quality.py         # USGS tailwater temperature / dissolved oxygen (07054527 preferred, 07054502 fallback)
├── prediction_log.py        # One CSV row per production run (predictions.csv)
├── fishing_report.py        # The fishing report: bands, programs, timing, provenance, band picker, rigging; standalone runner
├── formatters.py            # HTML/text page: banner, current conditions, arrivals table, chart embed
├── chart_generator.py       # Matplotlib vertical dam→White Hole chart (plug arrival per landmark)
├── landmarks.py             # Pinned GPS points → river miles (White Hole scaled to exactly 7.0)
├── suncalc.py               # NOAA sunrise/sunset (copied from new-croton-fishing) — the one copy page, report and journal share
├── inventory_audit.py       # Gear registries + drift audit against the Croton tackle inventory
├── generate_test_html.py    # Renders the fixture scenarios for visual inspection
├── run_white_hole.sh        # Production script (Pi): stash, pull --rebase, run, commit, push with one retry
├── index.html               # GitHub Pages root redirect
├── scripts/
│   ├── build_journal.py         # journal/entries/*.md → journal/build/ (venv-tier: imports the report's vocabulary)
│   └── audit_gear_inventory.py  # CLI for inventory_audit
├── journal/                 # Trip notes + catch tables (README.md, TEMPLATE.md, entries/); build/ is gitignored
├── research/                # WHITE_RIVER_RESEARCH_BRIEF.md (the tagged source layer) + archive/ (frozen snapshots, never sources)
├── last_good_data.json      # Outage cache, committed by the Pi each good run
├── predictions.csv          # Prediction log, committed by the Pi each run
├── .github/workflows/       # tests.yml (uv + pytest on push/PR), gitleaks.yml
├── pyproject.toml, uv.lock, pytest.ini
└── tests/
    ├── conftest.py                # 10 water-condition fixtures (naive datetimes); autouse: tmp cwd, network off
    ├── test_data_fetcher.py       # USACE parsing, 2400 rows, spillway columns, DNS fallback
    ├── test_forecast_fetcher.py   # <pre>-date validation, tomorrow fetch, MW→CFS
    ├── test_water_calculator.py   # Travel time, recession window, significant_change, timelines, clock
    ├── test_water_quality.py      # USGS JSON, gauge preference, thresholds
    ├── test_prediction_log.py     # Row contents, CSV append, opt-in from main
    ├── test_fishing_report.py     # Bands, programs, two-spool rule, timing, outline, provenance, band picker, section purity
    ├── test_build_journal.py      # Journal parsing, catch vocabulary, model-row matching, crosswalk
    ├── test_gear_inventory.py     # Registries; drift vs the inventory file when present
    ├── test_formatters.py         # Banner, arrivals table, water-quality block, sun line, text summary
    ├── test_landmarks.py
    └── test_integration.py        # End-to-end scenarios incl. timezone-aware data
```

## Architecture

### Timezone Model (important)

Both feeds report **Central time** (`America/Chicago`): the USACE page's header says
"Time CS/CDT" and SWPA publishes in Central. Production datetimes are therefore
timezone-aware Central end to end: `data_fetcher.DAM_TIMEZONE` and
`forecast_fetcher.SWPA_TIMEZONE` stamp parsed timestamps and `main.py` computes
`current_time = datetime.now(DAM_TIMEZONE)`. Never compare these against a naive
`datetime.now()`: the Pi runs Eastern, and the pre-fix skew reported every arrival an hour
early. Test fixtures are naive throughout, which is fine as long as `data` and
`current_time` in any one call are both naive or both aware.

### Data Flow

```
main.generate_white_hole_summary(output_format, data, dataset_name, current_time, prediction_log_file)
    ↓
data_fetcher.get_bull_shoals_data() → Playwright → parse_table_content(html) → list[dict]
    parse_dam_datetime() rolls USACE's "2400" midnight to the next day
    ERR_NAME_NOT_RESOLVED → resolve_via_doh() → retry with --host-resolver-rules
    failure → error sentinel → main falls back to load_last_good_data (≤ 24 h) with a feed_failed banner
    ↓
forecast_fetcher.get_swpa_forecast(current_time) → today's + tomorrow's day page, each validated
    against the <pre> header date → hourly MW → mw_to_cfs() → future hours only
    ↓
water_quality.get_water_quality(current_time) → USGS IV JSON → one reading (temp °F, DO mg/L, statuses)
    ↓
water_calculator:
    get_flow(entry)                         total_release, else turbine_release
    calculate_travel_time(cfs)              hours over WHITE_HOLE_MILE at the His Place band speeds
    significant_change(from, to)            "rising" / "falling" / None (>20% and >500 CFS)
    recession_window(cut, from, to, mile)   (start, fully_down) for a cut
    determine_water_state / get_recent_trend / forecast_conditions
    calculate_timeline(data, now)           ≤ 4 actual entries, status current/incoming/arrived, change, recession_start
    calculate_forecast_timeline(swpa, now, previous_cfs)
    find_incoming_change(timeline, cfs)     the first incoming item that is a significant change
    group_forecast_runs(forecast)           same-CFS hours collapsed into runs
    clock(dt, reference)                    "4:39 PM" / "Mon 4:39 PM"
    ↓
fishing_report.generate_fishing_report(cfs, now, timeline, forecast, water_quality) → dict (all bands)
    → render_fishing_report_html(report)
formatters.generate_html_summary(...) → page; arrival_rows()/render_arrivals() build the table
    generate_text_summary(...) → text; include_chart_in_html; save_html_summary
chart_generator.generate_vertical_river_chart(data, now, filename) → PNG
prediction_log.build_prediction_row(...) → append_prediction(row, file)   (production only)
```

### Core Data Structure

Water entries are dicts: `date_time` (aware Central in production, naive in fixtures),
`elevation`, `tailwater`, `generation` (MWh), `turbine_release`, `spillway_release`,
`total_release` (CFS), optional `error`. **Always read flow through
`water_calculator.get_flow(entry)`**, never `entry['turbine_release']`: spillway and
non-power releases count downstream. `elevation` and `tailwater` are parsed and currently
unused (an open item from the review).

### Key Calculations and Parameter Locations

- **Flow selection** (`water_calculator.get_flow`): total_release with turbine_release fallback.
- **Travel time** (`water_calculator.calculate_travel_time`): 7-mile distance (`landmarks.WHITE_HOLE_MILE`), speed piecewise-linear between `SPEED_ANCHORS` — (band-midpoint CFS, mph) pairs at 3300 CFS per generator, 1.875–4.75 mph, clamped outside the anchored range. Sourced from His Place Resort's observational table; each band's average anchors at the band midpoint. Rising water is treated as a plug that arrives whole. **Never validated against the river**: no discharge gauge exists near White Hole; `predictions.csv` plus on-site clock times are the intended check.
- **Falling water** (`water_calculator.recession_window`): a cut is a window, not a step — it starts when the front of the cut arrives at the speed of the *higher* flow it replaces and is fully down when the slower low-flow water has made the trip (`start = cut + tt(from_cfs)·mile/7`, `end = cut + tt(to_cfs)·mile/7`). The bracket contains His Place's rule of thumb (distance ÷ 2 ≈ hours to ~85% fall-out; their 15-mile/25,000 CFS example → 7.5 h sits inside the model's 3.3–8 h). `annotate_changes` tags every timeline/forecast item with `change` ('rising'/'falling'/None vs the item before it, seeded by `previous_cfs`) and `recession_start`; the page and the fishing report render drops as "falling ~start, down ~end" (windows under 10 min collapse to one time — `formatters.MIN_RECESSION_WINDOW`). The current-flow determination and the chart still use plug arrival.
- **Significant change** (`water_calculator.significant_change`): >20% AND >500 CFS, shared by water state, forecast wording, timeline tags, and the banner. `find_incoming_change` returns the first *incoming* timeline item that meets it — the banner's "RISING WATER arriving in ~N minutes" and the fishing report's RISE/DROP EN ROUTE must use that, never the nearest incoming plug (a same-level reading often sits ahead of the real change; live regression 2026-09-20).
- **Water state** (`water_calculator.determine_water_state`): compares first vs last of the 3 most recent arrival-adjusted entries by the significant-change rule.
- **Recent trend** (`water_calculator.get_recent_trend`): sorts the 6-hour window by time, compares earliest vs latest reading; 1.5×/1.2× + 500 CFS thresholds. Must stay direction-based — a previous spread-vs-average version reported steady declines as increases.
- **Fishing conditions** (`water_calculator.get_fishing_condition`): CFS thresholds 2000 / 5000 / 10000.
- **Arrivals at White Hole** (`formatters.arrival_rows` / `render_arrivals` over `calculate_timeline` + `group_forecast_runs`): the page's table is **keyed on arrival at White Hole**, not on the dam clock (the old "Time" column was the release hour, which read as nonsense next to "AT WHITE HOLE NOW" — Brian, 2026-09-21). One list: the water at White Hole now first ("since ~arrival"), then everything on its way in the order it gets there, measured ("released 7:00 AM", blue) and scheduled ("scheduled 2 PM" / "scheduled 12–2 PM", purple) rows interleaved; rows that already passed are dropped because the chart shows what is where; a scheduled hour the dam has already reported is dropped in favour of the reading. Falling rows sort and display by the start of the drop ("falling now" once started). Weekday divider when the arrival day changes. The banner's scheduled alert names the day's peak.
- **MW→CFS** (`forecast_fetcher.mw_to_cfs`): linear via `BSD_FULL_MW = 391`, `BSD_FULL_CFS = 26400` (validated ±5% against actuals), plus `BSD_MIN_FLOW_CFS = 250` base flow, floored at `BSD_MIN_TOTAL_CFS = 750` — the dam never runs below its minimum-flow release (~750 observed, ~850 per His Place). Entry `min_flow_cfs` is `cfs - generation_cfs` so a breakdown always sums.
- **Forecast validity and horizon** (`forecast_fetcher.get_swpa_forecast`): fetches today's day-of-week page **and tomorrow's** (posted by ~5 p.m.; Friday covers the weekend), validating each against the date in the `<pre>` header line (`PROJECTED LOADING SCHEDULE <DAY> <MONTH> <DD>, <YYYY>`, `SCHEDULE_DATE_RE`). A page that is undated or dated for another day is dropped — the day pages persist for a week, so a missed post would otherwise serve last week's schedule. **Never validate against the `<title>`**: its date is the CMS render date and every one of the seven pages carries *today's* date there (verified 2026-09-20). Returns remaining today + all of tomorrow, chronological.
- **Staleness guard** (`main.py:STALE_DATA_HOURS = 3`): when the newest USACE reading is older than this, `stale_hours` flows into both formatters and renders a "DAM DATA DELAYED" warning.
- **Outage fallback** (`main.py:MAX_CACHE_AGE_HOURS = 24`): each successful production run saves the fetched data to `last_good_data.json` (`data_fetcher.save_last_good_data`, called only from `main.py.__main__`). When the live fetch fails, `generate_white_hole_summary` falls back to `load_last_good_data` and renders the normal report with a red "LIVE DAM FEED UNAVAILABLE" banner (`feed_failed`), plus the stale banner once the cache ages past `STALE_DATA_HOURS`. Cache older than 24 h, missing, corrupt, or error-flagged → the error page. The cache is **committed** by `run_white_hole.sh` (its `git stash -u` would destroy an untracked copy). Motivated by the Aug 27 2026 army.mil DNS outage.
- **DNS fallback** (`data_fetcher.get_bull_shoals_data`): on `ERR_NAME_NOT_RESOLVED`, `resolve_via_doh` asks cloudflare-dns.com for the A record and Chromium is relaunched with `--host-resolver-rules=MAP host ip` (the existing `--ignore-certificate-errors` covers a mismatched cert on the pinned IP). Other errors are not retried. Added 2026-09-21 after the Pi's resolver failed army.mil; the Pi's resolver was also fixed (see Deployment).
- **Water quality** (`water_quality.get_water_quality`): one call to the USGS instantaneous-values service for gauges 07054527 (near Fairview, beside the Cane Island pin — preferred) and 07054502 (0.7 mi below the dam — fallback): water temperature and dissolved oxygen, 15-minute, **no discharge**. Thresholds: DO <5 mg/L low / <6 marginal; temp <50°F cold / 50–62 prime / 62–68 warm / ≥68 hot (commonly cited trout ranges — verify before tightening). Rendered as pills under Current Conditions (`formatters.generate_water_quality_html`, age shown past `STALE_READING_HOURS`), in the text summary, and as the first lines of the fishing report's season notes (`fishing_report.water_notes`; a per-season fallback sentence when the fetch fails — the old fixed "~53–56°F" note contradicted the live gauge). Fetch failure never blanks the page.
- **Sunrise/sunset** (`suncalc.light_windows` via `fishing_report.light_windows_for`): dawn = sunrise−1 h..+2 h, dusk = sunset−2 h..+1 h, at the White Hole pin; the Current Conditions line, the report's "Low light today" Timing bullet and the journal builder's windows all use this one function.
- **Prediction log** (`prediction_log.py`): `main.__main__` passes `prediction_log_file=PREDICTION_LOG_FILE` for the HTML run only, appending one row per production run to `predictions.csv` (run time, latest reading, predicted White Hole CFS and its source reading, next significant actual change with its arrival or recession window, first significant scheduled change, water temp/DO, feed_failed). Committed by `run_white_hole.sh`. Purpose: the first validation dataset for the travel model — compare against timestamped on-site observations (journal) and later dam readings.
- **Landmarks** (`landmarks.py`): pinned GPS coordinates (Brian's in-river points beside each landmark) for the 8 dam→White Hole locations; river miles are cumulative haversine chord distances along the chain, scaled so The White Hole lands exactly on `WHITE_HOLE_MILE = 7.0` (the raw chord sum ~6.73 mi undercuts the meanders; scaling preserves the His Place calibration). `LANDMARK_MILES` drives the chart's points and the fishing report's `REACH_SPOTS`/`SPOT_COORDS` (Gaston's ≈ mile 4.09). Cranor's Island stays at an estimated 9.5 — no GPS chain below White Hole.

### Fishing Report (`fishing_report.py`)

A flow-driven fishing report for the Gaston's (mile 4) → Cranor's Island (mile 9.5) reach,
appended to the bottom of the page. Design rules:

- **The repo's flow model is the driver.** All arrival ETAs come from
  `calculate_travel_time` scaled by river mile (`spot_arrival_times`,
  `spot_recession_windows`); flow bands (`FLOW_BANDS`) align with `get_fishing_condition`
  thresholds (2000/5000/10000) plus a 16,500 split. The research brief's surge-front
  arrival table was deliberately discarded as conflicting.
- **Content source**: the Aug 2026 research brief, `research/WHITE_RIVER_RESEARCH_BRIEF.md`
  (deleted 2026-08-25, restored 2026-09-21) — fishing knowledge only: spots, rigs, baits,
  presentations, regulations. Every claim in it carries a `[CONFIRMED]` / `[REPORTED]` /
  `[INFERRED]` / `[CONFLICT]` tag and §12 lists its sources; trace a report bullet to a
  tagged claim before changing it, and keep the tags when quoting. Its travel-time table
  (§3.3) and "the Narrows" name remain superseded by this repo's model and Cranor's Island.
- **Gear doctrine (strict)**: `~/CodeProjects/new-croton-fishing/reference/
  tackle-inventory.md` is the single inventory of record — **read it fresh each
  session and do not restate its contents here**: a stale snapshot of it in this
  file caused real cross-repo drift, caught 2026-08-26. Every item the report names must
  either trace to an inventory row or appear in `GEAR_CHECK` as an explicit buy/verify
  item — never present unowned gear as owned. Governance split (the rod rack's **Water
  column**): this repo prescribes from **AR**-designated rods plus whatever row the
  inventory marks as the AR travel rod; NY rods are the Croton fleet and off-limits. In
  exchange, the AR rows' *duty and respool cells* are THIS repo's to govern — when the
  species-program doctrine here changes a gear prescription, edit those inventory cells in
  the same session; and when the inventory changes, re-audit `GEAR_CHECK`. Two standing
  facts by Brian's word: ALL fly gear is uninventoried (Recon 5-wt etc. — a future
  inventory section), and soft craw/hellgrammite plastics are NOT owned. Brian maintains
  the inventory file manually; never edit it from here. Fresh bait is bought in Arkansas.
- **The drift test (2026-09-21)**: `inventory_audit.py` holds three registries —
  `OWNED_GEAR` (label, how the report mentions it, how its inventory row reads),
  `BUY_OR_VERIFY` (named as not owned) and `UNINVENTORIED` (fly gear) — and `GEAR_TOKENS`,
  the brand/hardware words that count as gear. `tests/test_gear_inventory.py` fails when the
  report names gear no registry covers, when a registered item is no longer mentioned, or —
  only where the inventory file exists (this workstation; skipped on the Pi and in CI) —
  when an owned item has no live row, matches only a "Pruned on repack day" paragraph, or
  its row says "failed inspection" without the gear check saying so.
  `scripts/audit_gear_inventory.py` runs the same audit from the shell (exit 1 on drift) for
  the Croton side. **Naming new gear in the report means registering it in the same
  commit.** The first run caught four drifts from the 2026-08-28 repack (pruned XPS ⅜ oz and
  gold/red spoon, "Countdown" for the inventory's "sinking swimmers", a bank sinker no
  longer listed) plus the marabou jigs' failed hook inspection, now a gear-check item.
- **Two-spool line rule (Brian's directive)**: exactly 4 lb (rainbow program) and 8 lb
  fluoro (browns program) everywhere, spin and fly tippet alike; 20/30 lb only as
  inventory/butt references; never introduce other pound-tests. Same principle for sinkers:
  one fixed starting bell per band (#10 · #8 · #7 · #6 · #4), variation handled by the
  on-water calibration rule. Tests enforce both.
- **Year-round, collapsed by default**: the whole report is a `<details>` block (no `open`
  attribute; band + CFS in the summary line). During trip windows (`SEASON_MONTHS`: Mar–Apr
  spring, Sep–Oct fall) it shows that window's playbook; other months
  `get_effective_season` previews the upcoming window's playbook, labeled "Off-season
  preview". The standalone runner renders it expanded.
- **Spin and fly sections are strictly separate** — never merge their content; a test
  enforces vocabulary separation per band panel. Section purity: spin/fly blocks contain
  tackle + presentation only; standalone where/when lines belong in Where-to-go and Timing;
  every bait bullet names its rig (White River rig / split-shot / float / tied direct);
  "bottom rig" is banned vocabulary.
- **Within each section, advice splits into two species programs** (Brian's requested
  grouping, behaviorally validated): **browns** (trophy, all released, big baits near
  structure, 8 lb fluoro) vs **rainbows & others** (numbers, keep 2 under 14 in, small baits
  in open drifts, 4 lb mono; cutthroat/brook/tiger fish like rainbows here). Every band's
  first bullet in each program is its leader spec — keep it that way; tests assert it.
- **The band picker** (`BAND_PICKER`, `_band_block`, `_band_picker_html`,
  `_band_panel_html`): ported from the archived White Hole Book's flow selector.
  `generate_fishing_report` builds `report["bands"]` — one block per `FLOW_BANDS` entry with
  the season's adds applied — and the renderer emits a tap-to-pick strip plus one
  `<div class="wh-band-panel" data-band=…>` per band (`<!-- band:key -->` marker before each;
  only the live band is unhidden and badged "at White Hole now"; an inline script toggles
  them, no persistence so a reload shows the live band). Where/boat/spin/fly and the
  per-program Journal lines are per panel; Timing, season notes, regulations, gear and
  rigging stay shared. Top-level `report["spin"]`/`["fly"]`/`["where"]` remain the live
  band's for compatibility.
- **Timing** (`build_timing`): the generic bullet, the day's low-light windows, RISE/DROP EN
  ROUTE from the first *significant* incoming plug (recession window for drops), the first
  SCHEDULED RISE/DROP with per-spot ETAs (windows for drops), then `schedule_outline` — one
  bullet per scheduled day ("Rest of today at White Hole: …", "Tomorrow (Mon) at White
  Hole: …") listing every significant change with its ETA, peak marked.
- **Provenance** (`SOURCES`, per-block `sources`, `EVIDENCE`): every band and season block
  names its sources and the page renders a "Sources:" line under it (`brief` links the
  restored research brief; a REPORTED or INFERRED claim stays that until a journal row or a
  primary source confirms it — never present it as a named local source's statement).
  `EVIDENCE` maps `(band key, program)` → `{fish, dates, note}` and renders a "Journal: N
  fish on record" line under each program block, defaulting to "no fish on record yet".
  **After each trip**: run the journal builder, read `journal/build/catches_report.md`'s
  "Bands and programs with a fish behind them" table, and update `EVIDENCE` by hand in the
  same commit as any doctrine change it justifies. The builder never writes `EVIDENCE`.
- **Cranor's Island** (Brian's name for the island below Cranor's White River Lodge, his
  downstream turnaround) is pinned at 36.333492497534266, -92.56191314472997 in
  `SPOT_COORDS`, rendered as a map link. The brief called it "the Narrows"; that name found
  no corroboration and was dropped.
- **`RIGGING_REFERENCE`**: static how-to content (White River rig build incl. the
  tippet-ring cartridge system with its SVG diagram `SPIN_RIG_SVG`, bait prep, boat strategy
  — tie/drift/anchor, tied-boat presentations, fly-from-boat, etiquette) rendered as
  collapsible blocks after the gear check. Unchanged by flow/season; spin and fly blocks
  tagged and kept separate; boat handling and etiquette shared.
- **`research/archive/`**: frozen snapshots, never sources — currently
  `WHITE_HOLE_BOOK_2026-08.html`, the claude.ai field-reference render of the brief plus an
  Aug 2026 inventory snapshot (stale on gear ownership, "bottom rig" wording, sculpin sizes,
  river miles). Its flow selector and rig diagram were ported into the report; nothing else
  from it should be.
- **Regulations**: dam → Norfork Access, 2 rainbows under 14 in, all other trout released
  immediately, single hooking point with bait, one attended rod; effective Feb 1 2026 "until
  further notice" (it replaced an emergency order — do not call it emergency management).
  Re-verified against AGFC 2026-09-20; re-verify before edits.

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
- Sunset for the windows (dawn/midday/dusk/night) comes from `suncalc.light_windows` at the
  White Hole pin — the same function the page and the report use.
- Voice intake (Croton's ssh + local-model path) is not wired here; entries are hand-written.

### Data Sources

- USACE Bull Shoals tabular data: `https://www.swl-wc.usace.army.mil/pages/data/tabular/htm/bulsdam.htm`
  — Central time; midnight encoded as `2400` on the previous day's date; partial rows use
  `----`/`---` dashes; the hourly CFS is derived from generation and the row timestamp
  behaves as the start of the hour it summarises.
- SWPA generation schedule: `https://www.energy.gov/swpa/{mon..sun}.htm` — hour-ending
  format (hour 1 = 00:00–01:00 Central); next-day schedules post ~5 p.m.; Friday posts
  Sat/Sun/Mon; the schedule date is in the `<pre>` header, never the `<title>`.
- USGS instantaneous values: `https://waterservices.usgs.gov/nwis/iv/` for sites 07054527
  and 07054502 (parameters 00010 temperature, 00300 dissolved oxygen; no discharge).
- Travel time model: https://www.hisplaceresort.net/white-river-info
- AGFC regulations: https://www.agfc.com/news/agfc-passes-new-trout-regulations-for-2026/

## Testing

Pytest with fixtures in `tests/conftest.py` providing 10 water-condition datasets (normal,
rising, falling, high, low, flood, fluctuating, sudden_jump, sudden_drop,
falling_water_scenario). Markers: `unit`, `integration`, `bug_fix`, `slow`.

```bash
uv run pytest tests/test_water_calculator.py   # one file
uv run pytest -k "test_forecast"               # pattern
uv run pytest -m integration                   # marker
```

CI (`.github/workflows/tests.yml`) runs the suite on every push and PR; the suite sat red
for three weeks before that existed.

### Pitfalls

- Tests run from a temporary directory (autouse `run_in_tmp_path`), so generated files stay
  out of the repo root, and **offline** (autouse `no_network` makes `requests.get` raise;
  tests that need a response monkeypatch it themselves). Running `main.py`,
  `fishing_report.py` without `--cfs`, or `generate_test_html.py` directly writes into the
  repo root — restore `vertical_flow_chart.png`, `white_hole_conditions.html`,
  `last_good_data.json` and `predictions.csv` with `git checkout` if the run was not meant
  to be committed.
- Never mix naive and aware datetimes in one dataset/call (comparison raises `TypeError`).
- The remote `master` advances hourly (Pi output commits) — `git pull --rebase` before
  pushing, and **do not push at the top of the hour** (see the push race under Deployment).
- `data_fetcher.get_error_data()` returns an error sentinel (single entry with `error: True`).
- The chart x-axis scales to the data (floor 5,000 CFS), so bar lengths are not comparable
  across days — the CFS labels carry the magnitude.
- Test helpers that build forecast dicts may omit `generators`/`wading`;
  `group_forecast_runs` tolerates that.

## Deployment

- **Host**: Raspberry Pi on the home LAN, project at `/home/frogmoses/WhiteRiverData`, log
  at `/home/frogmoses/log/white_hole.log`. Runs **Eastern time** — safe only because all
  pipeline datetimes are timezone-aware Central. Commit timestamps are Eastern; the page is
  Central.
- **Reach it**: `ssh briancarroll` (workstation alias → 192.168.1.181, user frogmoses).
- **Serving**: GitHub Pages from `master`; live at
  https://briancarroll.cool/WhiteRiverData/white_hole_conditions.html
- **Cron**: hourly on the hour —
  `0 * * * * cd /home/frogmoses/WhiteRiverData && ./run_white_hole.sh >> /home/frogmoses/log/white_hole.log 2>&1`
- **`run_white_hole.sh`**: venv Python if present; `git stash push -u`; `git pull --rebase`
  (not `--ff-only`: a stranded local output commit from a rejected push must ride on top of
  origin, keeping its `predictions.csv` row); `main.py`; `git add` the two output files plus
  `last_good_data.json` and `predictions.csv` when present; commit; `git push`, and on
  rejection `git pull --rebase && git push` once.
- **Push race**: the Pi pulls, runs and pushes at :00. A workstation push landing inside
  that window gets the Pi's push rejected (it happened 2026-09-21 06:00); the script now
  heals itself, but avoid pushing code at the top of the hour.
- **DNS**: the Pi runs Pi-hole + unbound on :53. Its Wi-Fi connection ("Dar-ling-a-ling",
  NetworkManager) was pointed at the router (192.168.1.1), which returns SERVFAIL for
  army.mil (DNSSEC) — 114 `ERR_NAME_NOT_RESOLVED` runs in the log through 2026-09-21. Fixed
  2026-09-21: `ipv4.dns "127.0.0.1 1.1.1.1"`, `ignore-auto-dns yes` (both families). The
  DoH fallback in `data_fetcher` is the second line of defence.

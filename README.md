# White River Data

Live water conditions and a flow-driven fishing report for the White Hole on the White
River below Bull Shoals Dam, Arkansas.

**The page:** https://briancarroll.cool/WhiteRiverData/white_hole_conditions.html

It rebuilds every hour on the hour. All times on it are Central, the dam's time.

## Reading the page

Top to bottom:

| Section | What it tells you |
|---|---|
| **Banner** | Can you wade right now, and is a rise or a drop on its way. A third line names the day's scheduled peak when high water is coming. |
| **Current Conditions** | The flow at White Hole now, wading and boating verdicts, sunrise and sunset with the low-light windows, and the tailwater's temperature and oxygen from the USGS gauge with a trout verdict (low oxygen means land fish fast). |
| **Arrivals at White Hole** | The water on its way to you, in the order it gets there. The top row is what is in front of you now. "Released" rows are the dam's hourly readings, "scheduled" rows are SWPA's generation plan for the rest of today and, once posted around 5 PM, tomorrow. Falling water shows as a window: when the level starts dropping and when it is fully down. |
| **Water Flow Progression** | The chart: which release is at which landmark right now, dam to White Hole, with map pins for each landmark. |
| **Fishing Report** | Collapsed by default. Timing around the generation changes, then a tap-to-pick strip with a playbook for every flow band: where to go, boat handling, spin and fly tackle split into a browns program and a rainbows program. Season notes, regulations, a gear check, and the rigging reference follow. |

Wading verdicts by flow at White Hole:

| CFS | Wading | Boating |
|---|---|---|
| under 2,000 | Excellent | Low water |
| 2,000 to 5,000 | Still wadable | Ideal |
| 5,000 to 10,000 | No wading | Ideal |
| over 10,000 | No wading | High water |

Travel times come from His Place Resort's observational table and have not yet been
checked against the river. Judge wading safety on site.

## After a trip

Write the trip up and let the fishing report learn from it:

```bash
cp journal/TEMPLATE.md journal/entries/2026-10-06-first-morning.md
```

Fill the front matter and the catch table (one row per fish, with the clock time), then:

```bash
uv run python scripts/build_journal.py
```

You get `journal/build/catches_report.md`: every fish with the flow model's numbers for
that hour attached, summarised by program, band, spot, rig, bait and light window, and
crossed against the report's flow-band and species-program blocks so each block of advice
shows how many fish stand behind it. The format is in `journal/README.md`.

Two things only you can add. Clock times for when a rise reached you or a drop started
and finished are the first real check the travel model has ever had; a line in the entry
body is enough. And fish counts per block go into `EVIDENCE` in `fishing_report.py` by
hand, from the catch report, so the page can say "Journal: 3 fish on record" instead of
"no fish on record yet".

## Occasionally

| Task | Command | You get |
|---|---|---|
| Preview the fishing report for any flow or season | `uv run python fishing_report.py --season fall --cfs 750` | `fishing_report.html`, expanded |
| Check the report's gear against the tackle inventory | `uv run python scripts/audit_gear_inventory.py` | Drift findings, or "0 findings"; exit 1 on drift |
| Render the page for eight water scenarios | `uv run python generate_test_html.py` | `white_hole_conditions_{scenario}.html` and charts |
| Run the tests | `uv run pytest` | 379 tests, offline |

The gear audit reads `~/CodeProjects/new-croton-fishing/reference/tackle-inventory.md`,
the single inventory of record, and is skipped where that file is absent.

## Running the page yourself

```bash
uv sync
playwright install chromium
uv run python main.py
```

That fetches the dam, the SWPA schedule and the USGS gauges live and writes
`white_hole_conditions.html` and `vertical_flow_chart.png` into the repo root, the same
files the Raspberry Pi commits every hour. Restore them with `git checkout` if the run was
not meant to be committed. Production runs also append one row of predictions to
`predictions.csv`, the log the travel model will eventually be checked against.

## Where the numbers come from

- **USACE** hourly releases at Bull Shoals Dam, the flow the whole page is built on.
- **SWPA** hourly generation schedules, converted to flow, for what is coming.
- **USGS** gauges below the dam for water temperature and dissolved oxygen. There is no
  discharge gauge near White Hole, which is why the model is unverified.
- **His Place Resort** for the travel-time table and the fall-out rule of thumb.
- The **research brief** in `research/WHITE_RIVER_RESEARCH_BRIEF.md` for the fishing
  content, every claim tagged by confidence. Each block on the page names its sources.

## License

Source code is MIT-licensed. The generated report content (the conditions page, chart,
and fishing report) is © Brian Carroll, all rights reserved — see [LICENSE](LICENSE).

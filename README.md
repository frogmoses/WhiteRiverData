# White River Data

Real-time water condition monitoring for White Hole on the White River near Bull Shoals Dam, Arkansas. Tracks flow conditions for wading and boating safety.

## Live Report

https://briancarroll.cool/WhiteRiverData/white_hole_conditions.html

Updates hourly via a Raspberry Pi that commits fresh data to this repo, served by GitHub Pages. All times on the report are Central time (the dam's timezone).

## Run Locally

```bash
uv sync
playwright install chromium
uv run python main.py
```

This scrapes current dam data, calculates conditions at White Hole, and produces:

| Output | Description |
|--------|-------------|
| `white_hole_conditions.html` | Report with headline banner, water timeline, SWPA generation forecast, and condition details |
| `vertical_flow_chart.png` | Chart showing dam-to-White Hole flow progression |

## Generate Test Scenarios

```bash
uv run python generate_test_html.py
```

Produces HTML and chart files for 8 water scenarios (normal, rising, falling, high, low, flood, fluctuating, sudden jump/drop). Open them in a browser to visually inspect output under different conditions.

## How It Works

Water released at Bull Shoals Dam takes roughly 1.5–4 hours (faster at higher flows) to travel 7 miles downstream to White Hole. The system:

1. Scrapes the USACE Bull Shoals Dam data page for hourly total releases (turbine + spillway, in CFS)
2. Calculates travel time based on flow rate using generator band interpolation
3. Determines which past release is currently affecting White Hole
4. Fetches the SWPA generation schedule to forecast scheduled releases and their arrival times
5. Reports wading/boating conditions and flags incoming changes

| CFS Range | Wading | Boating |
|-----------|--------|---------|
| < 2,000 | Excellent | Low water |
| 2,000 - 5,000 | Still wadable | Ideal |
| 5,000 - 10,000 | No wading | Ideal |
| > 10,000 | No wading | High water |

Travel-time speeds come from [His Place Resort's White River guide](https://www.hisplaceresort.net/white-river-info), which cautions that they are observational estimates — don't rely on this report alone to judge safe wading.

## Running Tests

```bash
uv run pytest              # run all tests
uv run pytest --cov        # with coverage report
```

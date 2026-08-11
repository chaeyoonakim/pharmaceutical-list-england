---
title: England Pharmacy Map
emoji: 💊
colorFrom: blue
colorTo: green
sdk: streamlit
sdk_version: "1.61.1"
app_file: dashboard/app.py
pinned: false
license: mit
short_description: Interactive map & stats for England's pharmacies
---

# pharmaceutical-list-england

Interactive map and statistics for England's community pharmacies, built on
the NHSBSA
[Consolidated Pharmaceutical List](https://opendata.nhsbsa.net/dataset/consolidated-pharmaceutical-list)
open data. Successor to
[pharmacy-analysis-with-open-data](https://github.com/chaeyoonakim/pharmacy-analysis-with-open-data),
rebuilt around a Streamlit dashboard.

## Features

- **Interactive England map** of every pharmacy in the Consolidated
  Pharmaceutical List, filterable by NHS region, Integrated Care Board (ICB),
  contract type, and quarter
- **Postcode near me** — type any England postcode and get the five nearest
  pharmacies with distance, walking time, open-now status, and a Google Maps
  walking-directions link
- **Area statistics** — quarterly pharmacy counts, true openings/closures
  (ODS-code churn between snapshots), and a next-year outlook from a
  transparent statistical trend model

## Quickstart

```bash
pip install -e ".[dashboard]"
streamlit run dashboard/app.py
```

That works immediately on a fresh clone: with no built dataset present the
app runs on a small bundled sample (and says so in a banner).

### Building the full dataset

On a machine with network access:

```bash
pip install -e ".[dev]"
python -m data.build_geo_lookup   # geocode all pharmacy postcodes (postcodes.io)
python -m data.build_dataset      # extract all quarters, enrich, write data/static/
```

Both commands are idempotent and cache aggressively (`cache/`, gitignored).
They write:

- `data/static/postcode_geo_lookup.csv.gz` — postcode → lat/lon/ICB/region
- `data/static/pharmacy_quarters.csv.gz` — one row per pharmacy-quarter

**Commit both files.** The dashboard (locally and on any deployment) then
needs no API access at all; only the optional "postcode near me" live lookup
and boundary outlines touch the network, and both degrade gracefully without
it.

### Adopting a newly published quarter

NHSBSA publishes one snapshot per quarter. Append its resource ID (e.g.
`CONSOL_PHARMACY_LIST_202526Q2`) to `quarterly_resources` in
`data/extract.py`, re-run the two build commands, and commit the refreshed
`data/static/` files. IDs the API doesn't recognise are logged and skipped,
so adding a not-yet-published quarter is harmless.

## Project layout

```
data/       all data-related scripts and files
  extract.py          NHSBSA API extractor (ported from the predecessor repo)
  transform.py        opening-hours + quarter parsing, tidy frame
  enrich.py           postcode → lat/lon/ICB/region join
  build_geo_lookup.py CLI: bulk-geocode every pharmacy postcode
  build_dataset.py    CLI: build the static dataset (--sample = offline)
  geo/                committed reference data (42 ICBs → 7 NHS regions)
  sample/             offline fixtures so the app and tests run anywhere
  static/             built dataset artifacts (committed once built)
src/        library code
  geo/                geocoding, ICB/region attribution, boundaries, distance
  stats/              area trends, churn, discontinuity detection, forecast
dashboard/  the Streamlit app (app.py + pure, tested logic modules)
tests/      offline test suite — no network needed, HTTP fully mocked
```

## Methodology & honest caveats

- **Counts** are unique pharmacy ODS codes per quarterly snapshot for the
  selected area.
- **Openings/closures** are set differences of ODS codes between consecutive
  snapshots — true churn, not just net count deltas.
- **Next-year outlook** fits a Theil–Sen line (median of pairwise slopes;
  OLS available as an option) to the quarterly counts and projects four
  quarters ahead with an approximate ±1.96·σ residual band, classified as
  growth / stable / decline at a ±1% projected-change threshold.
- **Snapshot discontinuities**: quarter-on-quarter jumps above 10% (the
  2025-26 Q1 snapshot jumps ~23% nationally vs 2024-25 Q4) are flagged in
  the UI as likely extraction artifacts, with a toggle to fit the trend on
  post-jump quarters only. Theil–Sen is the default because it is robust to
  a single level shift.
- The forecast is a trend extrapolation over at most ~12 observations — not
  a causal model. Its caveats are shown next to every projection.
- **No dispensing volumes are shown.** The source list contains none, and
  the predecessor project's "annual dispensing" figures were simulated
  (random draws) — they were deliberately not ported.

## Data sources & attribution

- Pharmacy data: NHSBSA Open Data Portal, Consolidated Pharmaceutical List
- Postcode geocoding: [postcodes.io](https://postcodes.io) (ONS/OS open data)
- ICB → NHS region reference: NHS England publications
- Boundaries (optional overlay): ONS Open Geography Portal

Contains public sector information licensed under the
[Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

## Deployment (Hugging Face Space)

The dashboard deploys as a Streamlit Space at
`https://huggingface.co/spaces/chaeyoona/pharmaceutical-list-england`,
kept in sync with `main` by `.github/workflows/sync-to-hf.yml`. The YAML
front-matter at the top of this README is the Space configuration.

One-time setup:

1. On [huggingface.co](https://huggingface.co/new-space) (logged in as
   `chaeyoona`), create a **Streamlit** Space named
   `pharmaceutical-list-england` (visibility your choice).
2. Create a Hugging Face access token with **write** scope
   (Settings → Access Tokens).
3. In this GitHub repo: Settings → Secrets and variables → Actions → add a
   repository secret named `HF_TOKEN` with that token.
4. Push to `main` (or run the "Sync to Hugging Face Space" workflow
   manually). The workflow force-pushes the repo to the Space, which then
   builds from `requirements.txt` and serves `dashboard/app.py`.

Build and commit `data/static/` first (see above) so the Space shows the
full dataset rather than the bundled sample. The Space needs no API keys:
only the live postcode lookup and boundary outlines call external services,
and both fall back gracefully.

## Development

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check .
mypy src data dashboard
pytest
```

## License

MIT — see [LICENSE](LICENSE).

# pharmaceutical-list-england

Interactive map and statistics for England's community pharmacies, built on the
NHSBSA [Consolidated Pharmaceutical List](https://opendata.nhsbsa.net/dataset/consolidated-pharmaceutical-list)
open data.

Successor to
[pharmacy-analysis-with-open-data](https://github.com/chaeyoonakim/pharmacy-analysis-with-open-data),
rebuilt around an interactive Streamlit dashboard.

## Features

- **Interactive England map** of every pharmacy in the Consolidated
  Pharmaceutical List, with filters for NHS region, Integrated Care Board
  (ICB), and contract type
- **Postcode near me** — type any England postcode and get the nearest
  pharmacies with distance, walking time, opening status, and directions
- **Area statistics** — quarterly pharmacy counts, openings and closures, and
  a next-year outlook from a transparent statistical trend model

## Project layout

```
data/       all data-related scripts and data files (extract, transform, enrich, build CLIs)
src/        library code (geo utilities, statistics)
dashboard/  the Streamlit app
tests/      offline test suite (no network required)
```

## Quickstart

```bash
pip install -e ".[dashboard]"
streamlit run dashboard/app.py
```

Full documentation lands with the dashboard build-out — see the open pull
requests.

## Data sources & attribution

- Pharmacy data: NHSBSA Open Data Portal, Consolidated Pharmaceutical List —
  released under the Open Government Licence v3.0
- Postcode geocoding: [postcodes.io](https://postcodes.io) (ONS/OS open data,
  OGL v3.0)
- Boundaries: ONS Open Geography Portal (OGL v3.0)

Contains public sector information licensed under the Open Government Licence v3.0.

## License

MIT — see [LICENSE](LICENSE).

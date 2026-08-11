"""Build the postcode → (lat, lon, ICB, NHS region) lookup via postcodes.io.

Usage (requires network — run on your own machine, not in a sandbox):

    python -m data.build_geo_lookup

Collects every unique postcode across all configured quarterly resources,
bulk-geocodes the ones not already in the lookup (idempotent — safe to re-run
after appending a new quarter), attributes the NHS region from the committed
ICB table, and writes ``data/static/postcode_geo_lookup.csv.gz``. Commit the
output so the dashboard needs no geocoding at runtime.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from data.extract import DataExtractor
from src.geo.icb_regions import icb_to_region
from src.geo.postcode_client import bulk_lookup
from src.geo.types import normalise_postcode

STATIC_DIR = Path(__file__).resolve().parent / "static"
OUTPUT_PATH = STATIC_DIR / "postcode_geo_lookup.csv.gz"

logger = logging.getLogger(__name__)


def collect_unique_postcodes(raw_by_resource: dict[str, pd.DataFrame]) -> list[str]:
    """All distinct normalised postcodes across the quarterly frames."""
    postcodes: set[str] = set()
    for raw in raw_by_resource.values():
        if "POST_CODE" in raw.columns:
            postcodes.update(
                normalise_postcode(p) for p in raw["POST_CODE"].dropna().astype(str)
            )
    postcodes.discard("")
    return sorted(postcodes)


def build_lookup_frame(postcodes: list[str]) -> pd.DataFrame:
    """Geocode postcodes and shape the result into the lookup schema."""
    geocoded = bulk_lookup(postcodes)
    rows = [
        {
            "postcode": info.postcode,
            "lat": info.lat,
            "lon": info.lon,
            "icb_code": info.icb_code or "",
            "icb_name": info.icb_name or "",
            "nhs_region": icb_to_region(info.icb_name) or "",
        }
        for info in geocoded.values()
    ]
    return pd.DataFrame(
        rows, columns=["postcode", "lat", "lon", "icb_code", "icb_name", "nhs_region"]
    )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    extractor = DataExtractor()
    raw_by_resource = extractor.extract_all_quarters()
    if not raw_by_resource:
        logger.error(
            "No quarterly data could be fetched — check network access to "
            "opendata.nhsbsa.net"
        )
        return 1

    postcodes = collect_unique_postcodes(raw_by_resource)
    logger.info(f"{len(postcodes)} unique postcodes across all quarters")

    existing = pd.DataFrame()
    if OUTPUT_PATH.exists():
        existing = pd.read_csv(OUTPUT_PATH)
        known = set(existing["postcode"].map(normalise_postcode))
        postcodes = [p for p in postcodes if p not in known]
        logger.info(f"{len(known)} already geocoded; {len(postcodes)} new to fetch")

    if postcodes:
        fresh = build_lookup_frame(postcodes)
        combined = (
            pd.concat([existing, fresh], ignore_index=True)
            .drop_duplicates("postcode")
            .sort_values("postcode")
        )
    else:
        combined = existing

    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    combined.to_csv(OUTPUT_PATH, index=False, compression="gzip")
    logger.info(f"Wrote {len(combined)} postcodes to {OUTPUT_PATH}")
    missing_region = int((combined["nhs_region"] == "").sum())
    if missing_region:
        logger.warning(
            f"{missing_region} postcodes have no NHS region attribution — "
            "check data/geo/icb_region_lookup.csv against the ICB names in "
            "the postcodes.io response"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Build the static analysis-ready dataset the dashboard ships with.

Usage:

    python -m data.build_dataset            # full build (needs network)
    python -m data.build_dataset --sample   # offline build from fixtures

Extracts every configured quarter, tidies it, joins the postcode geo lookup,
and writes ``data/static/pharmacy_quarters.csv.gz`` — commit the output so
the dashboard (and the Hugging Face Space) needs no API access at runtime.
Run ``python -m data.build_geo_lookup`` first for a full build so geocoding
coverage is complete.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd

from data.enrich import attach_geo
from data.extract import DataExtractor
from data.transform import DataTransformer
from src.geo.lookup_store import load_lookup

DATA_DIR = Path(__file__).resolve().parent
STATIC_DIR = DATA_DIR / "static"
OUTPUT_PATH = STATIC_DIR / "pharmacy_quarters.csv.gz"
SAMPLE_PHARMACIES = DATA_DIR / "sample" / "sample_pharmacies.csv"

logger = logging.getLogger(__name__)


def load_sample_raw() -> dict[str, pd.DataFrame]:
    """The committed sample fixtures, split per quarterly resource."""
    df = pd.read_csv(SAMPLE_PHARMACIES)
    return {
        resource_id: group.drop(columns=["resource_id"]).reset_index(drop=True)
        for resource_id, group in df.groupby("resource_id", sort=False)
    }


def build(sample: bool = False) -> pd.DataFrame:
    """Extract → tidy → enrich; returns the final frame."""
    if sample:
        raw_by_resource = load_sample_raw()
    else:
        raw_by_resource = DataExtractor().extract_all_quarters()
        if not raw_by_resource:
            raise RuntimeError(
                "No quarterly data could be fetched — check network access to "
                "opendata.nhsbsa.net, or use --sample for the offline fixtures"
            )

    tidy = DataTransformer().build_tidy_frame(raw_by_resource)
    lookup = load_lookup()
    logger.info(f"Using {lookup.provenance} postcode lookup")
    return attach_geo(tidy, lookup.frame)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sample",
        action="store_true",
        help="build from the committed sample fixtures (no network)",
    )
    args = parser.parse_args(argv)

    enriched = build(sample=args.sample)
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    enriched.to_csv(OUTPUT_PATH, index=False, compression="gzip")
    logger.info(
        f"Wrote {len(enriched)} pharmacy-quarter rows "
        f"({enriched['quarter_label'].nunique()} quarters) to {OUTPUT_PATH}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Dataset loading and filtering for the dashboard (pure, testable)."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
STATIC_DATASET = REPO_ROOT / "data" / "static" / "pharmacy_quarters.csv.gz"
SAMPLE_PHARMACIES = REPO_ROOT / "data" / "sample" / "sample_pharmacies.csv"
SAMPLE_LOOKUP = REPO_ROOT / "data" / "sample" / "sample_geo_lookup.csv"

ALL_ENGLAND = "All England"
ALL_ICBS = "All ICBs"

logger = logging.getLogger(__name__)


def load_dataset() -> tuple[pd.DataFrame, str]:
    """The enriched pharmacy-quarters frame plus its provenance.

    Prefers the built static dataset; falls back to building from the
    committed sample fixtures in-process so a fresh clone always works.
    Provenance is "static" or "sample" (drives the dashboard banner).
    """
    if STATIC_DATASET.exists():
        df = pd.read_csv(STATIC_DATASET, parse_dates=["quarter_date"])
        logger.info(f"Loaded {len(df)} rows from static dataset")
        return df, "static"

    from data.build_dataset import build

    df = build(sample=True)
    df["quarter_date"] = pd.to_datetime(df["quarter_date"])
    logger.info(f"Built {len(df)} rows from sample fixtures")
    return df, "sample"


def quarter_options(df: pd.DataFrame) -> list[str]:
    """Quarter labels, newest first."""
    ordered = (
        df[["quarter_label", "quarter_date"]]
        .drop_duplicates()
        .sort_values("quarter_date", ascending=False)
    )
    return [str(label) for label in ordered["quarter_label"]]


def region_options(df: pd.DataFrame) -> list[str]:
    """ "All England" plus the regions present in the data."""
    regions = sorted(
        r for r in df["nhs_region"].dropna().unique() if r and r != "Unknown"
    )
    return [ALL_ENGLAND, *regions]


def icb_options(df: pd.DataFrame, region: str) -> list[str]:
    """ "All ICBs" plus the ICBs present in the selected region."""
    scope = df if region == ALL_ENGLAND else df[df["nhs_region"] == region]
    icbs = sorted(i for i in scope["icb_name"].dropna().unique() if i)
    return [ALL_ICBS, *icbs]


def contract_type_options(df: pd.DataFrame) -> list[str]:
    return sorted(c for c in df["contract_type"].dropna().unique() if c)


def filter_area(
    df: pd.DataFrame,
    region: str = ALL_ENGLAND,
    icb: str = ALL_ICBS,
    contract_types: list[str] | None = None,
) -> pd.DataFrame:
    """Rows for the selected area across ALL quarters (trends need history)."""
    result = df
    if region != ALL_ENGLAND:
        result = result[result["nhs_region"] == region]
    if icb != ALL_ICBS:
        result = result[result["icb_name"] == icb]
    if contract_types:
        result = result[result["contract_type"].isin(contract_types)]
    return result


def quarter_slice(df: pd.DataFrame, quarter_label: str) -> pd.DataFrame:
    """One quarter's rows (for the map)."""
    return df[df["quarter_label"] == quarter_label]


def mappable(df: pd.DataFrame) -> pd.DataFrame:
    """Rows with coordinates (the map cannot place the rest)."""
    return df[df["lat"].notna() & df["lon"].notna()]

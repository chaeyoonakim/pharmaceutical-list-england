"""ICB → NHS region attribution from the committed reference table.

Keys on the ICB *name* because postcodes.io reliably returns names while the
code field has drifted (ccg/icb); names are matched after normalisation so
"NHS Devon Integrated Care Board", "NHS Devon ICB", and "Devon" all resolve.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import pandas as pd

ICB_REGION_CSV = (
    Path(__file__).resolve().parent.parent.parent
    / "data"
    / "geo"
    / "icb_region_lookup.csv"
)

NHS_REGIONS = [
    "North East and Yorkshire",
    "North West",
    "Midlands",
    "East of England",
    "London",
    "South East",
    "South West",
]


def _normalise_icb_name(name: str) -> str:
    """Reduce an ICB name to its distinctive core for matching."""
    text = name.strip().lower()
    text = re.sub(r"^nhs\s+", "", text)
    text = re.sub(r"\s+integrated care board$", "", text)
    text = re.sub(r"\s+icb$", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return text


@lru_cache(maxsize=1)
def _region_by_normalised_name() -> dict[str, str]:
    df = pd.read_csv(ICB_REGION_CSV)
    return {
        _normalise_icb_name(str(row.icb_name)): str(row.nhs_region)
        for row in df.itertuples()
    }


def icb_to_region(icb_name: str | None) -> str | None:
    """NHS region for an ICB name, or None when unknown."""
    if not icb_name or not isinstance(icb_name, str):
        return None
    return _region_by_normalised_name().get(_normalise_icb_name(icb_name))


def all_icb_names() -> list[str]:
    """The 42 canonical ICB names from the reference table."""
    return sorted(pd.read_csv(ICB_REGION_CSV)["icb_name"].tolist())

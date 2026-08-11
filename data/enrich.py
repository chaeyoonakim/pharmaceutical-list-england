"""Geographic enrichment: join the postcode geo lookup onto the tidy frame."""

from __future__ import annotations

import logging

import pandas as pd

from src.geo.regions_fallback import region_from_postcode
from src.geo.types import normalise_postcode

logger = logging.getLogger(__name__)

GEO_COLUMNS = ["lat", "lon", "icb_code", "icb_name", "nhs_region"]


def attach_geo(tidy: pd.DataFrame, lookup: pd.DataFrame) -> pd.DataFrame:
    """Add lat/lon/ICB/region columns to a tidy pharmacy frame.

    Joins on normalised postcode. Rows whose postcode is missing from the
    lookup keep NaN coordinates (they are excluded from the map but stay in
    the statistics) and get their NHS region from the postcode-prefix
    heuristic so regional counts remain complete.
    """
    if tidy.empty:
        return tidy.copy()

    enriched = tidy.copy()
    enriched["postcode_norm"] = enriched["postcode"].map(normalise_postcode)

    lookup_indexed = lookup.copy()
    lookup_indexed["postcode_norm"] = lookup_indexed["postcode"].map(normalise_postcode)
    lookup_indexed = lookup_indexed.drop_duplicates("postcode_norm")[
        ["postcode_norm", *GEO_COLUMNS]
    ]

    enriched = enriched.merge(lookup_indexed, on="postcode_norm", how="left")

    unmatched = enriched["lat"].isna()
    if unmatched.any():
        enriched.loc[unmatched, "nhs_region"] = enriched.loc[unmatched, "postcode"].map(
            region_from_postcode
        )
        logger.info(
            f"{int(unmatched.sum())} of {len(enriched)} rows lack geocoding; "
            "regions filled from postcode-prefix heuristic"
        )

    enriched = enriched.drop(columns=["postcode_norm"])
    return enriched

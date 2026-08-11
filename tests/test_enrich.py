"""Tests for data.enrich — geo join and fallback behaviour."""

from __future__ import annotations

import pandas as pd

from data.enrich import attach_geo
from data.transform import DataTransformer


def _tidy(sample_raw_by_resource: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return DataTransformer().build_tidy_frame(sample_raw_by_resource)


def test_join_covers_all_fixture_rows(
    sample_raw_by_resource: dict[str, pd.DataFrame],
    sample_geo_lookup: pd.DataFrame,
) -> None:
    enriched = attach_geo(_tidy(sample_raw_by_resource), sample_geo_lookup)
    # Every fixture postcode is in the fixture lookup, so no NaN coordinates.
    assert enriched["lat"].notna().all()
    assert enriched["nhs_region"].notna().all()
    assert set(enriched.columns) >= {"lat", "lon", "icb_name", "nhs_region"}


def test_regions_consistent_per_pharmacy(
    sample_raw_by_resource: dict[str, pd.DataFrame],
    sample_geo_lookup: pd.DataFrame,
) -> None:
    enriched = attach_geo(_tidy(sample_raw_by_resource), sample_geo_lookup)
    per_pharmacy = enriched.groupby("ods_code")["nhs_region"].nunique()
    assert (per_pharmacy == 1).all()
    manchester = enriched[enriched["ods_code"] == "FTEST01"]
    assert (manchester["nhs_region"] == "North West").all()


def test_unmatched_postcode_falls_back_to_heuristic(
    sample_raw_by_resource: dict[str, pd.DataFrame],
    sample_geo_lookup: pd.DataFrame,
) -> None:
    tidy = _tidy(sample_raw_by_resource)
    # Remove Manchester postcodes from the lookup to force the fallback.
    lookup = sample_geo_lookup[
        ~sample_geo_lookup["postcode"].str.startswith("M")
    ].copy()
    enriched = attach_geo(tidy, lookup)
    manchester = enriched[enriched["ods_code"] == "FTEST01"]
    assert manchester["lat"].isna().all()  # excluded from map
    assert (manchester["nhs_region"] == "North West").all()  # kept in stats


def test_empty_frame() -> None:
    lookup = pd.DataFrame(
        columns=["postcode", "lat", "lon", "icb_code", "icb_name", "nhs_region"]
    )
    assert attach_geo(pd.DataFrame(), lookup).empty

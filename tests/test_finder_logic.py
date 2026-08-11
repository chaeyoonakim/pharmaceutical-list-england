"""Tests for dashboard.finder_logic and dashboard.data_access."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from dashboard import data_access
from dashboard.finder_logic import (
    google_maps_walking_url,
    is_open_now,
    nearest_pharmacies,
)
from data.enrich import attach_geo
from data.transform import DataTransformer
from src.geo.types import GeoPoint

MONDAY_NOON = datetime(2026, 8, 10, 12, 0)  # a Monday
MONDAY_LATE = datetime(2026, 8, 10, 22, 30)
SUNDAY_NOON = datetime(2026, 8, 9, 12, 0)


@pytest.fixture(scope="module")
def enriched(
    sample_raw_by_resource: dict[str, pd.DataFrame],
    sample_geo_lookup: pd.DataFrame,
) -> pd.DataFrame:
    tidy = DataTransformer().build_tidy_frame(sample_raw_by_resource)
    return attach_geo(tidy, sample_geo_lookup)


@pytest.fixture(scope="module")
def latest_quarter(enriched: pd.DataFrame) -> pd.DataFrame:
    latest = data_access.quarter_options(enriched)[0]
    return data_access.quarter_slice(enriched, latest)


class TestIsOpenNow:
    def test_open_within_hours(self) -> None:
        assert is_open_now("09:00-17:30", MONDAY_NOON)

    def test_closed_outside_hours(self) -> None:
        assert not is_open_now("09:00-17:30", MONDAY_LATE)

    def test_split_day_gap(self) -> None:
        assert not is_open_now("09:00-12:00,14:00-17:00", datetime(2026, 8, 10, 13, 0))
        assert is_open_now("09:00-12:00,14:00-17:00", datetime(2026, 8, 10, 15, 0))

    def test_closed_string(self) -> None:
        assert not is_open_now("Closed", MONDAY_NOON)
        assert not is_open_now(None, MONDAY_NOON)

    def test_overnight_open_until_midnight(self) -> None:
        assert is_open_now("22:00-06:00", datetime(2026, 8, 10, 23, 0))
        assert not is_open_now("22:00-06:00", MONDAY_NOON)


class TestNearestPharmacies:
    def test_ranking_from_manchester(self, latest_quarter: pd.DataFrame) -> None:
        # M1 1AE city centre: Manchester pharmacies must come first.
        user = GeoPoint(53.4794, -2.2453)
        result = nearest_pharmacies(user, latest_quarter, n=5, now=MONDAY_NOON)
        assert len(result) == 5
        assert result["distance_km"].is_monotonic_increasing
        assert result.iloc[0]["postcode"].startswith("M")
        # Piccadilly Pharmacy is at the user's own postcode → distance ~0.
        assert result.iloc[0]["distance_km"] < 0.1

    def test_open_now_only_filters(self, latest_quarter: pd.DataFrame) -> None:
        user = GeoPoint(53.4794, -2.2453)
        all_result = nearest_pharmacies(user, latest_quarter, n=10, now=SUNDAY_NOON)
        open_result = nearest_pharmacies(
            user, latest_quarter, n=10, open_now_only=True, now=SUNDAY_NOON
        )
        # On a Sunday only the 07:00-23:00 pharmacies are open ("std" profile
        # is Closed on Sundays), so the open-now list must be smaller.
        assert len(open_result) < len(all_result)
        assert open_result["open_now"].all()

    def test_maps_url_encodes_address(self, latest_quarter: pd.DataFrame) -> None:
        user = GeoPoint(53.4794, -2.2453)
        result = nearest_pharmacies(user, latest_quarter, n=1, now=MONDAY_NOON)
        url = result.iloc[0]["maps_url"]
        assert url.startswith("https://www.google.com/maps/dir/?api=1")
        assert "travelmode=walking" in url
        assert "origin=53.4794,-2.2453" in url
        assert " " not in url

    def test_empty_candidates(self) -> None:
        empty = pd.DataFrame(columns=["lat", "lon", "name", "address", "postcode"])
        result = nearest_pharmacies(GeoPoint(53.0, -2.0), empty)
        assert result.empty


class TestGoogleMapsUrl:
    def test_url_shape(self) -> None:
        url = google_maps_walking_url(
            GeoPoint(53.48, -2.24), "1 Piccadilly Gardens, Manchester", "M1 1AE"
        )
        assert "destination=1+Piccadilly+Gardens%2C+Manchester%2C+M1+1AE" in url


class TestDataAccess:
    def test_quarter_options_newest_first(self, enriched: pd.DataFrame) -> None:
        options = data_access.quarter_options(enriched)
        assert options[0] == "2025-26 Q1"
        assert options[-1] == "2022-23 Q2"
        assert len(options) == 12

    def test_region_options(self, enriched: pd.DataFrame) -> None:
        options = data_access.region_options(enriched)
        assert options[0] == data_access.ALL_ENGLAND
        assert "North West" in options
        assert "Unknown" not in options

    def test_icb_options_dependent_on_region(self, enriched: pd.DataFrame) -> None:
        london_icbs = data_access.icb_options(enriched, "London")
        assert london_icbs[0] == data_access.ALL_ICBS
        assert "NHS North West London Integrated Care Board" in london_icbs
        assert "NHS Greater Manchester Integrated Care Board" not in london_icbs

    def test_filter_area_by_icb(self, enriched: pd.DataFrame) -> None:
        filtered = data_access.filter_area(
            enriched,
            region="North West",
            icb="NHS Greater Manchester Integrated Care Board",
        )
        assert set(filtered["nhs_region"].unique()) == {"North West"}
        assert filtered["ods_code"].str.startswith("FTEST").all()

    def test_filter_by_contract_type(self, enriched: pd.DataFrame) -> None:
        appliance = data_access.filter_area(enriched, contract_types=["Appliance"])
        assert set(appliance["contract_type"].unique()) == {"Appliance"}

    def test_load_dataset_sample_fallback(self) -> None:
        df, provenance = data_access.load_dataset()
        # In the test environment no static build exists.
        assert provenance in {"sample", "static"}
        assert {"ods_code", "lat", "lon", "nhs_region", "quarter_label"} <= set(
            df.columns
        )

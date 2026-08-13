"""Tests for dashboard.area_builder."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from dashboard.area_builder import (
    CustomArea,
    build_export_zip,
    deserialise_areas,
    filter_by_area,
    serialise_areas,
    validate_area_name,
)
from data.enrich import attach_geo
from data.transform import DataTransformer


@pytest.fixture(scope="module")
def enriched(
    sample_raw_by_resource: dict[str, pd.DataFrame],
    sample_geo_lookup: pd.DataFrame,
) -> pd.DataFrame:
    tidy = DataTransformer().build_tidy_frame(sample_raw_by_resource)
    return attach_geo(tidy, sample_geo_lookup)


class TestValidateAreaName:
    def test_empty_name_rejected(self) -> None:
        assert validate_area_name("", {}) is not None
        assert validate_area_name("   ", {}) is not None

    def test_duplicate_name_rejected(self) -> None:
        existing = {"North Cluster": CustomArea("North Cluster", ("A",))}
        assert validate_area_name("North Cluster", existing) is not None

    def test_new_name_accepted(self) -> None:
        assert validate_area_name("New Area", {}) is None


class TestFilterByArea:
    def test_combines_multiple_icbs(self, enriched: pd.DataFrame) -> None:
        icbs = tuple(enriched["icb_name"].dropna().unique()[:2])
        area = CustomArea(name="Combined", icb_names=icbs)
        filtered = filter_by_area(enriched, area)
        assert not filtered.empty
        assert set(filtered["icb_name"].unique()) <= set(icbs)

    def test_unknown_icb_yields_empty(self, enriched: pd.DataFrame) -> None:
        area = CustomArea(name="Nowhere", icb_names=("NHS Nonexistent ICB",))
        filtered = filter_by_area(enriched, area)
        assert filtered.empty

    def test_contract_type_filter_applies(self, enriched: pd.DataFrame) -> None:
        icbs = tuple(enriched["icb_name"].dropna().unique())
        area = CustomArea(name="All", icb_names=icbs)
        filtered = filter_by_area(enriched, area, contract_types=["Appliance"])
        assert set(filtered["contract_type"].unique()) <= {"Appliance"}


class TestSerialiseRoundTrip:
    def test_round_trip(self) -> None:
        areas = {
            "North Cluster": CustomArea("North Cluster", ("NHS A ICB", "NHS B ICB")),
            "South Cluster": CustomArea("South Cluster", ("NHS C ICB",)),
        }
        raw = serialise_areas(areas)
        restored = deserialise_areas(raw)
        assert restored == areas

    def test_serialise_is_valid_json(self) -> None:
        areas = {"X": CustomArea("X", ("NHS A ICB",))}
        payload = json.loads(serialise_areas(areas))
        assert payload == {"X": ["NHS A ICB"]}


class TestBuildExportZip:
    def test_zip_contains_all_three_files(self) -> None:
        zip_bytes = build_export_zip(b"a,b\n1,2\n", '{"X": []}', "methodology notes")
        import io
        import zipfile

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = set(zf.namelist())
            assert names == {
                "pharmacy_area_data.csv",
                "custom_areas.json",
                "methodology.txt",
            }
            assert zf.read("pharmacy_area_data.csv") == b"a,b\n1,2\n"

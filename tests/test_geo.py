"""Tests for src.geo — all network mocked, offline fallbacks exercised."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.geo.distance import haversine_km, haversine_km_vec
from src.geo.icb_regions import all_icb_names, icb_to_region
from src.geo.lookup_store import geocode_postcode
from src.geo.postcode_client import _parse_result, bulk_lookup, lookup_single
from src.geo.regions_fallback import region_from_postcode
from src.geo.types import normalise_postcode, outward_code


class TestPostcodeNormalisation:
    def test_lowercase_and_spaces(self) -> None:
        assert normalise_postcode("m1  1ae") == "M11AE"

    def test_already_clean(self) -> None:
        assert normalise_postcode("SW1A1AA") == "SW1A1AA"

    def test_non_string(self) -> None:
        assert normalise_postcode(None) == ""  # type: ignore[arg-type]
        assert normalise_postcode(1234) == ""  # type: ignore[arg-type]

    def test_outward_code(self) -> None:
        assert outward_code("M1 1AE") == "M1"
        assert outward_code("SW1A 1AA") == "SW1A"
        assert outward_code("M1") == "M1"


class TestRegionsFallback:
    """The ported heuristic with its shadowing bugs fixed."""

    def test_nw_not_shadowed_by_n(self) -> None:
        # Original ladder returned London for every N* postcode.
        assert region_from_postcode("NW1 4RY") == "London"
        assert region_from_postcode("NE1 4ST") == "North East and Yorkshire"
        assert region_from_postcode("NG1 5FS") == "Midlands"
        assert region_from_postcode("NR1 1AA") == "East of England"
        assert region_from_postcode("N1 9AL") == "London"

    def test_w_not_shadowing_two_letter_areas(self) -> None:
        assert region_from_postcode("WV1 1AA") == "Midlands"
        assert region_from_postcode("WS1 1AA") == "Midlands"
        assert region_from_postcode("WA9 4BZ") == "North West"
        assert region_from_postcode("WF1 1AA") == "North East and Yorkshire"
        assert region_from_postcode("W2 1NY") == "London"

    def test_tw_is_london(self) -> None:
        assert region_from_postcode("TW6 1QG") == "London"

    def test_sp_only_in_south_west(self) -> None:
        assert region_from_postcode("SP1 1AA") == "South West"

    def test_classic_cases(self) -> None:
        assert region_from_postcode("M1 2BN") == "North West"
        assert region_from_postcode("B1 1AA") == "Midlands"
        assert region_from_postcode("LS1 4DT") == "North East and Yorkshire"
        assert region_from_postcode("EX1 1AA") == "South West"
        assert region_from_postcode("CB1 1AA") == "East of England"
        assert region_from_postcode("RH6 0NN") == "South East"

    def test_unknown(self) -> None:
        assert region_from_postcode("") == "Unknown"
        assert region_from_postcode("ZZ99") == "Unknown"


class TestIcbRegions:
    def test_reference_table_has_42_icbs(self) -> None:
        assert len(all_icb_names()) == 42

    def test_full_name(self) -> None:
        assert (
            icb_to_region("NHS Greater Manchester Integrated Care Board")
            == "North West"
        )

    def test_short_forms(self) -> None:
        assert icb_to_region("NHS Devon ICB") == "South West"
        assert icb_to_region("Devon") == "South West"

    def test_punctuation_variants(self) -> None:
        assert (
            icb_to_region(
                "NHS Bristol, North Somerset and South Gloucestershire "
                "Integrated Care Board"
            )
            == "South West"
        )

    def test_unknown(self) -> None:
        assert icb_to_region("NHS Atlantis ICB") is None
        assert icb_to_region(None) is None
        assert icb_to_region("") is None


class TestDistance:
    def test_zero_distance(self) -> None:
        assert haversine_km(53.48, -2.24, 53.48, -2.24) == 0.0

    def test_known_distance_manchester_to_london(self) -> None:
        distance = haversine_km(53.4794, -2.2453, 51.5010, -0.1416)
        assert 260 < distance < 265

    def test_vectorised_matches_scalar(self) -> None:
        import numpy as np

        lats = np.array([53.4794, 51.5010, 54.9730])
        lons = np.array([-2.2453, -0.1416, -1.6180])
        vec = haversine_km_vec(52.0, -1.0, lats, lons)
        for i in range(3):
            assert vec[i] == pytest.approx(
                haversine_km(52.0, -1.0, float(lats[i]), float(lons[i])), abs=1e-9
            )


CANNED_SINGLE: dict[str, Any] = {
    "postcode": "M1 1AE",
    "latitude": 53.4794,
    "longitude": -2.2453,
    "country": "England",
    "icb": "NHS Greater Manchester Integrated Care Board",
    "codes": {"icb": "E54000057"},
}

CANNED_LEGACY_CCG: dict[str, Any] = {
    "postcode": "EX1 1AA",
    "latitude": 50.724,
    "longitude": -3.527,
    "country": "England",
    "ccg": "NHS Devon ICB",
    "codes": {"ccg": "E38000230"},
}


class TestPostcodeClientParsing:
    def test_parse_current_icb_fields(self) -> None:
        info = _parse_result(CANNED_SINGLE)
        assert info is not None
        assert info.postcode == "M11AE"
        assert info.icb_name == "NHS Greater Manchester Integrated Care Board"
        assert info.icb_code == "E54000057"
        assert info.country == "England"

    def test_parse_legacy_ccg_fields(self) -> None:
        info = _parse_result(CANNED_LEGACY_CCG)
        assert info is not None
        assert info.icb_name == "NHS Devon ICB"
        assert info.icb_code == "E38000230"

    def test_parse_incomplete(self) -> None:
        assert _parse_result({}) is None
        assert _parse_result({"postcode": "M1 1AE"}) is None

    def test_lookup_single_mocked(self) -> None:
        session = MagicMock()
        session.get.return_value = MagicMock(
            status_code=200, json=lambda: {"status": 200, "result": CANNED_SINGLE}
        )
        info = lookup_single("m1 1ae", session=session)
        assert info is not None
        assert info.lat == pytest.approx(53.4794)

    def test_lookup_single_not_found(self) -> None:
        session = MagicMock()
        session.get.return_value = MagicMock(status_code=404)
        assert lookup_single("ZZ1 1ZZ", session=session) is None

    def test_bulk_lookup_mocked(self) -> None:
        session = MagicMock()
        session.post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "status": 200,
                "result": [
                    {"query": "M1 1AE", "result": CANNED_SINGLE},
                    {"query": "ZZ1 1ZZ", "result": None},
                ],
            },
        )
        with patch("src.geo.postcode_client.time.sleep"):
            results = bulk_lookup(["M1 1AE", "ZZ1 1ZZ"], session=session)
        assert set(results.keys()) == {"M11AE"}


class TestGeocodePostcode:
    def test_exact_match_offline(self, sample_geo_lookup: pd.DataFrame) -> None:
        lookup = sample_geo_lookup.copy()
        lookup["postcode"] = lookup["postcode"].map(normalise_postcode)
        info = geocode_postcode("M1 1AE", lookup, allow_network=False)
        assert info is not None
        assert info.lat == pytest.approx(53.4794)
        assert info.nhs_region == "North West"

    def test_outward_code_centroid_offline(
        self, sample_geo_lookup: pd.DataFrame
    ) -> None:
        lookup = sample_geo_lookup.copy()
        lookup["postcode"] = lookup["postcode"].map(normalise_postcode)
        # M1 9ZZ is not in the fixture, but other M1 postcodes are absent too —
        # use CB district which has CB2 1TN only for its outward code, then a
        # genuinely different unit in the same district:
        info = geocode_postcode("CB2 9ZZ", lookup, allow_network=False)
        assert info is not None
        assert info.lat == pytest.approx(52.203)

    def test_unknown_postcode_offline(self, sample_geo_lookup: pd.DataFrame) -> None:
        lookup = sample_geo_lookup.copy()
        lookup["postcode"] = lookup["postcode"].map(normalise_postcode)
        assert geocode_postcode("ZZ99 9ZZ", lookup, allow_network=False) is None

    def test_network_preferred_when_allowed(
        self, sample_geo_lookup: pd.DataFrame
    ) -> None:
        with patch("src.geo.lookup_store.postcode_client.lookup_single") as mock_single:
            from src.geo.types import PostcodeInfo

            mock_single.return_value = PostcodeInfo(
                postcode="M11AE",
                lat=53.5,
                lon=-2.3,
                icb_name="NHS Greater Manchester Integrated Care Board",
            )
            info = geocode_postcode("M1 1AE", sample_geo_lookup, allow_network=True)
        assert info is not None
        assert info.lat == 53.5  # network value, not the lookup's 53.4794
        assert info.nhs_region == "North West"  # derived via ICB table

"""Tests for data.transform — hours parsing, quarter parsing, tidy frame."""

from __future__ import annotations

import pandas as pd
import pytest

from data.transform import DataTransformer


@pytest.fixture(scope="module")
def transformer() -> DataTransformer:
    return DataTransformer()


class TestParseTimeString:
    def test_standard_day(self, transformer: DataTransformer) -> None:
        assert transformer.parse_time_string("09:00-17:00") == 8.0

    def test_split_day(self, transformer: DataTransformer) -> None:
        assert transformer.parse_time_string("09:00-12:00,14:00-17:00") == 6.0

    def test_overnight(self, transformer: DataTransformer) -> None:
        assert transformer.parse_time_string("22:00-06:00") == 8.0

    def test_closed(self, transformer: DataTransformer) -> None:
        assert transformer.parse_time_string("Closed") == 0.0

    def test_none_and_nan(self, transformer: DataTransformer) -> None:
        assert transformer.parse_time_string(None) == 0.0
        assert transformer.parse_time_string(float("nan")) == 0.0

    def test_garbage(self, transformer: DataTransformer) -> None:
        assert transformer.parse_time_string("not a time") == 0.0

    def test_half_hours(self, transformer: DataTransformer) -> None:
        assert transformer.parse_time_string("08:30-18:30") == 10.0


class TestParseQuarterInfo:
    def test_q2(self, transformer: DataTransformer) -> None:
        info = transformer.parse_quarter_info("CONSOL_PHARMACY_LIST_202223Q2")
        assert info["year"] == 2022
        assert info["quarter"] == 2
        assert info["label"] == "2022-23 Q2"
        assert (info["date"].year, info["date"].month) == (2022, 7)

    def test_q3_not_mislabelled(self, transformer: DataTransformer) -> None:
        # The predecessor project read the 5th digit ("2" of "23") as the
        # quarter; make sure Q3 parses as Q3.
        info = transformer.parse_quarter_info("CONSOL_PHARMACY_LIST_202223Q3")
        assert info["quarter"] == 3
        assert info["label"] == "2022-23 Q3"
        assert (info["date"].year, info["date"].month) == (2022, 10)

    def test_q4_lands_in_next_calendar_year(self, transformer: DataTransformer) -> None:
        info = transformer.parse_quarter_info("CONSOL_PHARMACY_LIST_202324Q4")
        assert info["quarter"] == 4
        assert info["label"] == "2023-24 Q4"
        assert (info["date"].year, info["date"].month) == (2024, 1)

    def test_final_suffix(self, transformer: DataTransformer) -> None:
        info = transformer.parse_quarter_info("CONSOL_PHARMACY_LIST_202526Q1FINAL")
        assert info["label"] == "2025-26 Q1"
        assert (info["date"].year, info["date"].month) == (2025, 4)

    def test_unparseable(self, transformer: DataTransformer) -> None:
        assert transformer.parse_quarter_info("SOMETHING_ELSE")["label"] == "Unknown"


class TestBuildTidyFrame:
    def test_schema_and_shape(
        self,
        transformer: DataTransformer,
        sample_raw_by_resource: dict[str, pd.DataFrame],
    ) -> None:
        tidy = transformer.build_tidy_frame(sample_raw_by_resource)
        expected_columns = {
            "ods_code",
            "name",
            "address",
            "postcode",
            "contract_type",
            "hours_monday",
            "hours_tuesday",
            "hours_wednesday",
            "hours_thursday",
            "hours_friday",
            "hours_saturday",
            "hours_sunday",
            "weekly_hours",
            "resource_id",
            "quarter_label",
            "quarter_date",
        }
        assert expected_columns <= set(tidy.columns)
        assert len(tidy) == 239  # committed fixture size
        assert tidy["quarter_label"].nunique() == 12

    def test_quarters_sorted_chronologically(
        self,
        transformer: DataTransformer,
        sample_raw_by_resource: dict[str, pd.DataFrame],
    ) -> None:
        tidy = transformer.build_tidy_frame(sample_raw_by_resource)
        assert tidy["quarter_date"].is_monotonic_increasing

    def test_weekly_hours_match_profiles(
        self,
        transformer: DataTransformer,
        sample_raw_by_resource: dict[str, pd.DataFrame],
    ) -> None:
        tidy = transformer.build_tidy_frame(sample_raw_by_resource)
        hundred_hour = tidy[tidy["ods_code"] == "FTEST02"]["weekly_hours"].unique()
        assert list(hundred_hour) == [112.0]  # 07:00-23:00 all seven days
        split = tidy[tidy["ods_code"] == "FTEST03"]["weekly_hours"].unique()
        assert list(split) == [30.0]  # 6h split day x5, weekend closed

    def test_address_joined(
        self,
        transformer: DataTransformer,
        sample_raw_by_resource: dict[str, pd.DataFrame],
    ) -> None:
        tidy = transformer.build_tidy_frame(sample_raw_by_resource)
        row = tidy[tidy["ods_code"] == "FTEST01"].iloc[0]
        assert row["address"] == "1 Piccadilly Gardens, Manchester"

    def test_empty_input(self, transformer: DataTransformer) -> None:
        assert transformer.build_tidy_frame({}).empty

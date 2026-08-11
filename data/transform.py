"""Transformation of raw NHSBSA pharmacy data into a tidy analysis frame.

Ported from pharmacy-analysis-with-open-data/data/transform.py (opening-hours
parsing incl. split days and overnight ranges), with one fix: the original
``parse_quarter_info`` read the quarter number from the 5th character of the
fiscal-year token (part of the end-year, e.g. the first "2" of "23" in
``202223Q3``) instead of the digit after "Q", mislabelling Q3/Q4 snapshots.
Quarter parsing here uses an explicit regex on the ``YYYYYYQn`` token and maps
fiscal quarters to real calendar dates (UK fiscal year starts in April).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

import pandas as pd

TRANSFORM_CONFIG: dict[str, Any] = {
    "time_patterns": {
        "single_range": r"(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})",
        "closed_indicators": ["closed", "", "null", "none"],
    },
}

# CONSOL_PHARMACY_LIST_202223Q2 → start year 2022, end-year digits 23, Q2.
_RESOURCE_QUARTER_PATTERN = re.compile(r"(\d{4})(\d{2})Q(\d)")

# Raw NHSBSA column → tidy snake_case column.
RAW_COLUMN_MAP: dict[str, str] = {
    "PHARMACY_ODS_CODE_F_CODE": "ods_code",
    "PHARMACY_TRADING_NAME": "name",
    "POST_CODE": "postcode",
    "CONTRACT_TYPE": "contract_type",
    "PHARMACY_OPENING_HOURS_MONDAY": "hours_monday",
    "PHARMACY_OPENING_HOURS_TUESDAY": "hours_tuesday",
    "PHARMACY_OPENING_HOURS_WEDNESDAY": "hours_wednesday",
    "PHARMACY_OPENING_HOURS_THURSDAY": "hours_thursday",
    "PHARMACY_OPENING_HOURS_FRIDAY": "hours_friday",
    "PHARMACY_OPENING_HOURS_SATURDAY": "hours_saturday",
    "PHARMACY_OPENING_HOURS_SUNDAY": "hours_sunday",
}

# Fallbacks seen across quarterly snapshots for the ODS code column.
ODS_CODE_FALLBACKS = ["PHARMACY_ODS_CODE_F_CODE", "PHARMACY_ODS_CODE", "ODS_CODE"]

ADDRESS_FIELDS = [
    "ADDRESS_FIELD1",
    "ADDRESS_FIELD2",
    "ADDRESS_FIELD3",
    "ADDRESS_FIELD4",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - TRANSFORM - %(levelname)s - %(message)s",
)


class DataTransformer:
    """Cleans and reshapes raw pharmacy data into analysis-ready form."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def parse_time_string(self, time_string: object) -> float:
        """Parse an opening-hours string into decimal hours.

        Examples:
            "09:00-17:00" → 8.0, "09:00-12:00,14:00-17:00" → 6.0 (split day),
            "22:00-06:00" → 8.0 (overnight), "Closed" → 0.0
        """
        if time_string is None or pd.isna(time_string):
            return 0.0

        text = str(time_string).strip()
        if text.lower() in TRANSFORM_CONFIG["time_patterns"]["closed_indicators"]:
            return 0.0

        if "," in text:
            return sum(
                self._parse_single_time_range(part.strip()) for part in text.split(",")
            )
        return self._parse_single_time_range(text)

    def _parse_single_time_range(self, time_range: str) -> float:
        """Parse one "HH:MM-HH:MM" range into decimal hours."""
        try:
            match = re.match(
                TRANSFORM_CONFIG["time_patterns"]["single_range"], time_range.strip()
            )
            if match:
                start_hour, start_min, end_hour, end_min = map(int, match.groups())
                start_minutes = start_hour * 60 + start_min
                end_minutes = end_hour * 60 + end_min
                if end_minutes < start_minutes:  # overnight, e.g. 22:00-06:00
                    end_minutes += 24 * 60
                return (end_minutes - start_minutes) / 60.0
            return 0.0
        except (ValueError, AttributeError):
            return 0.0

    def calculate_weekly_hours(self, df: pd.DataFrame) -> pd.Series:
        """Sum parsed daily opening hours into a weekly total per pharmacy."""
        opening_hours_columns = [
            col for col in df.columns if col.startswith("PHARMACY_OPENING_HOURS_")
        ]
        if not opening_hours_columns:
            self.logger.warning("No opening hours columns found in data")
            return pd.Series(0.0, index=df.index)

        weekly = pd.Series(0.0, index=df.index)
        for column in opening_hours_columns:
            weekly += df[column].apply(self.parse_time_string)
        return weekly

    def parse_quarter_info(self, resource_id: str) -> dict[str, Any]:
        """Parse fiscal year/quarter from a resource ID.

        ``CONSOL_PHARMACY_LIST_202223Q3`` → fiscal year 2022-23, Q3, dated
        2022-10-01 (fiscal Q1 starts in April; Q4 lands in January of the
        following calendar year).
        """
        match = _RESOURCE_QUARTER_PATTERN.search(resource_id)
        if not match:
            self.logger.error(f"Cannot parse quarter from resource ID: {resource_id}")
            return {
                "year": 2022,
                "quarter": 1,
                "label": "Unknown",
                "date": datetime(2022, 1, 1),
            }

        start_year = int(match.group(1))
        end_digits = match.group(2)
        quarter_num = int(match.group(3))

        if quarter_num == 4:
            date = datetime(start_year + 1, 1, 1)
        else:
            date = datetime(start_year, 4 + (quarter_num - 1) * 3, 1)

        return {
            "year": start_year,
            "quarter": quarter_num,
            "label": f"{start_year}-{end_digits} Q{quarter_num}",
            "date": date,
        }

    def build_tidy_frame(
        self, raw_by_resource: dict[str, pd.DataFrame]
    ) -> pd.DataFrame:
        """Combine per-quarter raw frames into one tidy frame.

        One row per pharmacy-quarter with snake_case columns: ods_code, name,
        address, postcode, contract_type, hours_monday..sunday, weekly_hours,
        resource_id, quarter_label, quarter_date. Rows without an ODS code are
        dropped (they cannot be tracked across quarters).
        """
        tidy_frames: list[pd.DataFrame] = []

        for resource_id, raw in raw_by_resource.items():
            if raw.empty:
                continue
            quarter = self.parse_quarter_info(resource_id)

            frame = pd.DataFrame(index=raw.index)
            frame["ods_code"] = self._first_available(raw, ODS_CODE_FALLBACKS)
            frame["name"] = raw.get("PHARMACY_TRADING_NAME", pd.Series(dtype=str))
            frame["address"] = self._join_address(raw)
            frame["postcode"] = raw.get("POST_CODE", pd.Series(dtype=str))
            frame["contract_type"] = raw.get("CONTRACT_TYPE", pd.Series(dtype=str))
            for raw_col, tidy_col in RAW_COLUMN_MAP.items():
                if tidy_col.startswith("hours_"):
                    frame[tidy_col] = raw.get(raw_col, pd.Series(dtype=str))
            frame["weekly_hours"] = self.calculate_weekly_hours(raw)
            frame["resource_id"] = resource_id
            frame["quarter_label"] = quarter["label"]
            frame["quarter_date"] = quarter["date"]

            frame = frame.dropna(subset=["ods_code"])
            frame = frame[frame["ods_code"].astype(str).str.strip() != ""]
            tidy_frames.append(frame)

        if not tidy_frames:
            return pd.DataFrame()

        tidy = pd.concat(tidy_frames, ignore_index=True)
        tidy = tidy.sort_values(["quarter_date", "ods_code"]).reset_index(drop=True)
        self.logger.info(
            f"Tidy frame: {len(tidy)} pharmacy-quarter rows across "
            f"{tidy['quarter_label'].nunique()} quarters"
        )
        return tidy

    @staticmethod
    def _first_available(raw: pd.DataFrame, candidates: list[str]) -> pd.Series:
        """Return the first present candidate column, else an all-NA series."""
        for col in candidates:
            if col in raw.columns:
                return raw[col]
        return pd.Series(pd.NA, index=raw.index)

    @staticmethod
    def _join_address(raw: pd.DataFrame) -> pd.Series:
        """Join ADDRESS_FIELD1-4 into one comma-separated address string."""
        present = [col for col in ADDRESS_FIELDS if col in raw.columns]
        if not present:
            return pd.Series("", index=raw.index)
        parts = raw[present].fillna("").astype(str)
        joined = parts.apply(
            lambda row: ", ".join(p.strip() for p in row if p.strip()), axis=1
        )
        return joined

    def validate_data_quality(self, df: pd.DataFrame) -> dict[str, Any]:
        """Basic quality metrics for a raw quarterly frame."""
        if df.empty:
            return {"status": "empty", "issues": ["No data to validate"]}

        issues: list[str] = []
        for col in ["PHARMACY_ODS_CODE_F_CODE", "CONTRACT_TYPE"]:
            if col in df.columns:
                missing = int(df[col].isna().sum())
                if missing > 0:
                    issues.append(f"Missing values in {col}: {missing}")

        if "PHARMACY_ODS_CODE_F_CODE" in df.columns:
            duplicates = int(df["PHARMACY_ODS_CODE_F_CODE"].duplicated().sum())
            if duplicates > 0:
                issues.append(f"Duplicate ODS codes: {duplicates}")

        return {
            "status": "valid" if not issues else "issues_found",
            "total_records": len(df),
            "issues": issues,
        }

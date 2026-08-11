"""Nearest-pharmacy lookup logic (pure, testable — no Streamlit imports).

Ported behaviours from the old repo's pharmacy_finder: open-now check
against today's parsed hours and Google Maps walking directions links. The
stub geocoder is gone — user postcodes resolve through
src.geo.lookup_store.geocode_postcode (network → local lookup → outward-code
centroid).
"""

from __future__ import annotations

import re
import urllib.parse
from datetime import datetime

import numpy as np
import pandas as pd

from data.transform import DataTransformer
from src.geo.distance import haversine_km_vec
from src.geo.types import GeoPoint

WALKING_SPEED_KMH = 5.0

_DAY_COLUMNS = [
    "hours_monday",
    "hours_tuesday",
    "hours_wednesday",
    "hours_thursday",
    "hours_friday",
    "hours_saturday",
    "hours_sunday",
]

_transformer = DataTransformer()


def is_open_now(hours_string: object, now: datetime) -> bool:
    """Whether a pharmacy with this day-string is open at ``now``.

    Handles split days ("09:00-12:00,14:00-17:00"); overnight ranges count
    as open from the start time until midnight (the wrap past midnight
    belongs to the next day's string in the source data).
    """
    if hours_string is None or pd.isna(hours_string):
        return False
    text = str(hours_string).strip()
    if _transformer.parse_time_string(text) == 0.0:
        return False

    minutes_now = now.hour * 60 + now.minute
    for part in text.split(","):
        rng = part.strip()
        match = re.match(r"(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})", rng)
        if not match:
            continue
        start_h, start_m, end_h, end_m = map(int, match.groups())
        start = start_h * 60 + start_m
        end = end_h * 60 + end_m
        if end < start:  # overnight: open from start until midnight today
            end = 24 * 60
        if start <= minutes_now < end:
            return True
    return False


def google_maps_walking_url(
    origin: GeoPoint, destination_address: str, destination_postcode: str
) -> str:
    """Google Maps walking-directions URL from the user to a pharmacy."""
    destination = urllib.parse.quote_plus(
        f"{destination_address}, {destination_postcode}"
    )
    return (
        "https://www.google.com/maps/dir/?api=1"
        f"&origin={origin.lat},{origin.lon}"
        f"&destination={destination}"
        "&travelmode=walking"
    )


def nearest_pharmacies(
    user: GeoPoint,
    quarter_df: pd.DataFrame,
    n: int = 5,
    open_now_only: bool = False,
    now: datetime | None = None,
) -> pd.DataFrame:
    """Top-N pharmacies nearest the user, with distance and status columns.

    ``quarter_df`` should be one quarter's rows (typically the latest);
    rows without coordinates are ignored. Returns columns: name, address,
    postcode, contract_type, distance_km, walking_minutes, open_now,
    todays_hours, maps_url — sorted by distance.
    """
    now = now or datetime.now()
    candidates = quarter_df[
        quarter_df["lat"].notna() & quarter_df["lon"].notna()
    ].copy()
    if candidates.empty:
        return pd.DataFrame(
            columns=[
                "name",
                "address",
                "postcode",
                "contract_type",
                "distance_km",
                "walking_minutes",
                "open_now",
                "todays_hours",
                "maps_url",
            ]
        )

    distances = haversine_km_vec(
        user.lat,
        user.lon,
        candidates["lat"].to_numpy(dtype=np.float64),
        candidates["lon"].to_numpy(dtype=np.float64),
    )
    candidates["distance_km"] = np.round(distances, 2)
    candidates["walking_minutes"] = np.ceil(distances / WALKING_SPEED_KMH * 60).astype(
        int
    )

    today_column = _DAY_COLUMNS[now.weekday()]
    candidates["todays_hours"] = candidates[today_column].fillna("Closed")
    candidates["open_now"] = candidates[today_column].map(lambda h: is_open_now(h, now))

    if open_now_only:
        candidates = candidates[candidates["open_now"]]

    candidates = candidates.sort_values("distance_km").head(n)
    candidates["maps_url"] = [
        google_maps_walking_url(user, str(row.address), str(row.postcode))
        for row in candidates.itertuples()
    ]
    return candidates[
        [
            "name",
            "address",
            "postcode",
            "contract_type",
            "distance_km",
            "walking_minutes",
            "open_now",
            "todays_hours",
            "maps_url",
        ]
    ].reset_index(drop=True)

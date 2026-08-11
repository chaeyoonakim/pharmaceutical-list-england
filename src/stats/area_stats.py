"""Quarterly trend statistics and a transparent next-year outlook.

Openings and closures are true churn: set differences of ODS codes between
consecutive quarterly snapshots (a pharmacy present last quarter but not this
one closed; the reverse opened). The forecast is deliberately simple and
honest — Theil–Sen (median of pairwise slopes, robust to single-quarter level
shifts like the known 2025 snapshot discontinuity) or OLS, projected four
quarters with an approximate residual-based band. It is a trend
extrapolation over at most ~12 observations, not a causal model, and the
caveats travel with the result.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

DISCONTINUITY_THRESHOLD_PCT = 10.0
CLASSIFICATION_THRESHOLD_PCT = 1.0
FORECAST_HORIZON_QUARTERS = 4

GROWTH = "growth"
STABLE = "stable"
DECLINE = "decline"

BASE_CAVEATS = [
    "Trend extrapolation over quarterly snapshot counts — not a causal or "
    "behavioural model.",
    "Quarterly snapshots can reflect list-extraction changes as well as real "
    "openings and closures.",
]


@dataclass
class AreaTrend:
    """Per-quarter counts and churn for one selected area."""

    quarter_labels: list[str]
    quarter_dates: list[pd.Timestamp]
    counts: list[int]
    openings: list[int]  # index 0 is always 0 (no previous quarter)
    closures: list[int]  # index 0 is always 0
    net_change: list[int]


@dataclass
class Forecast:
    """A four-quarter projection with classification and caveats."""

    horizon_labels: list[str]
    projected: list[float]
    lower: list[float]
    upper: list[float]
    slope_per_quarter: float
    classification: str
    method: str
    caveats: list[str] = field(default_factory=list)


def compute_area_trend(area_df: pd.DataFrame) -> AreaTrend:
    """Counts and ODS-set-diff churn per quarter for an already-filtered frame.

    Expects tidy columns ods_code, quarter_label, quarter_date. Quarters are
    ordered by quarter_date.
    """
    if area_df.empty:
        return AreaTrend([], [], [], [], [], [])

    quarters = (
        area_df[["quarter_label", "quarter_date"]]
        .drop_duplicates()
        .sort_values("quarter_date")
    )

    labels: list[str] = []
    dates: list[pd.Timestamp] = []
    counts: list[int] = []
    openings: list[int] = []
    closures: list[int] = []
    net_change: list[int] = []

    previous_codes: set[str] | None = None
    for row in quarters.itertuples():
        label = str(row.quarter_label)
        date = pd.Timestamp(row.quarter_date)
        codes = set(
            area_df.loc[area_df["quarter_label"] == label, "ods_code"].astype(str)
        )
        labels.append(label)
        dates.append(date)
        counts.append(len(codes))
        if previous_codes is None:
            openings.append(0)
            closures.append(0)
            net_change.append(0)
        else:
            opened = len(codes - previous_codes)
            closed = len(previous_codes - codes)
            openings.append(opened)
            closures.append(closed)
            net_change.append(opened - closed)
        previous_codes = codes

    return AreaTrend(labels, dates, counts, openings, closures, net_change)


def detect_discontinuities(
    counts: Sequence[int], threshold_pct: float = DISCONTINUITY_THRESHOLD_PCT
) -> list[int]:
    """Indices whose quarter-on-quarter change exceeds the threshold.

    A |QoQ| jump above ~10% in a national quarterly series (e.g. the
    8,451 → 10,378 step between the 2024-25 and 2025-26 snapshot extracts)
    is far likelier to be an extraction-method change than real churn.
    """
    indices: list[int] = []
    for i in range(1, len(counts)):
        previous = counts[i - 1]
        if previous == 0:
            continue
        change_pct = abs(counts[i] - previous) / previous * 100
        if change_pct > threshold_pct:
            indices.append(i)
    return indices


def _theil_sen(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Median-of-pairwise-slopes estimator (slope, intercept)."""
    slopes = [
        (y[j] - y[i]) / (x[j] - x[i])
        for i in range(len(x))
        for j in range(i + 1, len(x))
        if x[j] != x[i]
    ]
    slope = float(np.median(slopes))
    intercept = float(np.median(y - slope * x))
    return slope, intercept


def _next_quarter_labels(last_label: str, horizon: int) -> list[str]:
    """Roll fiscal quarter labels forward: "2025-26 Q1" → Q2, Q3, Q4, next FY Q1."""
    try:
        fiscal, quarter_part = last_label.rsplit(" Q", 1)
        start_year = int(fiscal.split("-")[0])
        quarter = int(quarter_part)
    except (ValueError, IndexError):
        return [f"+{i}" for i in range(1, horizon + 1)]

    labels = []
    for _ in range(horizon):
        quarter += 1
        if quarter > 4:
            quarter = 1
            start_year += 1
        labels.append(f"{start_year}-{str(start_year + 1)[-2:]} Q{quarter}")
    return labels


def forecast_counts(
    trend: AreaTrend,
    horizon: int = FORECAST_HORIZON_QUARTERS,
    method: str = "theil_sen",
    start_index: int = 0,
) -> Forecast | None:
    """Project the count series ``horizon`` quarters ahead.

    ``start_index`` fits only quarters from that index on (the
    "exclude pre-discontinuity quarters" toggle). Returns None when fewer
    than 3 usable observations remain.
    """
    counts = np.asarray(trend.counts[start_index:], dtype=float)
    if len(counts) < 3:
        return None

    x = np.arange(len(counts), dtype=float)
    if method == "ols":
        slope, intercept = (float(v) for v in np.polyfit(x, counts, 1))
    else:
        method = "theil_sen"
        slope, intercept = _theil_sen(x, counts)

    fitted = intercept + slope * x
    residual_std = float(np.std(counts - fitted))
    band = 1.96 * residual_std

    future_x = np.arange(len(counts), len(counts) + horizon, dtype=float)
    projected = intercept + slope * future_x

    caveats = list(BASE_CAVEATS)
    caveats.append(f"Fitted on {len(counts)} quarterly observations.")
    discontinuities = detect_discontinuities([int(c) for c in counts])
    if discontinuities:
        caveats.append(
            "The fitted series contains a quarter-on-quarter jump above "
            f"{DISCONTINUITY_THRESHOLD_PCT:.0f}% — likely a snapshot/extraction "
            "artifact; consider excluding pre-jump quarters."
        )

    last_observed = counts[-1]
    if last_observed > 0:
        change_pct = (projected[-1] - last_observed) / last_observed * 100
    else:
        change_pct = 0.0
    if change_pct > CLASSIFICATION_THRESHOLD_PCT:
        classification = GROWTH
    elif change_pct < -CLASSIFICATION_THRESHOLD_PCT:
        classification = DECLINE
    else:
        classification = STABLE

    last_label = trend.quarter_labels[-1] if trend.quarter_labels else ""
    return Forecast(
        horizon_labels=_next_quarter_labels(last_label, horizon),
        projected=[float(v) for v in projected],
        lower=[float(v - band) for v in projected],
        upper=[float(v + band) for v in projected],
        slope_per_quarter=slope,
        classification=classification,
        method=method,
        caveats=caveats,
    )

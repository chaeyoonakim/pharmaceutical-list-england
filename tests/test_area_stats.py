"""Tests for src.stats.area_stats against the engineered fixture events."""

from __future__ import annotations

import pandas as pd
import pytest

from data.enrich import attach_geo
from data.transform import DataTransformer
from src.stats.area_stats import (
    DECLINE,
    GROWTH,
    STABLE,
    AreaTrend,
    compute_area_trend,
    detect_discontinuities,
    forecast_counts,
)


@pytest.fixture(scope="module")
def enriched(
    sample_raw_by_resource: dict[str, pd.DataFrame],
    sample_geo_lookup: pd.DataFrame,
) -> pd.DataFrame:
    tidy = DataTransformer().build_tidy_frame(sample_raw_by_resource)
    return attach_geo(tidy, sample_geo_lookup)


class TestComputeAreaTrend:
    def test_national_counts(self, enriched: pd.DataFrame) -> None:
        trend = compute_area_trend(enriched)
        assert len(trend.counts) == 12
        # 21 pharmacies at start (FTEST21 not yet open), 19 at the end
        # (FTEST05, FTEST13, FTEST15 closed; FTEST21 opened).
        assert trend.counts[0] == 21
        assert trend.counts[-1] == 19

    def test_engineered_closure_detected(self, enriched: pd.DataFrame) -> None:
        trend = compute_area_trend(enriched)
        # FTEST05 last appears in 2023-24 Q2 (index 4) → closure in index 5.
        assert trend.closures[5] == 1
        assert trend.openings[5] == 0

    def test_engineered_opening_detected(self, enriched: pd.DataFrame) -> None:
        trend = compute_area_trend(enriched)
        # FTEST21 first appears in 2024-25 Q3 (index 9).
        assert trend.openings[9] == 1

    def test_regional_filter_decline(self, enriched: pd.DataFrame) -> None:
        ney = enriched[enriched["nhs_region"] == "North East and Yorkshire"]
        trend = compute_area_trend(ney)
        # 4 pharmacies at start, 2 by the end (FTEST13 and FTEST15 close).
        assert trend.counts[0] == 4
        assert trend.counts[-1] == 2
        assert sum(trend.closures) == 2
        assert sum(trend.openings) == 0

    def test_net_change_consistency(self, enriched: pd.DataFrame) -> None:
        trend = compute_area_trend(enriched)
        for i in range(1, len(trend.counts)):
            assert trend.counts[i] - trend.counts[i - 1] == trend.net_change[i], (
                f"net change inconsistent at index {i}"
            )

    def test_empty_frame(self) -> None:
        trend = compute_area_trend(pd.DataFrame())
        assert trend.counts == []


class TestDetectDiscontinuities:
    def test_smooth_series_clean(self) -> None:
        assert detect_discontinuities([100, 101, 99, 98, 100]) == []

    def test_extraction_jump_detected(self) -> None:
        # Modelled on the real 8451 → 10378 jump (+22.8%).
        counts = [8948, 8703, 8451, 10378]
        assert detect_discontinuities(counts) == [3]

    def test_zero_previous_skipped(self) -> None:
        assert detect_discontinuities([0, 50]) == []


def _trend_from_counts(counts: list[int]) -> AreaTrend:
    labels = [f"2022-23 Q{(i % 4) + 1}" for i in range(len(counts))]
    dates = list(pd.date_range("2022-04-01", periods=len(counts), freq="QS"))
    zeros = [0] * len(counts)
    return AreaTrend(labels, dates, counts, zeros, zeros, zeros)


class TestForecastCounts:
    def test_declining_series_classified_decline(self) -> None:
        forecast = forecast_counts(_trend_from_counts([100, 97, 95, 92, 90, 87]))
        assert forecast is not None
        assert forecast.slope_per_quarter < 0
        assert forecast.classification == DECLINE
        assert len(forecast.projected) == 4

    def test_growing_series_classified_growth(self) -> None:
        forecast = forecast_counts(_trend_from_counts([90, 93, 95, 98, 100, 103]))
        assert forecast is not None
        assert forecast.classification == GROWTH

    def test_flat_series_classified_stable(self) -> None:
        forecast = forecast_counts(_trend_from_counts([100, 100, 100, 100]))
        assert forecast is not None
        assert forecast.classification == STABLE
        assert forecast.slope_per_quarter == 0.0

    def test_theil_sen_robust_to_level_shift(self) -> None:
        # Flat series with one artifact jump: Theil–Sen should stay near
        # flat while OLS is dragged upward.
        counts = [100, 100, 100, 100, 100, 100, 100, 100, 122, 122, 122, 122]
        theil = forecast_counts(_trend_from_counts(counts), method="theil_sen")
        ols = forecast_counts(_trend_from_counts(counts), method="ols")
        assert theil is not None and ols is not None
        assert abs(theil.slope_per_quarter) < abs(ols.slope_per_quarter)

    def test_discontinuity_caveat_and_exclusion(self) -> None:
        counts = [8948, 8703, 8451, 10378, 10390, 10405]
        with_jump = forecast_counts(_trend_from_counts(counts))
        assert with_jump is not None
        assert any("jump" in c for c in with_jump.caveats)
        # Fit only post-jump quarters via start_index.
        post_jump = forecast_counts(_trend_from_counts(counts), start_index=3)
        assert post_jump is not None
        assert not any("jump" in c for c in post_jump.caveats)
        assert post_jump.slope_per_quarter == pytest.approx(13.5, abs=1.0)

    def test_band_contains_projection(self) -> None:
        forecast = forecast_counts(_trend_from_counts([100, 98, 103, 99, 101, 100]))
        assert forecast is not None
        for lower, mid, upper in zip(
            forecast.lower, forecast.projected, forecast.upper, strict=True
        ):
            assert lower <= mid <= upper

    def test_horizon_labels_roll_fiscal_year(self) -> None:
        trend = _trend_from_counts([100, 100, 100, 100])  # ends at 2022-23 Q4
        forecast = forecast_counts(trend)
        assert forecast is not None
        assert forecast.horizon_labels == [
            "2023-24 Q1",
            "2023-24 Q2",
            "2023-24 Q3",
            "2023-24 Q4",
        ]

    def test_too_few_points(self) -> None:
        assert forecast_counts(_trend_from_counts([100, 101])) is None

    def test_ols_method_reported(self) -> None:
        forecast = forecast_counts(_trend_from_counts([1, 2, 3, 4]), method="ols")
        assert forecast is not None
        assert forecast.method == "ols"

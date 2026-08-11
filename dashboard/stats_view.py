"""Statistics panel figure/metric builders (pure, testable)."""

from __future__ import annotations

from typing import Any

import plotly.graph_objects as go

from src.stats.area_stats import AreaTrend, Forecast

TREND_COLOUR = "#1f77b4"
FORECAST_COLOUR = "#d62728"
OPENINGS_COLOUR = "#2ca02c"
CLOSURES_COLOUR = "#d62728"

CLASSIFICATION_BADGES = {
    "growth": ("📈 Growth likely", "The trend projects more pharmacies a year out."),
    "stable": ("➡️ Broadly stable", "The trend projects little change a year out."),
    "decline": ("📉 Decline likely", "The trend projects fewer pharmacies a year out."),
}


def headline_metrics(trend: AreaTrend) -> dict[str, Any]:
    """Values for the metric tiles."""
    if not trend.counts:
        return {
            "current_count": 0,
            "net_change_total": 0,
            "latest_openings": 0,
            "latest_closures": 0,
            "latest_quarter": "—",
        }
    return {
        "current_count": trend.counts[-1],
        "net_change_total": trend.counts[-1] - trend.counts[0],
        "latest_openings": trend.openings[-1],
        "latest_closures": trend.closures[-1],
        "latest_quarter": trend.quarter_labels[-1],
    }


def trend_figure(trend: AreaTrend, forecast: Forecast | None) -> go.Figure:
    """Observed counts line with the projection and its band appended."""
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=trend.quarter_labels,
            y=trend.counts,
            mode="lines+markers",
            name="Pharmacies",
            line={"color": TREND_COLOUR, "width": 2},
        )
    )

    if forecast is not None and trend.counts:
        # Bridge from the last observed point into the projection.
        x = [trend.quarter_labels[-1], *forecast.horizon_labels]
        projected = [float(trend.counts[-1]), *forecast.projected]
        lower = [float(trend.counts[-1]), *forecast.lower]
        upper = [float(trend.counts[-1]), *forecast.upper]

        fig.add_trace(
            go.Scatter(
                x=[*x, *x[::-1]],
                y=[*upper, *lower[::-1]],
                fill="toself",
                fillcolor="rgba(214, 39, 40, 0.12)",
                line={"width": 0},
                hoverinfo="skip",
                name="Approx. 95% band",
                showlegend=True,
            )
        )
        fig.add_trace(
            go.Scatter(
                x=x,
                y=projected,
                mode="lines+markers",
                name=f"Forecast ({forecast.method.replace('_', '–')})",
                line={"color": FORECAST_COLOUR, "width": 2, "dash": "dash"},
                marker={"symbol": "diamond"},
            )
        )

    fig.update_layout(
        margin={"l": 10, "r": 10, "t": 30, "b": 10},
        height=320,
        yaxis_title="Pharmacies",
        legend={"orientation": "h", "y": -0.25},
        title="Quarterly pharmacy count and next-year projection",
    )
    return fig


def churn_figure(trend: AreaTrend) -> go.Figure:
    """Openings vs closures per quarter (first quarter has no baseline)."""
    labels = trend.quarter_labels[1:]
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=labels,
            y=trend.openings[1:],
            name="Openings",
            marker_color=OPENINGS_COLOUR,
        )
    )
    fig.add_trace(
        go.Bar(
            x=labels,
            y=[-c for c in trend.closures[1:]],
            name="Closures",
            marker_color=CLOSURES_COLOUR,
        )
    )
    fig.update_layout(
        barmode="relative",
        margin={"l": 10, "r": 10, "t": 30, "b": 10},
        height=280,
        yaxis_title="Pharmacies (+opened / −closed)",
        legend={"orientation": "h", "y": -0.3},
        title="Openings and closures by quarter (ODS-code churn)",
    )
    return fig


def classification_badge(forecast: Forecast | None) -> tuple[str, str]:
    """(headline, explanation) for the outlook badge."""
    if forecast is None:
        return (
            "ℹ️ Not enough data",
            "Fewer than three usable quarters — no projection is shown.",
        )
    return CLASSIFICATION_BADGES[forecast.classification]

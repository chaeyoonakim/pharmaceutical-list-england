"""Plotly map figure construction (pure, testable)."""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go

CONTRACT_COLOURS = {
    "Community": "#005eb8",  # NHS blue
    "Appliance": "#003087",  # NHS dark blue
    "LPS": "#007f3b",  # NHS green
}
DEFAULT_COLOUR = "#4c6272"  # NHS grey
ENGLAND_CENTER = {"lat": 52.8, "lon": -1.5}
ENGLAND_ZOOM = 5.3


def _hover_text(row: Any) -> str:
    return (
        f"<b>{row.name_}</b><br>{row.address}<br>{row.postcode}"
        f"<br>ODS: {row.ods_code} · {row.contract_type}"
        f"<br>{row.weekly_hours:.1f} h/week"
    )


def build_map_figure(
    mappable_df: pd.DataFrame,
    boundaries: dict[str, Any] | None = None,
    user_point: tuple[float, float] | None = None,
) -> go.Figure:
    """Scatter map of pharmacies, coloured by contract type.

    ``boundaries`` (optional GeoJSON FeatureCollection) is drawn as outline
    layers beneath the markers. ``user_point`` adds a distinct marker for
    the visitor's own postcode location.
    """
    fig = go.Figure()

    frame = mappable_df.rename(columns={"name": "name_"})
    for contract_type, group in frame.groupby("contract_type", sort=True):
        fig.add_trace(
            go.Scattermap(
                lat=group["lat"],
                lon=group["lon"],
                mode="markers",
                name=str(contract_type),
                marker={
                    "size": 9,
                    "color": CONTRACT_COLOURS.get(str(contract_type), DEFAULT_COLOUR),
                    "opacity": 0.75,
                },
                text=[_hover_text(row) for row in group.itertuples()],
                hoverinfo="text",
            )
        )

    if user_point is not None:
        fig.add_trace(
            go.Scattermap(
                lat=[user_point[0]],
                lon=[user_point[1]],
                mode="markers",
                name="You",
                marker={"size": 16, "color": "#d5281b", "symbol": "circle"},
                text=["Your postcode"],
                hoverinfo="text",
            )
        )

    layers = []
    if boundaries is not None:
        layers.append(
            {
                "source": boundaries,
                "type": "line",
                "color": "#555555",
                "line": {"width": 1},
            }
        )

    if len(frame) > 0:
        center = {
            "lat": float(frame["lat"].mean()),
            "lon": float(frame["lon"].mean()),
        }
        lat_span = float(frame["lat"].max() - frame["lat"].min())
        lon_span = float(frame["lon"].max() - frame["lon"].min())
        span = max(lat_span, lon_span)
        if span < 0.2:
            zoom = 11.0
        elif span < 1.0:
            zoom = 8.5
        elif span < 3.0:
            zoom = 7.0
        else:
            zoom = ENGLAND_ZOOM
    else:
        center, zoom = ENGLAND_CENTER, ENGLAND_ZOOM

    fig.update_layout(
        map={
            "style": "carto-positron",
            "center": center,
            "zoom": zoom,
            "layers": layers,
        },
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        height=560,
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 0.01,
            "xanchor": "left",
            "x": 0.01,
            "bgcolor": "rgba(255,255,255,0.7)",
        },
    )
    return fig

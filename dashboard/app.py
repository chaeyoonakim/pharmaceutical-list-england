"""Streamlit dashboard: England pharmacy map, area statistics, near-me lookup.

Run from the repository root:

    streamlit run dashboard/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# streamlit runs this file as a script, so make the repo root importable.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from dashboard import data_access, finder_logic, map_view, stats_view  # noqa: E402
from src.geo import boundaries as boundaries_module  # noqa: E402
from src.geo.lookup_store import geocode_postcode, load_lookup  # noqa: E402
from src.geo.types import GeoPoint  # noqa: E402
from src.stats.area_stats import (  # noqa: E402
    compute_area_trend,
    detect_discontinuities,
    forecast_counts,
)

st.set_page_config(
    page_title="England pharmacy map",
    page_icon="💊",
    layout="wide",
)


@st.cache_data(show_spinner="Loading pharmacy data…")
def _load_dataset() -> tuple[pd.DataFrame, str]:
    return data_access.load_dataset()


@st.cache_data(show_spinner=False)
def _load_boundaries(kind: str) -> dict | None:
    return boundaries_module.get_boundaries("region" if kind == "region" else "icb")


@st.cache_data(show_spinner=False)
def _load_geo_lookup() -> pd.DataFrame:
    return load_lookup().frame


def main() -> None:
    df, provenance = _load_dataset()

    st.title("💊 England pharmacy map")
    st.caption(
        "NHSBSA Consolidated Pharmaceutical List · quarterly snapshots "
        f"{df['quarter_label'].min()} – {df['quarter_label'].max()} · "
        "Contains public sector information licensed under OGL v3.0"
    )

    if provenance == "sample":
        st.warning(
            "**Showing bundled sample data** (a small fixture set). Build the "
            "full dataset with `python -m data.build_geo_lookup && "
            "python -m data.build_dataset` on a machine with network access, "
            "then commit `data/static/`.",
            icon="⚠️",
        )

    # ---------------- sidebar filters ----------------
    with st.sidebar:
        st.header("Filters")
        quarter = st.selectbox("Quarter (map)", data_access.quarter_options(df))
        region = st.selectbox("NHS region", data_access.region_options(df))
        icb = st.selectbox("Integrated Care Board", data_access.icb_options(df, region))
        contract_types = st.multiselect(
            "Contract type",
            data_access.contract_type_options(df),
            default=[],
            help="Empty selection = all contract types",
        )
        st.divider()
        st.header("Forecast settings")
        method = st.radio(
            "Method",
            ["theil_sen", "ols"],
            format_func=lambda m: "Theil–Sen (robust)" if m == "theil_sen" else "OLS",
        )
        exclude_pre_jump = st.checkbox(
            "Exclude quarters before a detected data jump",
            value=False,
            help=(
                "Quarter-on-quarter count jumps above 10% usually reflect a "
                "change in how the snapshot was extracted, not real openings; "
                "this fits the trend only on quarters after the last jump."
            ),
        )
        show_boundaries = st.checkbox("Show boundary outlines", value=False)

    area_df = data_access.filter_area(df, region, icb, contract_types or None)
    area_label = icb if icb != data_access.ALL_ICBS else region

    # ---------------- map ----------------
    quarter_df = data_access.quarter_slice(area_df, quarter)
    mappable_df = data_access.mappable(quarter_df)
    unmapped = len(quarter_df) - len(mappable_df)

    st.subheader(f"{area_label} — {quarter}")
    st.markdown(
        f"**{len(quarter_df)}** pharmacies in this selection"
        + (
            f" ({unmapped} without coordinates, not shown on the map)"
            if unmapped
            else ""
        )
    )

    boundary_geojson = None
    if show_boundaries:
        boundary_geojson = _load_boundaries(
            "icb"
            if icb != data_access.ALL_ICBS or region == data_access.ALL_ENGLAND
            else "region"
        )
        if boundary_geojson is None:
            st.info(
                "Boundary outlines unavailable (no cached copy and no network "
                "access to the ONS Open Geography Portal)."
            )

    st.plotly_chart(
        map_view.build_map_figure(mappable_df, boundary_geojson),
        use_container_width=True,
    )

    # ---------------- near me ----------------
    st.subheader("📍 Pharmacies near me")
    st.caption(
        "Type an England postcode. The Consolidated Pharmaceutical List "
        "covers England only."
    )
    near_col1, near_col2 = st.columns([2, 1])
    with near_col1:
        user_postcode = st.text_input(
            "Your postcode", placeholder="e.g. M1 1AE", key="user_postcode"
        )
    with near_col2:
        open_now_only = st.checkbox("Open now only", value=False)

    if user_postcode.strip():
        lookup = _load_geo_lookup()
        info = geocode_postcode(user_postcode, lookup)
        if info is None:
            st.error(
                "Could not locate that postcode. Check the spelling — and note "
                "that only England postcodes can be matched."
            )
        elif info.country and info.country != "England":
            st.error(
                f"{user_postcode.upper().strip()} is in {info.country}. "
                "England only — the Consolidated Pharmaceutical List covers "
                "England pharmacies."
            )
        else:
            user_point = GeoPoint(info.lat, info.lon)
            latest_quarter = data_access.quarter_options(df)[0]
            nearest = finder_logic.nearest_pharmacies(
                user_point,
                data_access.quarter_slice(df, latest_quarter),
                n=5,
                open_now_only=open_now_only,
            )
            if nearest.empty:
                st.info("No pharmacies matched (try unticking 'Open now only').")
            else:
                st.markdown(
                    f"Nearest pharmacies to **{user_postcode.upper().strip()}** "
                    f"({latest_quarter} list):"
                )
                display = nearest.rename(
                    columns={
                        "name": "Pharmacy",
                        "address": "Address",
                        "postcode": "Postcode",
                        "contract_type": "Contract",
                        "distance_km": "Distance (km)",
                        "walking_minutes": "Walk (min)",
                        "open_now": "Open now",
                        "todays_hours": "Today's hours",
                        "maps_url": "Directions",
                    }
                )
                st.dataframe(
                    display,
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        "Directions": st.column_config.LinkColumn(
                            display_text="🚶 Google Maps"
                        )
                    },
                )

    # ---------------- statistics ----------------
    st.subheader(f"📊 How the pharmacy business went — {area_label}")

    trend = compute_area_trend(area_df)
    if not trend.counts:
        st.info("No data for this selection.")
        return

    start_index = 0
    discontinuities = detect_discontinuities(trend.counts)
    if discontinuities:
        st.warning(
            "This series contains at least one quarter-on-quarter jump above "
            "10% — likely a snapshot/extraction artifact rather than real "
            "openings (known issue: the 2025-26 Q1 snapshot counts jump "
            "~23% nationally). Interpret trends with care.",
            icon="⚠️",
        )
        if exclude_pre_jump:
            start_index = discontinuities[-1]

    forecast = forecast_counts(trend, method=method, start_index=start_index)

    metrics = stats_view.headline_metrics(trend)
    tile1, tile2, tile3, tile4 = st.columns(4)
    tile1.metric(f"Pharmacies ({metrics['latest_quarter']})", metrics["current_count"])
    tile2.metric(
        "Net change since first quarter",
        f"{metrics['net_change_total']:+d}",
    )
    tile3.metric("Opened last quarter", metrics["latest_openings"])
    tile4.metric("Closed last quarter", metrics["latest_closures"])

    badge, explanation = stats_view.classification_badge(forecast)
    st.markdown(f"### {badge}")
    st.caption(explanation)

    st.plotly_chart(stats_view.trend_figure(trend, forecast), use_container_width=True)
    st.plotly_chart(stats_view.churn_figure(trend), use_container_width=True)

    if forecast is not None:
        with st.expander("Forecast caveats — read before quoting numbers"):
            for caveat in forecast.caveats:
                st.markdown(f"- {caveat}")
            st.markdown(
                "- Dispensing-volume figures are **not** shown anywhere in "
                "this dashboard: the source list contains none, and the "
                "predecessor project's dispensing numbers were simulated."
            )


main()

"""Streamlit dashboard: England pharmacy map, area statistics, near-me lookup.

Styled to match this portfolio's other NHS tools (the AIF Allocation Tool,
HeartLink) and, in its sidebar "Custom areas" section, adapts the AIF
Allocation Tool's core mechanic — build a named place by aggregating base
geographic units, save/compare/delete it, export or re-import the whole set
as JSON — to this dataset's ICB-level granularity.

Run from the repository root:

    streamlit run dashboard/app.py
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

# streamlit runs this file as a script, so make the repo root importable.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from dashboard import (  # noqa: E402
    area_builder,
    data_access,
    finder_logic,
    map_view,
    stats_view,
    theme,
)
from src.geo import boundaries as boundaries_module  # noqa: E402
from src.geo.lookup_store import geocode_postcode, load_lookup  # noqa: E402
from src.geo.types import GeoPoint  # noqa: E402
from src.stats.area_stats import (  # noqa: E402
    compute_area_trend,
    detect_discontinuities,
    forecast_counts,
)

st.set_page_config(
    page_title="England Pharmacy Map",
    page_icon="https://www.england.nhs.uk/wp-content/themes/nhsengland/static/img/favicon.ico",
    layout="wide",
    menu_items={
        "Get Help": "https://opendata.nhsbsa.net/dataset/consolidated-pharmaceutical-list",
        "Report a bug": "https://github.com/chaeyoonakim/pharmaceutical-list-england/issues",
        "About": (
            "Interactive map, near-me finder and area statistics for "
            "England's community pharmacies, built on the NHSBSA "
            "Consolidated Pharmaceutical List."
        ),
    },
)

METHODOLOGY_TEXT = """England Pharmacy Map — methodology notes

Counts are unique pharmacy ODS codes per quarterly snapshot for the
selected area.

Openings/closures are set differences of ODS codes between consecutive
snapshots — true churn, not just net count deltas.

Next-year outlook fits a Theil-Sen line (median of pairwise slopes; OLS
available as an option) to the quarterly counts and projects four quarters
ahead with an approximate +/-1.96 sigma residual band, classified as
growth / stable / decline at a +/-1% projected-change threshold.

Snapshot discontinuities: quarter-on-quarter jumps above 10% are flagged
as likely extraction artifacts, with a toggle to fit the trend on
post-jump quarters only.

Data source: NHSBSA Open Data Portal, Consolidated Pharmaceutical List.
Contains public sector information licensed under the Open Government
Licence v3.0.
"""


@st.cache_data(show_spinner="Loading pharmacy data…")
def _load_dataset() -> tuple[pd.DataFrame, str]:
    return data_access.load_dataset()


@st.cache_data(show_spinner=False)
def _load_boundaries(kind: str) -> dict | None:
    return boundaries_module.get_boundaries("region" if kind == "region" else "icb")


@st.cache_data(show_spinner=False)
def _load_geo_lookup() -> pd.DataFrame:
    return load_lookup().frame


def _custom_areas() -> dict[str, area_builder.CustomArea]:
    if "custom_areas" not in st.session_state:
        st.session_state.custom_areas = {}
    areas: dict[str, area_builder.CustomArea] = st.session_state.custom_areas
    return areas


def _render_area_builder_sidebar(df: pd.DataFrame) -> area_builder.CustomArea | None:
    """The "Custom areas" sidebar section; returns the currently selected area."""
    areas = _custom_areas()

    st.header("Custom areas")
    st.caption(
        "Combine ICBs into a named area to compare — the same place-based "
        "approach as the NHS AIF Allocation Tool, applied at ICB level."
    )

    all_icbs = sorted(i for i in df["icb_name"].dropna().unique() if i)
    new_area_icbs = st.multiselect("ICBs to combine", all_icbs, key="new_area_icbs")
    new_area_name = st.text_input("Name this area", key="new_area_name")

    if st.button("Save area"):
        error = area_builder.validate_area_name(new_area_name, areas)
        if error:
            st.error(error)
        elif not new_area_icbs:
            st.error("Please select one or more ICBs.")
        else:
            areas[new_area_name.strip()] = area_builder.CustomArea(
                name=new_area_name.strip(), icb_names=tuple(new_area_icbs)
            )
            st.success(f"Saved '{new_area_name.strip()}'.")

    selected: area_builder.CustomArea | None = None
    if areas:
        choice = st.selectbox("View a saved area", ["None", *areas.keys()])
        if choice != "None":
            selected = areas[choice]
            if st.button("Delete this area"):
                del areas[choice]
                st.rerun()

    with st.expander("Advanced options"):
        st.download_button(
            "Download custom areas as JSON",
            data=area_builder.serialise_areas(areas),
            file_name="custom_areas.json",
            mime="application/json",
        )
        uploaded = st.file_uploader("Upload custom areas JSON", type=["json"])
        if uploaded is not None:
            try:
                st.session_state.custom_areas = area_builder.deserialise_areas(
                    uploaded.read().decode("utf-8")
                )
                st.success("Custom areas loaded.")
                st.rerun()
            except (ValueError, KeyError) as exc:
                st.error(f"Could not read that file: {exc}")

    return selected


def main() -> None:
    df, provenance = _load_dataset()

    theme.inject_style()
    theme.render_header(
        "England Pharmacy Map",
        "NHSBSA Consolidated Pharmaceutical List · interactive map, near-me "
        "finder and area statistics",
    )
    st.caption(
        f"Quarterly snapshots {df['quarter_label'].min()} – "
        f"{df['quarter_label'].max()} · Contains public sector information "
        "licensed under OGL v3.0"
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
        selected_area = _render_area_builder_sidebar(df)
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

    if selected_area is not None:
        area_df = area_builder.filter_by_area(df, selected_area, contract_types or None)
        area_label = selected_area.name
    else:
        area_df = data_access.filter_area(df, region, icb, contract_types or None)
        area_label = icb if icb != data_access.ALL_ICBS else region

    latest_quarter = data_access.quarter_options(df)[0]

    # ---------------- near me ----------------
    user_point: GeoPoint | None = None
    with st.container(border=True):
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
                    "Could not locate that postcode. Check the spelling — and "
                    "note that only England postcodes can be matched."
                )
            elif info.country and info.country != "England":
                st.error(
                    f"{user_postcode.upper().strip()} is in {info.country}. "
                    "England only — the Consolidated Pharmaceutical List covers "
                    "England pharmacies."
                )
            else:
                user_point = GeoPoint(info.lat, info.lon)
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
                        f"({latest_quarter} list) — the map below zooms to this "
                        "location:"
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

    # ---------------- map ----------------
    # A postcode search narrows the map's scope to that location; otherwise
    # the map's scope follows the sidebar's region/ICB/custom-area filter.
    if user_point is not None:
        map_scope_df = data_access.quarter_slice(df, latest_quarter)
        if contract_types:
            map_scope_df = map_scope_df[
                map_scope_df["contract_type"].isin(contract_types)
            ]
        map_label = f"Near {user_postcode.upper().strip()}"
    else:
        map_scope_df = data_access.quarter_slice(area_df, quarter)
        map_label = f"{area_label} — {quarter}"
    mappable_df = data_access.mappable(map_scope_df)
    unmapped = len(map_scope_df) - len(mappable_df)

    with st.container(border=True):
        st.subheader(map_label)
        st.markdown(
            f"**{len(map_scope_df)}** pharmacies in this selection"
            + (
                f" ({unmapped} without coordinates, not shown on the map)"
                if unmapped
                else ""
            )
        )

        boundary_geojson = None
        if show_boundaries and user_point is None:
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
            map_view.build_map_figure(
                mappable_df,
                boundary_geojson,
                user_point=(user_point.lat, user_point.lon)
                if user_point is not None
                else None,
            ),
            use_container_width=True,
        )

    # ---------------- statistics ----------------
    with st.container(border=True):
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
        tile1.metric(
            f"Pharmacies ({metrics['latest_quarter']})", metrics["current_count"]
        )
        tile2.metric(
            "Net change since first quarter",
            f"{metrics['net_change_total']:+d}",
        )
        tile3.metric("Opened last quarter", metrics["latest_openings"])
        tile4.metric("Closed last quarter", metrics["latest_closures"])

        badge, explanation = stats_view.classification_badge(forecast)
        st.markdown(f"### {badge}", unsafe_allow_html=True)
        st.caption(explanation)

        st.plotly_chart(
            stats_view.trend_figure(trend, forecast), use_container_width=True
        )
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

        csv_bytes = area_df.to_csv(index=False).encode("utf-8")
        current_date = datetime.now().strftime("%Y-%m-%d")
        zip_bytes = area_builder.build_export_zip(
            csv_bytes,
            area_builder.serialise_areas(_custom_areas()),
            METHODOLOGY_TEXT,
        )
        st.download_button(
            label="Download ZIP (area data + custom areas + methodology)",
            data=zip_bytes,
            file_name=f"england-pharmacy-map {current_date}.zip",
            mime="application/zip",
        )

    st.subheader("Help and Support")
    with st.expander("About this tool"):
        st.markdown(
            "This dashboard tracks England's community pharmacy network "
            "using the NHSBSA Consolidated Pharmaceutical List. Use the "
            "sidebar to filter by NHS region, ICB, or a custom area built "
            "from several ICBs, or search for the pharmacies nearest any "
            "England postcode."
        )
        st.markdown(
            "Source code: "
            "[github.com/chaeyoonakim/pharmaceutical-list-england]"
            "(https://github.com/chaeyoonakim/pharmaceutical-list-england)"
        )
    st.info(
        "For questions about this tool, open an issue on "
        "[GitHub](https://github.com/chaeyoonakim/pharmaceutical-list-england/issues)."
    )


main()

"""Custom-area builder — pure logic (no Streamlit imports, no session state).

Adapts the NHS AIF Allocation Tool's core mechanic — define a "place" by
aggregating base geographic units, name it, save it, compare it, export/
import the whole set as JSON — to this dataset's ICB-level granularity: a
custom "area" here is a named combination of one or more Integrated Care
Boards rather than GP practices.
"""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass

import pandas as pd

RESERVED_NAMES = {""}


@dataclass(frozen=True)
class CustomArea:
    """A user-named combination of ICBs."""

    name: str
    icb_names: tuple[str, ...]


def validate_area_name(name: str, existing: dict[str, CustomArea]) -> str | None:
    """None if ``name`` is usable, else a user-facing error message."""
    stripped = name.strip()
    if stripped in RESERVED_NAMES:
        return "Please give your area a name."
    if stripped in existing:
        return f"An area named '{stripped}' already exists."
    return None


def filter_by_area(
    df: pd.DataFrame,
    area: CustomArea,
    contract_types: list[str] | None = None,
) -> pd.DataFrame:
    """Rows for every ICB in ``area``, across all quarters."""
    result = df[df["icb_name"].isin(area.icb_names)]
    if contract_types:
        result = result[result["contract_type"].isin(contract_types)]
    return result


def serialise_areas(areas: dict[str, CustomArea]) -> str:
    """Custom areas as JSON, for the "download session" button."""
    payload = {name: list(area.icb_names) for name, area in areas.items()}
    return json.dumps(payload, indent=2, sort_keys=False)


def deserialise_areas(raw: str) -> dict[str, CustomArea]:
    """Parse JSON produced by :func:`serialise_areas` (or hand-written)."""
    payload = json.loads(raw)
    return {
        name: CustomArea(name=name, icb_names=tuple(icbs))
        for name, icbs in payload.items()
    }


def build_export_zip(
    csv_bytes: bytes, session_json: str, methodology_text: str
) -> bytes:
    """A downloadable ZIP: area data CSV + saved-areas JSON + methodology notes.

    Mirrors the AIF Allocation Tool's "Download ZIP" bundle (data + session
    config + documentation) so the export is self-explanatory offline.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        zip_file.writestr("pharmacy_area_data.csv", csv_bytes)
        zip_file.writestr("custom_areas.json", session_json)
        zip_file.writestr("methodology.txt", methodology_text)
    return buffer.getvalue()

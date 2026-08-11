"""Postcode-area → NHS region heuristic, used only when geocoding has no answer.

Ported from pharmacy-analysis-with-open-data/mapping/postcode_mapper.py with
its ordering bugs fixed: the original used a startswith ladder where "N"
shadowed "NW"/"NE"/"NG"…, "W" shadowed "WA"/"WV"/"WS"…, and "SP" appeared in
two regions. Matching here extracts the true postcode area (the leading
letters) with a regex and does a single dict lookup, so no prefix can shadow
another. This remains a heuristic — postcode areas do not align perfectly
with NHS region boundaries; prefer the geocoded ICB-based region wherever
available.
"""

from __future__ import annotations

import re

from src.geo.types import normalise_postcode

UNKNOWN_REGION = "Unknown"

_REGION_AREAS: dict[str, list[str]] = {
    "East of England": ["CB", "CM", "CO", "IP", "NR", "PE", "SG", "SS"],
    "London": [
        "BR",
        "CR",
        "DA",
        "E",
        "EC",
        "EN",
        "HA",
        "IG",
        "KT",
        "N",
        "NW",
        "RM",
        "SE",
        "SM",
        "SW",
        "TW",
        "UB",
        "W",
        "WC",
        "WD",
    ],
    "Midlands": [
        "B",
        "CV",
        "DE",
        "DY",
        "LE",
        "LN",
        "NG",
        "NN",
        "S",
        "ST",
        "TF",
        "WS",
        "WV",
    ],
    "North East and Yorkshire": [
        "BD",
        "DH",
        "DL",
        "DN",
        "HD",
        "HG",
        "HU",
        "HX",
        "LS",
        "NE",
        "SR",
        "TS",
        "WF",
        "YO",
    ],
    "North West": [
        "BB",
        "BL",
        "CA",
        "CH",
        "CW",
        "FY",
        "L",
        "LA",
        "M",
        "OL",
        "PR",
        "SK",
        "WA",
        "WN",
    ],
    "South East": [
        "AL",
        "BN",
        "CT",
        "GU",
        "HP",
        "LU",
        "ME",
        "MK",
        "OX",
        "PO",
        "RG",
        "RH",
        "SL",
        "SO",
        "TN",
    ],
    "South West": [
        "BA",
        "BH",
        "BS",
        "DT",
        "EX",
        "GL",
        "PL",
        "SN",
        "SP",
        "TA",
        "TQ",
        "TR",
    ],
}

_AREA_TO_REGION: dict[str, str] = {
    area: region for region, areas in _REGION_AREAS.items() for area in areas
}

# The leading letters of a UK postcode (its "area"): 1-2 alpha characters.
_AREA_PATTERN = re.compile(r"^([A-Z]{1,2})\d")


def region_from_postcode(postcode: str) -> str:
    """Heuristic NHS region for a postcode, or "Unknown"."""
    norm = normalise_postcode(postcode)
    match = _AREA_PATTERN.match(norm)
    if not match:
        return UNKNOWN_REGION
    return _AREA_TO_REGION.get(match.group(1), UNKNOWN_REGION)

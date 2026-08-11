"""Postcode geo-lookup persistence and offline-capable geocoding.

The lookup file (postcode, lat, lon, icb_code, icb_name, nhs_region) is built
by ``python -m data.build_geo_lookup`` and committed to ``data/static/`` so
the dashboard works without network. Resolution order: static build →
committed sample fixture. Runtime geocoding of a user's postcode tries the
network first (postcodes.io), then the local lookup, then an outward-code
centroid of the lookup.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.geo import postcode_client
from src.geo.icb_regions import icb_to_region
from src.geo.types import PostcodeInfo, normalise_postcode, outward_code

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
STATIC_LOOKUP_PATH = REPO_ROOT / "data" / "static" / "postcode_geo_lookup.csv.gz"
SAMPLE_LOOKUP_PATH = REPO_ROOT / "data" / "sample" / "sample_geo_lookup.csv"

LOOKUP_COLUMNS = ["postcode", "lat", "lon", "icb_code", "icb_name", "nhs_region"]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LookupResult:
    """A loaded lookup table plus where it came from ("static" or "sample")."""

    frame: pd.DataFrame
    provenance: str


def load_lookup(
    static_path: Path = STATIC_LOOKUP_PATH,
    sample_path: Path = SAMPLE_LOOKUP_PATH,
) -> LookupResult:
    """Load the postcode lookup, preferring the built static file."""
    for path, provenance in [(static_path, "static"), (sample_path, "sample")]:
        if path.exists():
            frame = pd.read_csv(path)
            frame["postcode"] = frame["postcode"].map(normalise_postcode)
            logger.info(f"Loaded {len(frame)} postcodes from {provenance} lookup")
            return LookupResult(frame=frame, provenance=provenance)
    raise FileNotFoundError(
        f"No postcode lookup found at {static_path} or {sample_path}"
    )


def _info_from_row(row: pd.Series, postcode: str) -> PostcodeInfo:
    icb_name = row.get("icb_name")
    icb_name_str = str(icb_name) if pd.notna(icb_name) and icb_name else None
    region = row.get("nhs_region")
    region_str = str(region) if pd.notna(region) and region else None
    code = row.get("icb_code")
    return PostcodeInfo(
        postcode=postcode,
        lat=float(row["lat"]),
        lon=float(row["lon"]),
        icb_code=str(code) if pd.notna(code) and code else None,
        icb_name=icb_name_str,
        nhs_region=region_str or icb_to_region(icb_name_str),
        country="England",
    )


def geocode_postcode(
    postcode: str,
    lookup: pd.DataFrame,
    allow_network: bool = True,
) -> PostcodeInfo | None:
    """Geocode a user-entered postcode.

    Tries postcodes.io (when allowed), then an exact match in the local
    lookup, then the centroid of lookup entries sharing the outward code
    (e.g. "M1"). Returns None when nothing matches.
    """
    norm = normalise_postcode(postcode)
    if not norm:
        return None

    if allow_network:
        live = postcode_client.lookup_single(norm)
        if live is not None:
            return PostcodeInfo(
                postcode=live.postcode,
                lat=live.lat,
                lon=live.lon,
                icb_code=live.icb_code,
                icb_name=live.icb_name,
                nhs_region=icb_to_region(live.icb_name),
                country=live.country,
            )

    exact = lookup[lookup["postcode"] == norm]
    if not exact.empty:
        return _info_from_row(exact.iloc[0], norm)

    ward = outward_code(norm)
    if ward:
        district = lookup[lookup["postcode"].map(outward_code) == ward]
        if not district.empty:
            centroid = district.iloc[0].copy()
            centroid["lat"] = district["lat"].mean()
            centroid["lon"] = district["lon"].mean()
            logger.info(
                f"Postcode {norm} resolved to outward-code centroid of {ward} "
                f"({len(district)} known postcodes)"
            )
            return _info_from_row(centroid, norm)

    return None

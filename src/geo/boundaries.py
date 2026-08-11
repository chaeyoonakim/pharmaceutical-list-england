"""Optional boundary GeoJSON from the ONS Open Geography Portal.

Ultra-generalised (BUC) NHS England Region and ICB boundaries, downloaded on
first use into the gitignored ``cache/geo/boundaries/`` and reused from disk
afterwards. Every failure path returns None — the map renders markers-only
without boundaries, so this module must never raise. URLs live in
``BOUNDARY_SOURCES`` for easy updating when ONS republishes layers.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Literal

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CACHE_DIR = REPO_ROOT / "cache" / "geo" / "boundaries"
REQUEST_TIMEOUT_SECONDS = 60

# ONS Open Geography Portal ArcGIS FeatureServer layers, ultra-generalised
# (BUC = boundary, ultra-generalised, clipped). If a layer 404s, find the
# current one at https://geoportal.statistics.gov.uk and update here.
BOUNDARY_SOURCES: dict[str, str] = {
    "region": (
        "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
        "NHS_England_Regions_July_2022_EN_BUC/FeatureServer/0/query"
        "?where=1%3D1&outFields=*&outSR=4326&f=geojson"
    ),
    "icb": (
        "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
        "Integrated_Care_Boards_July_2023_EN_BUC/FeatureServer/0/query"
        "?where=1%3D1&outFields=*&outSR=4326&f=geojson"
    ),
}

logger = logging.getLogger(__name__)


def get_boundaries(
    kind: Literal["region", "icb"],
    cache_dir: Path = DEFAULT_CACHE_DIR,
    session: requests.Session | None = None,
) -> dict[str, Any] | None:
    """Boundary GeoJSON for NHS regions or ICBs, cached on disk.

    Returns the parsed GeoJSON dict, or None when neither cache nor network
    can provide it (non-fatal: callers render without boundaries).
    """
    cache_file = cache_dir / f"{kind}_buc.geojson"

    if cache_file.exists():
        try:
            with open(cache_file, encoding="utf-8") as f:
                data: dict[str, Any] = json.load(f)
            return data
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Ignoring corrupt boundary cache {cache_file}: {e}")

    url = BOUNDARY_SOURCES.get(kind)
    if url is None:
        return None

    http = session or requests.Session()
    try:
        response = http.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        if response.status_code != 200:
            logger.info(
                f"Boundary download for {kind} failed: HTTP {response.status_code}"
            )
            return None
        geojson: dict[str, Any] = response.json()
        if geojson.get("type") != "FeatureCollection":
            logger.info(f"Boundary response for {kind} is not GeoJSON — skipping")
            return None
    except (requests.RequestException, json.JSONDecodeError) as e:
        logger.info(f"Boundary download for {kind} unavailable: {e}")
        return None

    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(geojson, f)
    except OSError as e:
        logger.warning(f"Could not cache {kind} boundaries: {e}")

    return geojson

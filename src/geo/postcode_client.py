"""postcodes.io client for geocoding and ICB attribution.

postcodes.io serves ONS/OS open data (OGL v3.0). The bulk endpoint accepts up
to 100 postcodes per request. The ``codes`` block's field names for health
geographies have drifted over the years (ccg → sub-ICB locations → ICB), so
parsing is deliberately defensive and centralised in ``_parse_result`` —
re-verify against a live response when first running a full build.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from typing import Any

import requests

from src.geo.types import PostcodeInfo, normalise_postcode

POSTCODES_IO_URL = "https://api.postcodes.io/postcodes"
BULK_BATCH_SIZE = 100
REQUEST_TIMEOUT_SECONDS = 30
DELAY_BETWEEN_REQUESTS_SECONDS = 0.2

logger = logging.getLogger(__name__)


def _parse_result(result: dict[str, Any]) -> PostcodeInfo | None:
    """Parse one postcodes.io result object into PostcodeInfo.

    Handles field-name drift: the ICB name may appear under ``icb`` (current)
    or ``ccg`` (legacy); its code under ``codes.icb`` or ``codes.ccg``.
    """
    postcode = result.get("postcode")
    lat = result.get("latitude")
    lon = result.get("longitude")
    if not postcode or lat is None or lon is None:
        return None

    codes = result.get("codes") or {}
    icb_name = result.get("icb") or result.get("ccg")
    icb_code = codes.get("icb") or codes.get("ccg")

    return PostcodeInfo(
        postcode=normalise_postcode(str(postcode)),
        lat=float(lat),
        lon=float(lon),
        icb_code=str(icb_code) if icb_code else None,
        icb_name=str(icb_name) if icb_name else None,
        country=result.get("country"),
    )


def lookup_single(
    postcode: str, session: requests.Session | None = None
) -> PostcodeInfo | None:
    """Geocode one postcode. Returns None when unknown or on any failure."""
    norm = normalise_postcode(postcode)
    if not norm:
        return None
    http = session or requests.Session()
    try:
        response = http.get(
            f"{POSTCODES_IO_URL}/{norm}", timeout=REQUEST_TIMEOUT_SECONDS
        )
        if response.status_code != 200:
            logger.info(f"postcodes.io returned {response.status_code} for {norm}")
            return None
        payload = response.json()
        result = payload.get("result")
        if not isinstance(result, dict):
            return None
        return _parse_result(result)
    except requests.RequestException as e:
        logger.warning(f"postcodes.io lookup failed for {norm}: {e}")
        return None


def bulk_lookup(
    postcodes: Sequence[str],
    session: requests.Session | None = None,
    batch_size: int = BULK_BATCH_SIZE,
) -> dict[str, PostcodeInfo]:
    """Geocode many postcodes via the bulk endpoint.

    Returns a mapping keyed by normalised postcode; postcodes the API cannot
    resolve are simply absent. Failed batches are logged and skipped so a
    long build survives transient errors.
    """
    http = session or requests.Session()
    unique = sorted({normalise_postcode(p) for p in postcodes} - {""})
    results: dict[str, PostcodeInfo] = {}

    for start in range(0, len(unique), batch_size):
        batch = unique[start : start + batch_size]
        try:
            response = http.post(
                POSTCODES_IO_URL,
                json={"postcodes": batch},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            if response.status_code != 200:
                logger.warning(
                    f"Bulk lookup batch {start // batch_size + 1} failed: "
                    f"HTTP {response.status_code}"
                )
                continue
            payload = response.json()
            for entry in payload.get("result") or []:
                parsed = _parse_result(entry.get("result") or {})
                if parsed is not None:
                    results[parsed.postcode] = parsed
        except requests.RequestException as e:
            logger.warning(f"Bulk lookup batch {start // batch_size + 1} failed: {e}")
        time.sleep(DELAY_BETWEEN_REQUESTS_SECONDS)

    logger.info(f"Geocoded {len(results)}/{len(unique)} unique postcodes")
    return results

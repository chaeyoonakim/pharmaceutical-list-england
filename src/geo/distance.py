"""Great-circle distance helpers (Haversine), scalar and vectorised.

Scalar version ported from pharmacy-analysis-with-open-data's
pharmacy_finder.py; the vectorised variant ranks thousands of pharmacies
against one user location in a single numpy pass.
"""

from __future__ import annotations

import math

import numpy as np
import numpy.typing as npt

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in km between two WGS84 points."""
    rlat1, rlon1, rlat2, rlon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def haversine_km_vec(
    lat: float,
    lon: float,
    lats: npt.NDArray[np.float64],
    lons: npt.NDArray[np.float64],
) -> npt.NDArray[np.float64]:
    """Distances in km from one point to arrays of points."""
    rlat = math.radians(lat)
    rlon = math.radians(lon)
    rlats = np.radians(lats)
    rlons = np.radians(lons)
    dlat = rlats - rlat
    dlon = rlons - rlon
    a = np.sin(dlat / 2) ** 2 + math.cos(rlat) * np.cos(rlats) * np.sin(dlon / 2) ** 2
    result: npt.NDArray[np.float64] = 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))
    return result

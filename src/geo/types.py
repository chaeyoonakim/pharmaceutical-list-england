"""Shared geo dataclasses."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GeoPoint:
    """A WGS84 coordinate."""

    lat: float
    lon: float


@dataclass(frozen=True)
class PostcodeInfo:
    """Geocoding result for one postcode."""

    postcode: str
    lat: float
    lon: float
    icb_code: str | None = None
    icb_name: str | None = None
    nhs_region: str | None = None
    country: str | None = None


def normalise_postcode(postcode: str) -> str:
    """Normalise a postcode for joining: uppercase, no internal spaces.

    "m1  1ae" → "M11AE". Returns "" for non-string/blank input.
    """
    if not isinstance(postcode, str):
        return ""
    return "".join(postcode.split()).upper()


def outward_code(postcode: str) -> str:
    """The outward (district) part of a normalised postcode, e.g. "M11AE" → "M1".

    The inward part of a full UK postcode is always 3 characters (digit +
    two letters), so strip 3 from a normalised full postcode. Returns the
    input unchanged when too short to split.
    """
    norm = normalise_postcode(postcode)
    if len(norm) > 3:
        return norm[:-3]
    return norm

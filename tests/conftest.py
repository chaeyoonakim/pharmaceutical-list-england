"""Shared fixtures: the committed sample data, loaded the way the app loads it."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DIR = REPO_ROOT / "data" / "sample"


@pytest.fixture(scope="session")
def sample_raw_by_resource() -> dict[str, pd.DataFrame]:
    """Sample pharmacies split per quarterly resource, mimicking API output."""
    df = pd.read_csv(SAMPLE_DIR / "sample_pharmacies.csv")
    return {
        resource_id: group.drop(columns=["resource_id"]).reset_index(drop=True)
        for resource_id, group in df.groupby("resource_id", sort=False)
    }


@pytest.fixture(scope="session")
def sample_geo_lookup() -> pd.DataFrame:
    """Sample postcode → (lat, lon, ICB, region) lookup."""
    return pd.read_csv(SAMPLE_DIR / "sample_geo_lookup.csv")

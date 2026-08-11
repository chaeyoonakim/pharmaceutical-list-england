"""Tests for data.extract — caching and skip-on-missing, all HTTP mocked."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pandas as pd
import pytest

from data.extract import EXTRACT_CONFIG, DataExtractor


class _FakeResponse:
    """Minimal stand-in for urllib's HTTP response context manager."""

    def __init__(self, payload: dict[str, Any], status: int = 200) -> None:
        self.status = status
        self._body = io.BytesIO(json.dumps(payload).encode("utf-8"))

    def read(self) -> bytes:
        return self._body.read()

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _success_payload(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {"success": True, "result": {"records": records, "total": len(records)}}


def _make_extractor(tmp_path: Path, cache_enabled: bool = True) -> DataExtractor:
    config = dict(EXTRACT_CONFIG["api"])
    config["cache_enabled"] = cache_enabled
    config["delay_between_requests"] = 0
    extractor = DataExtractor(config)
    extractor.cache_dir = str(tmp_path)
    return extractor


def test_extract_data_parses_records(tmp_path: Path) -> None:
    extractor = _make_extractor(tmp_path, cache_enabled=False)
    payload = _success_payload([{"PHARMACY_ODS_CODE_F_CODE": "FX001"}])
    with patch(
        "data.extract.urllib.request.urlopen", return_value=_FakeResponse(payload)
    ):
        df = extractor.extract_data("CONSOL_PHARMACY_LIST_202223Q2")
    assert len(df) == 1
    assert df.iloc[0]["PHARMACY_ODS_CODE_F_CODE"] == "FX001"


def test_extract_data_caches_and_reuses(tmp_path: Path) -> None:
    extractor = _make_extractor(tmp_path)
    payload = _success_payload([{"PHARMACY_ODS_CODE_F_CODE": "FX001"}])
    with patch(
        "data.extract.urllib.request.urlopen", return_value=_FakeResponse(payload)
    ) as mocked:
        extractor.extract_data("RES_A", limit=10)
        assert mocked.call_count == 1
    # Second call must be served from cache without any HTTP.
    with patch("data.extract.urllib.request.urlopen") as mocked:
        df = extractor.extract_data("RES_A", limit=10)
        mocked.assert_not_called()
    assert len(df) == 1


def test_unknown_resource_returns_empty_not_crash(tmp_path: Path) -> None:
    extractor = _make_extractor(tmp_path, cache_enabled=False)
    payload = {"success": False, "error": {"message": "Not found"}}
    with patch(
        "data.extract.urllib.request.urlopen", return_value=_FakeResponse(payload)
    ):
        df = extractor.extract_data("CONSOL_PHARMACY_LIST_209999Q9")
    assert df.empty


def test_network_error_retries_then_empty(tmp_path: Path) -> None:
    extractor = _make_extractor(tmp_path, cache_enabled=False)
    with patch(
        "data.extract.urllib.request.urlopen", side_effect=OSError("connection refused")
    ) as mocked:
        df = extractor.extract_data("RES_A")
        assert mocked.call_count == extractor.config["retry_attempts"]
    assert df.empty


def test_extract_all_quarters_skips_empty(tmp_path: Path) -> None:
    extractor = _make_extractor(tmp_path, cache_enabled=False)
    good = _success_payload([{"PHARMACY_ODS_CODE_F_CODE": "FX001"}])
    bad = {"success": False}

    def fake_urlopen(url: str, timeout: int = 0) -> _FakeResponse:
        # Only the first configured quarter has data in this scenario.
        first = EXTRACT_CONFIG["quarterly_resources"][0]
        return _FakeResponse(good if first in url else bad)

    with patch("data.extract.urllib.request.urlopen", side_effect=fake_urlopen):
        results = extractor.extract_all_quarters()
    assert list(results.keys()) == [EXTRACT_CONFIG["quarterly_resources"][0]]


def test_extract_count(tmp_path: Path) -> None:
    extractor = _make_extractor(tmp_path, cache_enabled=False)
    payload = {"success": True, "result": {"total": 10378}}
    with patch(
        "data.extract.urllib.request.urlopen", return_value=_FakeResponse(payload)
    ):
        assert extractor.extract_count("RES_A") == 10378


def test_quarterly_resources_are_chronological() -> None:
    resources: list[str] = EXTRACT_CONFIG["quarterly_resources"]
    assert len(resources) == len(set(resources))
    assert resources[0].endswith("202223Q2")
    assert resources[-1].endswith("202526Q1FINAL")


def test_cached_frame_roundtrip(tmp_path: Path) -> None:
    extractor = _make_extractor(tmp_path)
    df = pd.DataFrame({"A": [1, 2]})
    cache_file = str(tmp_path / "roundtrip.csv")
    extractor._save_to_cache(df, cache_file)
    loaded = extractor._load_from_cache(cache_file)
    assert loaded is not None
    pd.testing.assert_frame_equal(loaded, df)


@pytest.mark.parametrize("hours", [0, 48])
def test_cache_validity_window(tmp_path: Path, hours: int) -> None:
    import os
    import time as time_module

    extractor = _make_extractor(tmp_path)
    cache_file = str(tmp_path / "age.csv")
    pd.DataFrame({"A": [1]}).to_csv(cache_file, index=False)
    stamp = time_module.time() - hours * 3600
    os.utime(cache_file, (stamp, stamp))
    assert extractor._is_cache_valid(cache_file) == (hours == 0)

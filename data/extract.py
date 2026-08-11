"""Data extraction from the NHSBSA Open Data Portal.

Ported from pharmacy-analysis-with-open-data/data/extract.py, keeping its
retry, caching, and rate-limiting behaviour. ``EXTRACT_CONFIG`` below holds
the hardcoded quarterly resource list: to adopt a newly published quarter,
append its resource ID to ``quarterly_resources``. Resources the API does not
recognise are logged and yield an empty frame, so speculative additions are
safe — callers skip empty results.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

EXTRACT_CONFIG: dict[str, Any] = {
    "api": {
        "root_url": "https://opendata.nhsbsa.net/api/3/action/datastore_search",
        "timeout_seconds": 30,
        "retry_attempts": 3,
        "delay_between_requests": 1,
        "cache_enabled": True,
        "cache_duration_hours": 24,
    },
    # One snapshot per quarter. Append new resource IDs here as NHSBSA
    # publishes them (see the dataset page for current names).
    "quarterly_resources": [
        "CONSOL_PHARMACY_LIST_202223Q2",
        "CONSOL_PHARMACY_LIST_202223Q3",
        "CONSOL_PHARMACY_LIST_202223Q4",
        "CONSOL_PHARMACY_LIST_202324Q1",
        "CONSOL_PHARMACY_LIST_202324Q2",
        "CONSOL_PHARMACY_LIST_202324Q3",
        "CONSOL_PHARMACY_LIST_202324Q4",
        "CONSOL_PHARMACY_LIST_202425Q1",
        "CONSOL_PHARMACY_LIST_202425Q2",
        "CONSOL_PHARMACY_LIST_202425Q3",
        "CONSOL_PHARMACY_LIST_202425Q4FINAL",
        "CONSOL_PHARMACY_LIST_202526Q1FINAL",
    ],
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - EXTRACT - %(levelname)s - %(message)s",
)


class DataExtractor:
    """Extracts pharmacy data from the NHSBSA API with retries and caching.

    Attributes:
        config: API configuration dictionary.
        logger: Logger for extraction operations.
        cache_dir: Directory for cached API responses (repo-root ``cache/``).
        request_count: Total number of API requests made.
        start_time: Timestamp when the extractor was created.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config: dict[str, Any] = config or EXTRACT_CONFIG["api"]
        self.logger = logging.getLogger(__name__)
        self.cache_dir = os.path.join(os.path.dirname(__file__), "..", "cache")
        self._ensure_cache_directory()
        self.request_count = 0
        self.start_time = datetime.now()

    def _ensure_cache_directory(self) -> None:
        """Ensure cache directory exists."""
        if self.config.get("cache_enabled", False):
            os.makedirs(self.cache_dir, exist_ok=True)

    def _get_cache_key(
        self, resource_id: str, limit: int, query_filter: dict[str, Any] | None = None
    ) -> str:
        """Generate cache key for a request."""
        cache_data = f"{resource_id}_{limit}_{query_filter}"
        return hashlib.md5(cache_data.encode()).hexdigest()

    def _is_cache_valid(self, cache_file: str) -> bool:
        """Check if a cache file is still fresh."""
        if not os.path.exists(cache_file):
            return False
        cache_age = datetime.now() - datetime.fromtimestamp(
            os.path.getmtime(cache_file)
        )
        max_age = timedelta(hours=self.config.get("cache_duration_hours", 24))
        return cache_age < max_age

    def _load_from_cache(self, cache_file: str) -> pd.DataFrame | None:
        """Load data from a cache file, or None if absent/stale/broken."""
        try:
            if self._is_cache_valid(cache_file):
                df = pd.read_csv(cache_file)
                self.logger.info(f"Loaded {len(df)} records from cache")
                return df
        except Exception as e:
            self.logger.warning(f"Failed to load from cache: {e}")
        return None

    def _save_to_cache(self, df: pd.DataFrame, cache_file: str) -> None:
        """Save data to a cache file (best-effort)."""
        try:
            df.to_csv(cache_file, index=False)
            self.logger.info(f"Cached {len(df)} records")
        except Exception as e:
            self.logger.warning(f"Failed to save to cache: {e}")

    def extract_count(self, resource_id: str) -> int:
        """Fetch only the record count for a resource (limit=0 request)."""
        api_url = f"{self.config['root_url']}?resource_id={resource_id}&limit=0"

        for attempt in range(self.config["retry_attempts"]):
            try:
                self.logger.info(
                    f"Extracting count for {resource_id} (attempt {attempt + 1})"
                )
                with urllib.request.urlopen(
                    api_url, timeout=self.config["timeout_seconds"]
                ) as response:
                    if response.status == 200:
                        result = json.loads(response.read().decode("utf-8"))
                        if result.get("success") and "result" in result:
                            count = int(result["result"].get("total", 0))
                            self.logger.info(f"Successfully extracted count: {count}")
                            return count
                        self.logger.warning(
                            f"API returned success=False for {resource_id} — skipping"
                        )
                        return 0
                    self.logger.error(
                        f"API request failed with status: {response.status}"
                    )
                    return 0
            except Exception as e:
                self.logger.error(
                    f"Error extracting count (attempt {attempt + 1}): {e}"
                )
                if attempt < self.config["retry_attempts"] - 1:
                    time.sleep(self.config["delay_between_requests"])
                    continue
                return 0
        return 0

    def extract_data(
        self,
        resource_id: str,
        limit: int = 20000,
        query_filter: dict[str, Any] | None = None,
    ) -> pd.DataFrame:
        """Fetch pharmacy records for a resource, using the 24h disk cache.

        Returns an empty DataFrame when the resource is unknown to the API or
        the request fails, logging the reason — so an unpublished quarter in
        ``quarterly_resources`` degrades to a skipped quarter, not a crash.
        """
        cache_file = ""
        if self.config.get("cache_enabled", False):
            cache_key = self._get_cache_key(resource_id, limit, query_filter)
            cache_file = os.path.join(self.cache_dir, f"{cache_key}.csv")
            cached_data = self._load_from_cache(cache_file)
            if cached_data is not None:
                return cached_data

        api_url = f"{self.config['root_url']}?resource_id={resource_id}&limit={limit}"
        if query_filter:
            encoded_query = urllib.parse.quote(json.dumps(query_filter))
            api_url += f"&q={encoded_query}"

        for attempt in range(self.config["retry_attempts"]):
            try:
                self.logger.info(
                    f"Extracting data for {resource_id} (attempt {attempt + 1})"
                )
                self.request_count += 1
                with urllib.request.urlopen(
                    api_url, timeout=self.config["timeout_seconds"]
                ) as response:
                    if response.status == 200:
                        result = json.loads(response.read().decode("utf-8"))
                        if result.get("success") and "records" in result.get(
                            "result", {}
                        ):
                            df = pd.DataFrame(result["result"]["records"])
                            self.logger.info(
                                f"Successfully extracted {len(df)} records"
                            )
                            if self.config.get("cache_enabled", False) and cache_file:
                                self._save_to_cache(df, cache_file)
                            return df
                        self.logger.warning(
                            f"No records found for {resource_id} — skipping"
                        )
                        return pd.DataFrame()
                    self.logger.error(
                        f"API request failed with status: {response.status}"
                    )
                    return pd.DataFrame()
            except Exception as e:
                self.logger.error(f"Error extracting data (attempt {attempt + 1}): {e}")
                if attempt < self.config["retry_attempts"] - 1:
                    time.sleep(self.config["delay_between_requests"])
                    continue
                return pd.DataFrame()
        return pd.DataFrame()

    def extract_all_quarters(self, limit: int = 20000) -> dict[str, pd.DataFrame]:
        """Fetch every configured quarterly resource, skipping unavailable ones.

        Returns a mapping of resource_id to its records, in the configured
        (chronological) order. Empty results are logged and omitted.
        """
        results: dict[str, pd.DataFrame] = {}
        for resource_id in EXTRACT_CONFIG["quarterly_resources"]:
            df = self.extract_data(resource_id, limit)
            if df.empty:
                self.logger.warning(f"Skipping {resource_id}: no data returned")
                continue
            results[resource_id] = df
            time.sleep(self.config["delay_between_requests"])
        return results

    def extract_multiple_counts(self, resource_ids: list[str]) -> dict[str, int]:
        """Fetch counts for multiple resources with polite rate limiting."""
        results: dict[str, int] = {}
        for resource_id in resource_ids:
            results[resource_id] = self.extract_count(resource_id)
            time.sleep(self.config["delay_between_requests"])
        return results

    def extract_latest_data(
        self, limit: int = 20000, query_filter: dict[str, Any] | None = None
    ) -> pd.DataFrame:
        """Fetch records from the most recent configured quarter."""
        latest_resource = EXTRACT_CONFIG["quarterly_resources"][-1]
        return self.extract_data(latest_resource, limit, query_filter)

    def extract_latest_count(self) -> int:
        """Fetch the record count of the most recent configured quarter."""
        latest_resource = EXTRACT_CONFIG["quarterly_resources"][-1]
        return self.extract_count(latest_resource)


if __name__ == "__main__":
    extractor = DataExtractor()
    print(f"Latest quarter pharmacy count: {extractor.extract_latest_count()}")

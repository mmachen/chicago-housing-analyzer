"""Automated Redfin listing download.

Redfin has no official public API. This module calls the same CSV-export
endpoint that the "Download All" link on a search-results page uses, with the
search filters from ``housing.config`` applied server-side.

Keep usage light: automated access is a gray area under Redfin's terms of
use, so this makes a single polite request per run — the same load as
clicking the download link yourself. Don't run it in a tight loop.
"""

from __future__ import annotations

import io
import urllib.parse
import urllib.request

import pandas as pd

from housing.config import (
    REDFIN_COLUMNS,
    REDFIN_PROPERTY_TYPES,
    REDFIN_REGION_ID,
    REDFIN_REGION_TYPE,
    REDFIN_SEARCH_FILTERS,
)

EXPORT_URL = "https://www.redfin.com/stingray/api/gis-csv"

# A browser-like user agent; the endpoint rejects the default urllib one.
_USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
               "AppleWebKit/537.36 (KHTML, like Gecko) "
               "Chrome/126.0.0.0 Safari/537.36")

_MAX_HOMES = 350  # largest value the export endpoint accepts


def build_search_url() -> str:
    """Build the CSV-export URL for the configured search."""
    params = {
        "al": 1,
        "region_id": REDFIN_REGION_ID,
        "region_type": REDFIN_REGION_TYPE,
        "status": 9,          # active listings
        "uipt": REDFIN_PROPERTY_TYPES,
        "sf": "1,2,3,5,6,7",  # standard for-sale types
        "num_homes": _MAX_HOMES,
        "v": 8,
        **REDFIN_SEARCH_FILTERS,
    }
    return f"{EXPORT_URL}?{urllib.parse.urlencode(params)}"


def download_listings() -> pd.DataFrame:
    """Download the configured search as a DataFrame (raw Redfin columns).

    Raises RuntimeError if the response doesn't look like the expected CSV,
    so a Redfin format change can't silently corrupt the dataset.
    """
    request = urllib.request.Request(build_search_url(),
                                     headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        text = response.read().decode("utf-8-sig")

    # Errors come back as JSON prefixed with "{}&&" instead of CSV.
    if text.startswith("{}&&"):
        raise RuntimeError(f"Redfin returned an error: {text[4:200]}")

    listings = pd.read_csv(io.StringIO(text))
    if len(listings.columns) != len(REDFIN_COLUMNS):
        raise RuntimeError(
            f"Unexpected CSV format from Redfin: got {len(listings.columns)} "
            f"columns, expected {len(REDFIN_COLUMNS)}. The export format may "
            f"have changed.")
    if len(listings) >= _MAX_HOMES:
        print(f"Warning: hit the {_MAX_HOMES}-home export cap; "
              f"narrow the search filters to see everything.")
    return listings

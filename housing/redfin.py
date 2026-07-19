"""Automated Redfin listing download.

Redfin has no official public API. This module calls the same CSV-export
endpoint that the "Download All" link on a search-results page uses, with the
search filters from ``housing.config`` applied server-side.

Two important behaviors of that endpoint:

- **Login**: MLS-listed homes (Active/Contingent/Pending) are only returned
  to signed-in sessions; anonymous requests get just Redfin's own
  "early access" (Pre On-Market) pool. Configure your redfin.com cookie
  (config.REDFIN_COOKIE_FILE or the REDFIN_COOKIE env var) to get everything.
- **Cap**: at most 350 rows per request. When a search hits the cap, the
  price range is bisected and fetched in bands, then de-duplicated.

Keep usage light: automated access is a gray area under Redfin's terms of
use (more so with your account cookie attached), so this stays at a handful
of polite requests per run -- the same load as clicking the download link.
"""

from __future__ import annotations

import io
import os
import time
import urllib.parse
import urllib.request

import pandas as pd

from housing.config import (
    REDFIN_COLUMNS,
    REDFIN_COOKIE_ENV_VAR,
    REDFIN_COOKIE_FILE,
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

_MAX_HOMES = 350   # largest value the export endpoint accepts
_MAX_SPLITS = 4    # price-band bisection depth when a request hits the cap
_MLS_COL = "MLS#"


def _load_cookie() -> str:
    cookie = os.environ.get(REDFIN_COOKIE_ENV_VAR, "").strip()
    if cookie:
        return cookie
    try:
        return REDFIN_COOKIE_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def build_search_url(min_price=None, max_price=None) -> str:
    """Build the CSV-export URL; price overrides support band-splitting."""
    params = {
        "al": 1,
        "region_id": REDFIN_REGION_ID,
        "region_type": REDFIN_REGION_TYPE,
        "status": 9,
        "uipt": REDFIN_PROPERTY_TYPES,
        "sf": "1,2,3,5,6,7",
        "num_homes": _MAX_HOMES,
        "v": 8,
        **REDFIN_SEARCH_FILTERS,
    }
    if min_price is not None:
        params["min_price"] = min_price
    if max_price is not None:
        params["max_price"] = max_price
    return f"{EXPORT_URL}?{urllib.parse.urlencode(params)}"


def _fetch_csv(url: str, cookie: str) -> pd.DataFrame:
    headers = {"User-Agent": _USER_AGENT}
    if cookie:
        headers["Cookie"] = cookie
    request = urllib.request.Request(url, headers=headers)
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
    return listings


def _fetch_range(min_price, max_price, cookie: str, depth: int = 0) -> pd.DataFrame:
    """Fetch one price band, bisecting when the 350-row cap is hit."""
    listings = _fetch_csv(build_search_url(min_price, max_price), cookie)
    capped = len(listings) >= _MAX_HOMES
    can_split = (depth < _MAX_SPLITS and min_price is not None
                 and max_price is not None and max_price - min_price > 50_000)
    if not capped or not can_split:
        if capped:
            print(f"Warning: hit the {_MAX_HOMES}-home cap for "
                  f"{min_price}-{max_price}; narrow the search filters.")
        return listings

    mid = (int(min_price) + int(max_price)) // 2
    print(f"  > {len(listings)}+ homes in {min_price}-{max_price}; "
          f"splitting at {mid}...")
    time.sleep(1.0)
    lower = _fetch_range(min_price, mid, cookie, depth + 1)
    time.sleep(1.0)
    upper = _fetch_range(mid, max_price, cookie, depth + 1)
    return pd.concat([lower, upper], ignore_index=True)


def download_listings() -> pd.DataFrame:
    """Download the configured search as a DataFrame (raw Redfin columns)."""
    cookie = _load_cookie()
    if not cookie:
        print("NOTE: no Redfin login cookie configured -- anonymous requests "
              "only return Redfin's early-access (Pre On-Market) listings.\n"
              "      To include actively-for-sale MLS homes, put your "
              f"redfin.com cookie in {REDFIN_COOKIE_FILE} (see README).")

    listings = _fetch_range(REDFIN_SEARCH_FILTERS.get("min_price"),
                            REDFIN_SEARCH_FILTERS.get("max_price"), cookie)
    if _MLS_COL in listings.columns:
        listings = listings.drop_duplicates(subset=[_MLS_COL], keep="first")
    listings = listings.reset_index(drop=True)

    if "STATUS" in listings.columns and len(listings):
        breakdown = ", ".join(f"{k}: {v}" for k, v in
                              listings["STATUS"].value_counts().items())
        print(f"Listing statuses -- {breakdown}")
    return listings

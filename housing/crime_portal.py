"""Download recent crime data from the Chicago Data Portal (Socrata API).

Dataset: Crimes - 2001 to Present (ID ijzp-q8t2)
https://data.cityofchicago.org/Public-Safety/Crimes-2001-to-Present/ijzp-q8t2

Only the columns needed for crime scoring are downloaded, renamed to match
the schema ``housing.crime`` expects. No API token is required; optionally
set CHICAGO_APP_TOKEN to raise the unauthenticated rate limit.
"""

from __future__ import annotations

import datetime
import os
import urllib.parse

import pandas as pd

DATASET_CSV_URL = "https://data.cityofchicago.org/resource/ijzp-q8t2.csv"
APP_TOKEN_ENV_VAR = "CHICAGO_APP_TOKEN"

_PAGE_SIZE = 50_000

# Socrata field name -> column name used by the rest of the pipeline.
_COLUMN_RENAMES = {
    "date": "Date",
    "primary_type": "Primary Type",
    "description": "Description",
    "latitude": "Latitude",
    "longitude": "Longitude",
}


def download_recent_crimes(months: int = 12) -> pd.DataFrame:
    """Download crime incidents from the last ``months`` months.

    Pages through the Socrata CSV endpoint until all matching rows are
    fetched. Returns a DataFrame with Date, Primary Type, Description,
    Latitude, and Longitude columns (empty if the portal returned nothing).
    """
    cutoff = datetime.date.today() - datetime.timedelta(days=round(months * 30.44))
    params = {
        "$select": ",".join(_COLUMN_RENAMES),
        "$where": f"date >= '{cutoff.isoformat()}T00:00:00'",
        "$order": ":id",  # stable ordering for pagination
        "$limit": _PAGE_SIZE,
    }
    token = os.environ.get(APP_TOKEN_ENV_VAR, "").strip()
    if token:
        params["$$app_token"] = token

    pages = []
    offset = 0
    while True:
        query = urllib.parse.urlencode({**params, "$offset": offset})
        page = pd.read_csv(f"{DATASET_CSV_URL}?{query}")
        if not page.empty:
            pages.append(page)
        if len(page) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE
        print(f"  ...downloaded {offset:,} rows so far", flush=True)

    if not pages:
        return pd.DataFrame(columns=list(_COLUMN_RENAMES.values()))
    return pd.concat(pages, ignore_index=True).rename(columns=_COLUMN_RENAMES)

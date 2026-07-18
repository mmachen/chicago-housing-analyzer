"""Cook County Assessor lookups: parcel PIN and assessed value per home.

Free Socrata endpoints, no API key. Results are cached in SQLite because
the assessor only reassesses periodically. The nearest parcel to the home's
coordinates is used -- exact for houses; for condo buildings (many PINs at
one location) it lands on one unit of the building, so treat condo values
as approximate.

EST_TAX_ANNUAL is a separate, simpler estimate: list price times the
effective Chicago residential rate (config.EFFECTIVE_TAX_RATE) -- roughly
what taxes look like after a post-sale reassessment.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

import pandas as pd

from housing.config import EFFECTIVE_TAX_RATE

PARCEL_URL = "https://datacatalog.cookcountyil.gov/resource/nj4t-kc8j.json"
VALUES_URL = "https://datacatalog.cookcountyil.gov/resource/uzyt-m557.json"

_USER_AGENT = "housing-app/1.0"

# Residential parcels are assessed at 10% of market value in Cook County.
_RESIDENTIAL_ASSESSMENT_LEVEL = 10

_SEARCH_BOX_DEG = 0.0006  # ~65 m


def _fetch(url: str, params: dict):
    query = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{url}?{query}",
                                 headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.load(response)


def format_pin(pin: str) -> str:
    """14-digit PIN -> the XX-XX-XXX-XXX-XXXX format the county uses."""
    pin = str(pin)
    if len(pin) != 14 or not pin.isdigit():
        return pin
    return f"{pin[:2]}-{pin[2:4]}-{pin[4:7]}-{pin[7:10]}-{pin[10:]}"


def lookup_parcel_value(lat: float, lon: float) -> dict:
    """Find the nearest residential parcel and its latest assessed value.

    Returns {} on any failure so one bad lookup can't break the pipeline.
    """
    try:
        rows = _fetch(PARCEL_URL, {
            "$select": "pin,class,lat,lon,year",
            "$where": (f"lat between {lat - _SEARCH_BOX_DEG} and {lat + _SEARCH_BOX_DEG}"
                       f" AND lon between {lon - _SEARCH_BOX_DEG} and {lon + _SEARCH_BOX_DEG}"),
            "$limit": 500,
        })
    except Exception as e:
        print(f"  > Parcel lookup failed: {e}")
        return {}
    if not rows:
        return {}

    parcels = pd.DataFrame(rows).drop_duplicates(subset=["pin"])
    residential = parcels[parcels["class"].astype(str).str.startswith("2")]
    if residential.empty:
        residential = parcels
    residential = residential.assign(
        _d=(pd.to_numeric(residential["lat"], errors="coerce") - lat).abs()
        + (pd.to_numeric(residential["lon"], errors="coerce") - lon).abs())
    pin = str(residential.nsmallest(1, "_d")["pin"].iloc[0])

    market_value = None
    value_year = None
    try:
        values = _fetch(VALUES_URL, {
            "pin": pin, "$order": "year DESC", "$limit": 5})
        for row in values:
            total = (row.get("board_tot") or row.get("certified_tot")
                     or row.get("mailed_tot"))
            if total and float(total) > 0:
                market_value = float(total) * _RESIDENTIAL_ASSESSMENT_LEVEL
                value_year = str(row.get("year", "")).split(".")[0]
                break
    except Exception as e:
        print(f"  > Assessed-value lookup failed for PIN {pin}: {e}")

    return {"pin": pin, "market_value": market_value, "value_year": value_year}


def add_tax_features(prop_df: pd.DataFrame, cache) -> None:
    """Fill ASSESSOR_PIN / ASSESSOR_MARKET_VALUE / EST_TAX_ANNUAL columns."""
    prop_df["EST_TAX_ANNUAL"] = (
        pd.to_numeric(prop_df["PRICE"], errors="coerce") * EFFECTIVE_TAX_RATE
    ).round()

    for i in prop_df.index:
        lat, lon = prop_df.at[i, "LATITUDE"], prop_df.at[i, "LONGITUDE"]
        if pd.isna(lat) or pd.isna(lon):
            continue
        cache_key = f"parcel|{round(lat, 6)}|{round(lon, 6)}"
        info = cache.get(cache_key)
        if info is None:
            info = lookup_parcel_value(lat, lon)
            cache.set(cache_key, info)
        if info.get("pin"):
            prop_df.at[i, "ASSESSOR_PIN"] = format_pin(info["pin"])
        if info.get("market_value"):
            prop_df.at[i, "ASSESSOR_MARKET_VALUE"] = info["market_value"]
            prop_df.at[i, "ASSESSOR_VALUE_YEAR"] = info.get("value_year")

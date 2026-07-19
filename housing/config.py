"""Central configuration for the housing pipeline and web app.

File paths, commute destinations, amenity definitions, and scoring defaults
all live here so they can be tuned without touching the pipeline code.

Note: commute destination names and amenity names become part of the generated
column names (e.g. ``COMMUTE_TIME_work_Mike``, ``GROCERY_CLOSEST``), which the
dashboard template reads. Renaming an entry orphans previously generated data.
"""

from __future__ import annotations

import os
from pathlib import Path

# --- Directories and files -------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data_sets"
OUTPUT_DIR = PROJECT_ROOT / "output"
CACHE_DIR = PROJECT_ROOT / "cache"

REDFIN_RAW_CSV = DATA_DIR / "RedFin_raw_data.csv"
CRIME_CSV = DATA_DIR / "Crimes_-_202103.csv"  # static fallback extract
CRIME_RECENT_CSV = DATA_DIR / "Crimes_recent.csv"  # written by update_crime_data.py
AFFORDABLE_HOUSING_CSV = DATA_DIR / "Affordable_Rental_Housing_Developments.csv"
SOCIOECONOMIC_CSV = DATA_DIR / "socioeconomic_indicators.csv"
LANGUAGES_CSV = DATA_DIR / "languages_spoken.csv"

FINAL_DATA_CSV = OUTPUT_DIR / "final_data.csv"
CACHE_DB = CACHE_DIR / "cache.db"

# Neighborhood datasets written by update_area_data.py (all free sources).
CTA_BUS_STOPS_CSV = DATA_DIR / "cta_bus_stops.csv"
METRA_STATIONS_CSV = DATA_DIR / "metra_stations.csv"
CPS_SCHOOLS_CSV = DATA_DIR / "cps_schools.csv"
RODENT_CSV = DATA_DIR / "rodent_complaints.csv"

# Price history appended by fetch_listings.py on every pull.
LISTING_HISTORY_CSV = DATA_DIR / "listing_history.csv"

# CTA rail geometry (also drawn on the dashboard map).
CTA_LINES_GEOJSON = PROJECT_ROOT / "static" / "cta_lines.geojson"


def crime_csv_path() -> Path:
    """Prefer the refreshed portal download; fall back to the static extract."""
    return CRIME_RECENT_CSV if CRIME_RECENT_CSV.exists() else CRIME_CSV

# Column names assigned to the raw Redfin export, in file order.
REDFIN_COLUMNS = [
    "SALE_TYPE", "SOLD_DATE", "PROPERTY_TYPE", "ADDRESS", "CITY", "STATE",
    "ZIP", "PRICE", "BEDS", "BATHS", "LOCATION", "SQFT", "LOT_SIZE", "YEAR",
    "DAY_ON_MARKET", "PRICE_PER_SQFT", "HOA", "STATUS", "NEXT_OPEN_S",
    "NEXT_OPEN_E", "URL", "SOURCE", "MLS", "FAVORITE", "INTERESTED",
    "LATITUDE", "LONGITUDE",
]

# --- Redfin search ---------------------------------------------------------

# Region for automated listing pulls (redfin.com/city/29470/IL/Chicago).
REDFIN_REGION_ID = 29470
REDFIN_REGION_TYPE = 6  # 6 = city

# Search filters applied server-side by Redfin. Garage must be filtered here
# because the CSV export has no parking column.
# To change the search: edit these values, then run
#   python fetch_listings.py
#   python build_dataset.py
# (drop max_price entirely for no upper limit; new homes only get commute/
# amenity data on a full build, which costs Google API calls per new home).
REDFIN_SEARCH_FILTERS = {
    "min_price": 600_000,
    "max_price": 1_400_000,
    "num_beds": 3,   # minimum bedrooms
    "num_baths": 2,  # minimum bathrooms
    "gar": "true",   # must have a garage
}

# Property types to include: 1=house, 2=condo, 3=townhouse, 4=multi-family.
REDFIN_PROPERTY_TYPES = "1,2,3,4"

# Redfin only returns MLS-listed (Active/Contingent/Pending) homes to
# signed-in sessions; anonymous requests get only Redfin's own
# "early access" (Pre On-Market) pool. Paste your browser's redfin.com
# cookie into this file (or the REDFIN_COOKIE env var) to get everything --
# see the README for how to copy it.
REDFIN_COOKIE_ENV_VAR = "REDFIN_COOKIE"
REDFIN_COOKIE_FILE = PROJECT_ROOT / "delete" / "redfin_cookie.txt"

# --- Google Maps API -------------------------------------------------------

API_KEY_ENV_VAR = "GOOGLE_MAPS_API_KEY"
API_KEY_FILE = PROJECT_ROOT / "delete" / "input.txt"
GOOGLE_QUERIES_PER_SECOND = 15


def load_google_api_key() -> str:
    """Return the Google Maps API key from the environment or the key file."""
    key = os.environ.get(API_KEY_ENV_VAR, "").strip()
    if key:
        return key
    try:
        return API_KEY_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        raise RuntimeError(
            f"Google Maps API key not found. Set the {API_KEY_ENV_VAR} "
            f"environment variable or create {API_KEY_FILE} containing the key."
        ) from None


# --- Commutes --------------------------------------------------------------

COMMUTE_DESTINATIONS = {
    "work_Mike": "320 S Canal St, Chicago, IL",
    "work_Xixi": "100 N Carpenter St, Chicago, IL",
    "school_Hana": "4929 N Sawyer Ave, Chicago, IL",
}

# Destinations that also get a rush-hour driving estimate (DRIVE_TIME_<name>).
DRIVING_DESTINATIONS = ("school_Hana",)

# Dashboard map markers for the destinations. Coordinates were geocoded once
# (OpenStreetMap Nominatim) so the dashboard makes no geocoding API calls;
# update them if a destination address in COMMUTE_DESTINATIONS changes.
DESTINATION_MARKERS = {
    "work_Mike": {"label": "Mike's Work", "icon": "\U0001F4BC",  # briefcase
                  "lat": 41.877115, "lon": -87.639991},
    "work_Xixi": {"label": "Xixi's Work", "icon": "\U0001F3E2",  # office
                  "lat": 41.885287, "lon": -87.653409},
    "school_Hana": {"label": "Hana's School", "icon": "\U0001F3EB",  # school
                    "lat": 41.971171, "lon": -87.709471},
}

# Per-destination commute requirements, in minutes, for the commute part of
# OVERALL_SCORE. A commute at or under "target" gets full credit; credit
# falls linearly to zero at "max" (at or beyond max scores 0). The home's
# commute score is its WORST destination score, so one unacceptable commute
# sinks the home no matter how good the others are. "mode" picks which
# measured time is judged: "transit" (COMMUTE_TIME) or "drive" (DRIVE_TIME).
COMMUTE_REQUIREMENTS = {
    "work_Mike": {"target": 60, "max": 90, "mode": "transit"},
    "work_Xixi": {"target": 60, "max": 90, "mode": "transit"},
    "school_Hana": {"target": 30, "max": 60, "mode": "drive"},  # driven to school
}

# CTA train lines flagged per commute (USES_<line>_LINE_<destination>).
CTA_TRAIN_LINES = ("BROWN", "RED", "BLUE", "PINK", "GREEN", "ORANGE", "PURPLE")

# Bump to force a refresh of all commute data on the next pipeline run.
# v3: step summaries now include board/exit stops and per-step durations.
COMMUTE_LOGIC_VERSION = 3

# --- Amenities -------------------------------------------------------------

# Internal name -> Google Places query. Names listed in KEYWORD_AMENITIES are
# searched by keyword (brand names); the rest use a Places "type" search.
AMENITY_TYPES = {
    "grocery": "grocery_or_supermarket",
    "restaurant": "restaurant",
    "liquor": "liquor_store",
    "bars": "bar",
    "parks": "park",
    "chicago_public_library": "Chicago Public Library",
    "whole_foods": "Whole Foods",
    "trader_joes": "Trader Joe's",
}

KEYWORD_AMENITIES = {"chicago_public_library", "whole_foods", "trader_joes"}

# Amenities counted toward the amenities part of OVERALL_SCORE.
SCORED_AMENITIES = ("grocery", "restaurant", "parks", "chicago_public_library")

# Bump to force a refresh of all places/amenity data on the next pipeline run.
PLACES_LOGIC_VERSION = 2

PLACES_SEARCH_RADIUS_METERS = 3200  # ~2 miles
WALKABLE_RADIUS_MILES = 0.5

# --- Local dataset radii ---------------------------------------------------

CRIME_RADIUS_MILES = 2.0
AFFORDABLE_RADIUS_MILES = 0.5
BUS_STOP_RADIUS_MILES = 0.25     # ~5-minute walk
RODENT_RADIUS_MILES = 0.25
CRIME_TREND_RADIUS_MILES = 1.0
NEAR_L_TRACKS_MILES = 0.095      # ~500 ft: close enough to hear the trains

# --- Taxes and carrying costs ----------------------------------------------

# Rough effective property-tax rate for Chicago residential, applied to the
# list price for the EST_TAX_ANNUAL estimate. Exact bills vary by exemptions
# and reassessment -- check the PIN on cookcountypropertyinfo.com.
EFFECTIVE_TAX_RATE = 0.019

# $1/month of HOA reduces buying power like ~$200 of price (rate-dependent);
# used to fold HOA fees into the value score.
HOA_PRICE_EQUIVALENT = 200

# --- Caching and scoring ---------------------------------------------------

DEFAULT_CACHE_TTL_DAYS = 14

# Positive components sum to 1; "bars" and "gun" are penalties subtracted
# from the total (avoid homes near bars and gun incidents).
#
# Two ways to tune these:
#   1. Per run, via CLI flags on build_dataset.py or refresh_all.py:
#        python build_dataset.py --w-gun 0.25    # punish gun incidents harder
#        python build_dataset.py --w-bars 0.15   # punish bar density harder
#        python build_dataset.py --w-commute 0.5 # emphasize commutes
#      (recompute for free by adding: --skip-commute --skip-places)
#   2. Permanently, by editing the values below.
DEFAULT_SCORE_WEIGHTS = {
    "commute": 0.4,
    "crime": 0.3,
    "amenities": 0.2,
    "price": 0.1,
    "bars": 0.1,
    "gun": 0.15,
}
